import os
import re
import sqlite3

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # only needed for a Postgres deployment
    psycopg2 = None
    RealDictCursor = None

# Ueber die Umgebung setzbar, damit Tests gegen eine eigene Wegwerf-Datei
# laufen statt gegen die Entwicklungsdatenbank.
DB_PATH = os.environ.get('SCHICHTPLAN_DB_PATH', 'schichtplan.db')

# Weekday convention throughout this project: 0=Monday ... 6=Sunday (Python's date.weekday()).
# Language-keyed so the same index works for both the UI (frontend has its own
# copy, see frontend/src/i18n) and backend-generated messages (app.py).
WEEKDAYS = {
    'de': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'],
    'en': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
}


def use_postgres():
    return bool(os.environ.get('DATABASE_URL'))


# SQLite is the local default because it needs no setup; hosted deployments set
# DATABASE_URL and get Postgres, because a container's filesystem does not
# survive a restart and a schedule that vanishes overnight is worse than useless.
# The queries are written once, in SQLite's dialect, and translated below.

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
    """Bringt das Schema auf den aktuellen Stand.

    Der eigentliche Inhalt liegt jetzt in backend/migrations/ - siehe
    migrations.py. Diese Funktion bleibt als Einstiegspunkt bestehen, damit
    app.py sich nicht aendern muss.
    """
    from migrations import apply_pending
    apply_pending()
