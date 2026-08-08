import os
import re
import sqlite3

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # only needed for a Postgres deployment
    psycopg2 = None
    RealDictCursor = None

DB_PATH = 'schichtplan.db'

# Weekday convention throughout this project: 0=Monday ... 6=Sunday (Python's date.weekday()).
WEEKDAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']


def use_postgres():
    return bool(os.environ.get('DATABASE_URL'))


# SQLite is the local default because it needs no setup; hosted deployments set
# DATABASE_URL and get Postgres, because a container's filesystem does not
# survive a restart and a schedule that vanishes overnight is worse than useless.
# The queries are written once, in SQLite's dialect, and translated below.

AUTO_ID = 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'

_INSERT_WITHOUT_RETURNING = re.compile(r'^\s*INSERT\b(?!.*\bRETURNING\b)', re.IGNORECASE | re.DOTALL)


class _PostgresCursor:
    """Adapts psycopg2 to the SQLite calling style the rest of the code uses.

    Two differences matter: parameters are %s rather than ?, and there is no
    lastrowid, so an INSERT that does not already ask for something back is given
    a RETURNING id and the value is captured where callers expect it.
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, query, params=()):
        translated = query.replace('?', '%s')
        wants_id = bool(_INSERT_WITHOUT_RETURNING.match(translated))
        if wants_id:
            translated = translated.rstrip().rstrip(';') + ' RETURNING id'

        self._cursor.execute(translated, params)

        if wants_id:
            row = self._cursor.fetchone()
            self.lastrowid = row['id'] if row else None
        else:
            self.lastrowid = None
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self._cursor.fetchall()]

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *_args, **_kwargs):
        return _PostgresCursor(self._connection.cursor(cursor_factory=RealDictCursor))

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_db_connection():
    if use_postgres():
        connection = psycopg2.connect(os.environ['DATABASE_URL'], sslmode=os.environ.get('PGSSLMODE', 'require'))
        return _PostgresConnection(connection)

    connection = sqlite3.connect(DB_PATH)
    connection.execute('PRAGMA foreign_keys = ON')
    connection.row_factory = sqlite3.Row
    return connection


def table_columns(cursor, table):
    """Existing column names, however the database likes to be asked."""
    if use_postgres():
        cursor.execute(
            'SELECT column_name AS name FROM information_schema.columns WHERE table_name = ?',
            (table,),
        )
    else:
        cursor.execute(f'PRAGMA table_info({table})')
    return {row['name'] for row in cursor.fetchall()}


def init_db():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Created first: users references it, and Postgres requires the target of a
    # foreign key to exist already.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employees(
            id {AUTO_ID},
            name TEXT NOT NULL,
            email TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            max_shifts_per_month INTEGER,
            weekly_hours REAL,
            min_rest_hours REAL NOT NULL DEFAULT 11,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Databases created before part-time/rest-period support only have the
    # original columns - CREATE TABLE IF NOT EXISTS above is a no-op for them.
    employee_columns = table_columns(cursor, 'employees')
    if 'weekly_hours' not in employee_columns:
        # Target hours/week for staff who don't work full time; None = no target,
        # unaffected by the weekly cap the scheduler enforces (see scheduler.py).
        cursor.execute('ALTER TABLE employees ADD COLUMN weekly_hours REAL')
    if 'min_rest_hours' not in employee_columns:
        # Hours required between the end of one shift and the start of the next
        # (German ArbZG default: 11h). NOT NULL with a default - unlike
        # weekly_hours, this is a safety-relevant setting that should never
        # silently become "no minimum" just because a write omitted it.
        cursor.execute('ALTER TABLE employees ADD COLUMN min_rest_hours REAL NOT NULL DEFAULT 11')

    # Accounts that can sign in. Two roles:
    #   'hr'       - full access: manages employees, shift types and schedules
    #   'employee' - read-only: may look at the published schedule, nothing else
    # Being scheduled does not require an account, so the employees table stays
    # separate; employee_id optionally links an account to its roster entry so
    # the calendar can highlight that person's own shifts.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS users(
            id {AUTO_ID},
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'hr',
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # One open invitation per account. HR never sees the token: it goes out by
    # email, so the person sets a password only they know. Only a SHA-256 of the
    # token is stored, so a copy of the database cannot be used to claim an
    # account - the token itself is 256 bits of randomness, which is why an
    # unsalted digest is enough here.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS password_invitations(
            id {AUTO_ID},
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Databases created before roles existed only have the original columns.
    user_columns = table_columns(cursor, 'users')
    if 'role' not in user_columns:
        # Existing accounts predate the split and were all full-access.
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'hr'")
    if 'employee_id' not in user_columns:
        cursor.execute('ALTER TABLE users ADD COLUMN employee_id INTEGER REFERENCES employees(id)')
    if 'email' not in user_columns:
        # Where an HR account's invitation goes. Employee accounts take theirs
        # from the linked roster entry instead, so it is not duplicated here.
        cursor.execute('ALTER TABLE users ADD COLUMN email TEXT')

    # Recurring weekly unavailability, e.g. "never works Wednesdays".
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_unavailable_weekdays(
            id {AUTO_ID},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            UNIQUE(employee_id, weekday)
        )
    ''')

    # One-off unavailability, e.g. vacation or sick leave on specific dates.
    # HR-managed: replace_employee_constraints() in app.py wipes and reinserts
    # this table from the roster form on every save of that employee, so it is
    # not where the *self-reported* absences below live - a save of an
    # unrelated field would silently erase them.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_unavailable_dates(
            id {AUTO_ID},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            reason TEXT,
            UNIQUE(employee_id, date)
        )
    ''')

    # Self-reported sick/vacation days. Separate from employee_unavailable_dates
    # above on purpose (see that table's comment) - this is the one place an
    # employee account is allowed to write, and only ever its own rows, only
    # ever for the current month (enforced in app.py, not here). Also feeds
    # load_employees_for_scheduling() so a later regeneration doesn't schedule
    # someone back onto a day they reported as sick/on vacation.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_absences(
            id {AUTO_ID},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            absence_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, date)
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_types(
            id {AUTO_ID},
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#0d9488',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # How many people are needed for a shift type, per weekday (weekends often differ from weekdays).
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_requirements(
            id {AUTO_ID},
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            required_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(shift_type_id, weekday)
        )
    ''')

    # If an employee has no rows here, they may work any shift type (no restriction).
    # If they have rows, they may only work the listed shift types (e.g. "only Frühschicht").
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_allowed_shift_types(
            id {AUTO_ID},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            UNIQUE(employee_id, shift_type_id)
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schedules(
            id {AUTO_ID},
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            unfilled_count INTEGER NOT NULL DEFAULT 0,
            generated_at TIMESTAMP,
            UNIQUE(year, month)
        )
    ''')

    # Lets one date run a shift at different hours than the shift type says,
    # e.g. the early shift finishing at 14:00 on Christmas Eve. Keyed per shift
    # per date, so everyone on that shift that day shares the changed hours.
    # Deliberately survives regeneration: hours HR set for a date should stick.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_time_overrides(
            id {AUTO_ID},
            schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            UNIQUE(schedule_id, date, shift_type_id)
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_assignments(
            id {AUTO_ID},
            schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id),
            slot_index INTEGER NOT NULL,
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            manually_edited INTEGER NOT NULL DEFAULT 0,
            absence_type TEXT,
            absent_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL
        )
    ''')

    # Databases created before self-service sick/vacation reporting only have
    # the original columns - CREATE TABLE IF NOT EXISTS above is a no-op for them.
    assignment_columns = table_columns(cursor, 'shift_assignments')
    if 'absence_type' not in assignment_columns:
        # Set (to 'sick'/'vacation') when this slot was freed because the
        # employee who had it reported an absence - employee_id is NULL at
        # that point (the slot behaves like any other open slot) and
        # absent_employee_id (below) remembers who it was, for display and so
        # they're excluded from their own replacement suggestions.
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN absence_type TEXT')
    if 'absent_employee_id' not in assignment_columns:
        cursor.execute(
            'ALTER TABLE shift_assignments ADD COLUMN absent_employee_id '
            'INTEGER REFERENCES employees(id) ON DELETE SET NULL'
        )

    connection.commit()
    connection.close()
