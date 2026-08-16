"""Hilfsfunktionen fuer Tests gegen ein echtes Postgres.

Bewusst kein Fixture-Modul (kein test_*.py-Praefix, wird von pytest nicht
selbst eingesammelt) - nur Bausteine, die conftest.py und
test_migrations_postgres.py gemeinsam nutzen.

Opt-in ueber TEST_DATABASE_URL statt DATABASE_URL: DATABASE_URL ist auch das
Signal, an dem db.use_postgres() eine Produktionsumgebung erkennt (siehe
db.py). Wuerde die Testsuite allein auf DATABASE_URL reagieren, koennte ein
Entwickler mit einer echten Produktions-URL in der Umgebung (z.B. lokal aus
Render kopiert, um einen Bug nachzustellen) versehentlich die Testsuite
dagegen laufen lassen. Der eigene Name macht daraus eine bewusste
Entscheidung.

Isolation: SQLite bekommt pro Test eine frische Datei (conftest.py). Das
Postgres-Aequivalent hier ist ein frisches Schema pro Test in derselben
Datenbank. db.py selbst weiss nichts davon - die Isolation wird allein
darueber erreicht, dass die pro Test gesetzte DATABASE_URL einen
"options=-c search_path=<schema>"-Parameter traegt: das ist eine
Standard-libpq-Verbindungsoption, die den Suchpfad schon vor der ersten
Anweisung der Verbindung umbiegt. app.py/db.py/migrations.py bleiben dadurch
unveraendert - nur die Verbindungs-URL unterscheidet sich zwischen Tests.
"""

import contextlib
import os
import uuid
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

try:
    import psycopg2
except ImportError:  # dev-requirements installieren psycopg2-binary immer mit,
    psycopg2 = None  # aber ein Import ohne TEST_DATABASE_URL darf trotzdem nicht scheitern.


def resolve_test_database_url():
    """Die vom Entwickler/von CI gesetzte Basis-Verbindung, oder None.

    None ist der weit ueberwiegende Fall (lokale Entwicklung ohne Postgres) -
    jede Aufruferin muss darauf mit dem bisherigen SQLite-Verhalten reagieren.

    Bewusst nicht "test_..." genannt: pytest sammelt sonst diese importierte
    Funktion selbst als Testfall ein (Namenskonvention test_*), obwohl sie nur
    eine Umgebungsvariable ausliest.
    """
    return os.environ.get('TEST_DATABASE_URL') or None


def _schema_scoped_url(base_url, schema):
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query))
    # Leerzeichen bewusst als %20 kodiert (quote_via=quote), nicht als '+':
    # libpq entscheidet nicht zuverlaessig, ob ein '+' im Query-Teil einer URI
    # eine Kodierung des Leerzeichens ist. -c erwartet syntaktisch ein
    # Leerzeichen vor dem Parameternamen.
    query['options'] = f'-c search_path={schema}'
    new_query = urlencode(query, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


@contextlib.contextmanager
def temporary_schema(base_url):
    """Legt ein frisches, eindeutig benanntes Schema an und raeumt es wieder ab.

    Liefert (schema_scoped_url, schema_name). schema_scoped_url ist eine
    vollstaendige DATABASE_URL, die ausschliesslich dieses Schema sieht -
    geeignet, um sie direkt als Umgebungsvariable fuer db.py zu setzen.
    """
    if psycopg2 is None:
        raise RuntimeError('psycopg2 fehlt - TEST_DATABASE_URL kann nicht bedient werden')

    schema = f'pgtest_{uuid.uuid4().hex[:16]}'
    admin_connection = psycopg2.connect(base_url)
    admin_connection.autocommit = True
    try:
        with admin_connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema}"')
        try:
            yield _schema_scoped_url(base_url, schema), schema
        finally:
            with admin_connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        admin_connection.close()
