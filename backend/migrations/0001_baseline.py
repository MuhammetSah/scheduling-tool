"""Ausgangsschema.

Wortgleich der bisherige init_db()-Rumpf aus db.py. Alle CREATE-Anweisungen
sind IF NOT EXISTS und die Spaltenergaenzungen sind bedingt, deshalb ist diese
Migration auf einer bestehenden Produktionsdatenbank ein reiner No-op, der nur
die Version protokolliert.

Ab 0002 sind Migrationen einfache SQL-Dateien.
"""

from db import table_columns, use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    auto_id = _auto_id()

    # Created first: users references it, and Postgres requires the target of a
    # foreign key to exist already.
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employees(
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            absence_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, date)
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_types(
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            UNIQUE(employee_id, shift_type_id)
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schedules(
            id {auto_id},
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
            id {auto_id},
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
            id {auto_id},
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


def down(cursor):
    """Es gibt keinen Weg hinter das Ausgangsschema zurueck."""
    raise RuntimeError('Das Ausgangsschema kann nicht zurueckgerollt werden')
