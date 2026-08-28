import logging
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

# Neben den Wochentagen, weil sie dasselbe sind: Beschriftungen, die kein
# Satz sind und deshalb nicht in i18n.py mit seinen Vorlagen passen. Gebraucht
# fuer den Namen des iCal-Kalenders.
MONTHS = {
    'de': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
           'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],
    'en': ['January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December'],
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
    """Existing column names, however the database likes to be asked.

    information_schema.columns is not restricted by search_path - it lists
    every table the connecting role can see, in every schema. Filtering by
    table_name alone (without table_schema) is invisible on a single-schema
    database, which is what every deployment of this project has been so
    far, but merges columns from unrelated same-named tables together on any
    Postgres database that has more than one schema - found while adding
    Postgres test coverage: two temporary per-test schemas, each with their
    own 'employees' table, made this query return the union of both. Scoping
    to current_schema() (the first entry of search_path, which is exactly
    the schema each connection here is meant to see - see the per-test
    search_path override in pg_testsupport.py) fixes that without needing to
    know the schema name up front.
    """
    if use_postgres():
        cursor.execute(
            'SELECT column_name AS name FROM information_schema.columns '
            'WHERE table_name = ? AND table_schema = current_schema()',
            (table,),
        )
    else:
        cursor.execute(f'PRAGMA table_info({table})')
    return {row['name'] for row in cursor.fetchall()}


_logger = logging.getLogger(__name__)


def init_db():
    """Bringt das Schema auf den aktuellen Stand.

    Der eigentliche Inhalt liegt jetzt in backend/migrations/ - siehe
    migrations.py. Diese Funktion bleibt als Einstiegspunkt bestehen, damit
    app.py sich nicht aendern muss.

    Protokolliert das Ergebnis, statt es wegzuwerfen: das ist auf Renders
    Free-Plan ohne Shell-Zugriff die einzige Stelle, an der nach einem Deploy
    sichtbar wird, ob und welche Migration gerade angewandt wurde (siehe
    app.py fuer die Logging-Konfiguration, die dafuer vor diesem Aufruf
    stehen muss).
    """
    from migrations import apply_pending
    applied = apply_pending()
    if applied:
        _logger.info('Migrationen angewandt: %s', ', '.join(applied))
    else:
        _logger.info('Keine Migrationen ausstehend')
