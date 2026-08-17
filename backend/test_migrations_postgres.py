"""Der Migrations-Runner und die Dialektschicht (db.py), gegen echtes Postgres.

test_migrations.py deckt denselben Runner nur gegen SQLite ab - dort laufen
seine eigenen Pruef-Helfer (tabellen(), indizes()) direkt gegen eine
sqlite3-Datei und lassen sich nicht sinnvoll auf Postgres uebertragen, ohne
jede Testfunktion umzuschreiben. Diese Datei bildet stattdessen gezielt genau
die Postgres-spezifischen Risiken nach, die in db.py/migrations.py nie
gegen eine echte Datenbank gelaufen sind: SERIAL statt AUTOINCREMENT,
RETURNING id, die auf Postgres implizite Transaktion hinter _begin(), das
Verhalten von CREATE UNIQUE INDEX IF NOT EXISTS auf einer Tabelle mit
bereits vorhandenen doppelten Zeilen, information_schema-Spaltenpruefung, der
Text-Vergleich in security.py und der Advisory-Lock in _migration_lock(), der
zwei gleichzeitige apply_pending()-Aufrufe serialisiert (siehe
test_gleichzeitige_worker_wenden_dieselbe_migration_nicht_doppelt_an unten).

Uebersprungen, wenn TEST_DATABASE_URL nicht gesetzt ist (siehe
pg_testsupport.py) - das ist der Normalfall fuer eine lokale
Entwicklungsumgebung ohne Postgres und fuer die bestehenden SQLite-CI-Jobs.
Absichtlich ein eigener Name statt DATABASE_URL: DATABASE_URL ist zugleich
das Signal, an dem db.use_postgres() eine Produktionsumgebung erkennt, und
darf nicht allein durch das Ausfuehren der Testsuite gesetzt/angesprochen
werden.

Isolation: jeder Test, der eine Datenbank braucht, bekommt ueber die
pg_db/pg_leere_migrationen-Fixtures ein frisches, eindeutig benanntes
Postgres-Schema (siehe pg_testsupport.temporary_schema). Das wird nicht nur
behauptet, sondern in test_zwei_schemata_teilen_keine_daten unten auch
gezeigt.
"""

import sys
import threading
from pathlib import Path

import psycopg2
import pytest

from pg_testsupport import resolve_test_database_url, temporary_schema

pytestmark = pytest.mark.skipif(
    not resolve_test_database_url(),
    reason='TEST_DATABASE_URL nicht gesetzt - Postgres-Tests uebersprungen (siehe pg_testsupport.py)',
)

BASELINE_PATH = Path(__file__).resolve().parent / 'migrations' / '0001_baseline.py'
INDEXES_SQL_PATH = Path(__file__).resolve().parent / 'migrations' / '0002_indexes.sql'
LOGIN_ATTEMPTS_SQL_PATH = Path(__file__).resolve().parent / 'migrations' / '0003_login_attempts.sql'
AVAILABILITY_PY_PATH = Path(__file__).resolve().parent / 'migrations' / '0004_employee_availability.py'


@pytest.fixture
def pg_db(monkeypatch):
    """Frisches Postgres-Schema samt frisch importiertem migrations-Modul.

    Postgres-Pendant zu fresh_db in test_migrations.py.
    """
    base_url = resolve_test_database_url()
    with temporary_schema(base_url) as (schema_url, schema):
        monkeypatch.setenv('DATABASE_URL', schema_url)
        monkeypatch.delenv('SCHICHTPLAN_DB_PATH', raising=False)

        for module in ('db', 'migrations'):
            sys.modules.pop(module, None)

        import migrations
        yield migrations, schema_url, schema


@pytest.fixture
def pg_leere_migrationen(pg_db, tmp_path, monkeypatch):
    """Isoliertes, leeres Migrationsverzeichnis - Postgres-Pendant zu
    leere_migrationen in test_migrations.py.
    """
    migrations, schema_url, schema = pg_db
    verzeichnis = tmp_path / 'test_migrations_pg'
    verzeichnis.mkdir()
    monkeypatch.setattr(migrations, 'MIGRATIONS_DIR', verzeichnis)
    return migrations, verzeichnis, schema_url, schema


def tabellen(schema_url, schema):
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT table_name FROM information_schema.tables WHERE table_schema = %s',
                (schema,),
            )
            return {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()


def indizes(schema_url, schema):
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT indexname FROM pg_indexes WHERE schemaname = %s', (schema,))
            return {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()


def test_frische_datenbank_bekommt_alle_tabellen(pg_db):
    migrations, schema_url, schema = pg_db

    angewandt = migrations.apply_pending()

    assert '0001_baseline' in angewandt
    assert {'employees', 'users', 'shift_types', 'shift_assignments',
            'schedules', 'schema_migrations', 'login_attempts',
            'employee_availability'} <= tabellen(schema_url, schema)


def test_auto_id_wird_als_serial_primary_key_angelegt(pg_db):
    """{auto_id} muss auf Postgres zu SERIAL PRIMARY KEY werden, nicht zu
    SQLites INTEGER PRIMARY KEY AUTOINCREMENT (siehe _placeholders() in
    migrations.py) - erkennbar an einer ueber eine Sequenz erzeugten
    column_default fuer die id-Spalte.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'employees' AND column_name = 'id'",
                (schema,),
            )
            default = cursor.fetchone()[0]
    finally:
        connection.close()

    assert default is not None and 'nextval' in default


def test_returning_id_wird_bei_blankem_insert_in_schema_migrations_verwendet(pg_db):
    """apply_pending() traegt jede Version ueber ein INSERT ohne eigenes
    RETURNING ein (siehe migrations.py). Schluege das automatische Anhaengen
    von RETURNING id in _PostgresCursor.execute() fehl, waere apply_pending()
    schon nicht durchgelaufen - dieser Test macht die Erwartung trotzdem
    explizit, indem er die vergebene id nachschlaegt.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM schema_migrations WHERE version = '0001_baseline'")
            row = cursor.fetchone()
    finally:
        connection.close()

    assert row is not None and row[0] is not None


def test_returning_id_wird_bei_blankem_insert_in_login_attempts_verwendet(pg_db):
    """Derselbe Mechanismus wie oben, diesmal fuer eine Anwendungstabelle
    statt fuer den Runner selbst - login_attempts ist genau die Tabelle, ueber
    die security.py bei jedem Anmeldeversuch schreibt.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    import db
    connection = db.get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO login_attempts (identifier, ip, succeeded, attempted_at) VALUES (?, ?, ?, ?)',
            ('tester', '127.0.0.1', 0, '2026-08-16T00:00:00+00:00'),
        )
        assert cursor.lastrowid is not None
        connection.commit()
    finally:
        connection.close()


def test_availability_mode_hat_anytime_als_standard(pg_leere_migrationen):
    """Postgres-Gegenstueck zu test_availability_mode_hat_anytime_als_standard
    in test_migrations.py: ALTER TABLE employees ADD COLUMN ... NOT NULL
    DEFAULT 'anytime' (0004_employee_availability.py) ist genau die Art
    Anweisung, deren Verhalten auf bereits vorhandenen Zeilen zwischen
    Dialekten abweichen kann - deshalb hier gegen echtes Postgres geprueft,
    nicht nur auf SQLite angenommen.

    Baut wie das SQLite-Original die echte Reihenfolge nach: erst 0001-0003
    anwenden, dann eine Mitarbeiterzeile einfuegen, dann erst 0004 obendrauf
    - statt einen Insert erst nach einer bereits vollstaendigen Migration zu
    machen, was einen fehlenden DEFAULT gar nicht bemerken wuerde, weil die
    Spalte dann schon existiert, bevor ueberhaupt etwas eingefuegt wird.
    """
    migrations, verzeichnis, schema_url, schema = pg_leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0003_login_attempts.sql').write_text(
        LOGIN_ATTEMPTS_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0004_employee_availability.py').write_text(
        AVAILABILITY_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT availability_mode FROM employees WHERE name = 'Anna'")
            modus = cursor.fetchone()[0]
    finally:
        connection.close()

    assert modus == 'anytime'


def spalten(schema_url, schema, tabelle):
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_schema = %s AND table_name = %s',
                (schema, tabelle),
            )
            return {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()


def test_fenstermigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(pg_db):
    """Postgres-Gegenstueck zu derselben Pruefung in test_migrations.py.

    Der Rundlauf up -> down -> up scheitert ohne die bedingte Pruefung in
    0004_employee_availability.py auf beiden Dialekten, nur mit
    unterschiedlichem Fehler: SQLite meldet "duplicate column name", Postgres
    einen DuplicateColumn - ADD COLUMN IF NOT EXISTS gaebe es zwar auf
    Postgres, aber nicht auf SQLite, deshalb prueft die Migration die Spalte
    selbst ueber db.table_columns(). Genau dieser Zweig laeuft hier gegen
    information_schema statt gegen PRAGMA table_info - eine andere
    Implementierung derselben Pruefung, die deshalb auch hier belegt gehoert.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    while '0004_employee_availability' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'employee_availability' not in tabellen(schema_url, schema)
    # Die Spalte ueberlebt die Ruecknahme absichtlich (siehe down() in
    # 0004_employee_availability.py) - das ist die Entscheidung, nicht der Fehler.
    assert 'availability_mode' in spalten(schema_url, schema, 'employees')

    erneut = migrations.apply_pending()

    assert '0004_employee_availability' in erneut
    assert 'employee_availability' in tabellen(schema_url, schema)
    assert 'availability_mode' in spalten(schema_url, schema, 'employees')


def test_fenster_werden_beim_loeschen_des_mitarbeiters_mitgeloescht(pg_db):
    """Postgres-Gegenstueck zu derselben Pruefung in test_migrations.py:
    ON DELETE CASCADE ist auf Postgres immer aktiv (anders als bei SQLite,
    das PRAGMA foreign_keys = ON pro Verbindung braucht, siehe
    db.get_db_connection()) - trotzdem hier explizit gegen echtes Postgres
    geprueft statt nur angenommen.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    import db
    connection = db.get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO employees (name) VALUES ('Anna')")
        employee_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO employee_availability (employee_id, weekday, start_time, end_time) '
            'VALUES (?, 0, ?, ?)', (employee_id, '08:00', '14:00'))
        connection.commit()
        cursor.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
        connection.commit()
        cursor.execute('SELECT COUNT(*) AS anzahl FROM employee_availability')
        rest = cursor.fetchone()['anzahl']
    finally:
        connection.close()

    assert rest == 0


def test_fehlgeschlagene_migration_hinterlaesst_keine_spur_dank_impliziter_transaktion(pg_leere_migrationen):
    """_begin() ist auf Postgres bewusst ein No-op (siehe migrations.py) und
    verlaesst sich darauf, dass psycopg2 DDL und DML in derselben impliziten
    Transaktion haelt, sodass connection.rollback() nach einer
    fehlgeschlagenen zweiten Anweisung auch die erfolgreiche erste Anweisung
    derselben Migration zuruecknimmt. Genau diese unbewiesene Annahme wird
    hier gegen echtes Postgres geprueft.
    """
    migrations, verzeichnis, schema_url, schema = pg_leere_migrationen
    (verzeichnis / '0001_zwei_schritte.sql').write_text(
        'CREATE TABLE bleibt_nicht(id INTEGER PRIMARY KEY); '
        'DAS IST KEIN GUELTIGES SQL;',
        encoding='utf-8',
    )

    with pytest.raises(Exception):
        migrations.apply_pending()

    assert migrations.applied_versions() == []
    assert 'bleibt_nicht' not in tabellen(schema_url, schema)


def test_unique_index_scheitert_an_bereits_vorhandenen_doppelten_plaetzen(pg_leere_migrationen):
    """Deckt die Warnung im Kommentar von 0002_indexes.sql ab: legt der
    UNIQUE-Index ux_assignment_slot ueber Zeilen an, die denselben Platz
    (schedule_id, date, shift_type_id, slot_index) bereits doppelt belegen,
    muss CREATE UNIQUE INDEX IF NOT EXISTS fehlschlagen - und zwar so, dass
    die Migration danach nicht als angewandt gilt und der Index nicht
    existiert (siehe auch den Rollback-Test oben).
    """
    migrations, verzeichnis, schema_url, schema = pg_leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO schedules (year, month, status) VALUES (2026, 3, 'generated') RETURNING id")
            schedule_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00') "
                "RETURNING id")
            shift_type_id = cursor.fetchone()[0]
            for _ in range(2):
                cursor.execute(
                    'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
                    'VALUES (%s, %s, %s, 0)', (schedule_id, '2026-03-02', shift_type_id))
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')

    with pytest.raises(Exception):
        migrations.apply_pending()

    assert '0002_indexes' not in migrations.applied_versions()
    assert 'ux_assignment_slot' not in indizes(schema_url, schema)


def test_derselbe_platz_kann_nicht_doppelt_belegt_werden(pg_db):
    """Gegenstueck zum Test oben auf sauberen Daten: ohne bereits vorhandene
    Duplikate legt sich der Index normal an und verhindert danach denselben
    Fehler, den er oben schon bei Bestandsdaten verhindert haette.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO schedules (year, month, status) VALUES (2026, 3, 'generated') RETURNING id")
            schedule_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00') "
                "RETURNING id")
            shift_type_id = cursor.fetchone()[0]
            cursor.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
                'VALUES (%s, %s, %s, 0)', (schedule_id, '2026-03-02', shift_type_id))
        connection.commit()

        with pytest.raises(psycopg2.errors.UniqueViolation):
            with connection.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
                    'VALUES (%s, %s, %s, 0)', (schedule_id, '2026-03-02', shift_type_id))
    finally:
        connection.close()


def test_indexmigration_laesst_sich_zurueckrollen(pg_db):
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    while '0002_indexes' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'ix_assignments_date_employee' not in indizes(schema_url, schema)
    assert '0002_indexes' not in migrations.applied_versions()


def test_login_attempts_text_vergleich_funktioniert_wie_auf_sqlite(pg_db):
    """attempted_at ist bewusst TEXT, kein TIMESTAMP (siehe der Kommentar in
    0003_login_attempts.sql) - is_locked_out() in security.py vergleicht ihn
    als reinen ISO-String (attempted_at >= ?). Muss auf Postgres denselben
    lexikographischen Vergleich liefern wie auf SQLite.
    """
    migrations, schema_url, schema = pg_db
    migrations.apply_pending()

    import db
    import security

    connection = db.get_db_connection()
    try:
        cursor = connection.cursor()
        for _ in range(security.MAX_FAILED_ATTEMPTS):
            security.record_attempt(cursor, 'tester', '127.0.0.1', succeeded=False)
        connection.commit()
        assert security.is_locked_out(cursor, 'tester')

        security.record_attempt(cursor, 'tester', '127.0.0.1', succeeded=True)
        connection.commit()
        assert not security.is_locked_out(cursor, 'tester')
    finally:
        connection.close()


def test_information_schema_probe_erkennt_fehlende_spalte_und_ergaenzt_sie(pg_leere_migrationen):
    """table_columns() in db.py fragt information_schema.columns ab, um zu
    entscheiden, ob eine ALTER TABLE ADD COLUMN noch noetig ist (siehe
    0001_baseline.py). Auf einer wirklich frischen Datenbank hat die Tabelle
    die Spalte schon aus dem CREATE TABLE selbst - dieser Zweig laeuft dort
    nie wirklich. Dieser Test baut deshalb absichtlich den Bestandsfall nach:
    eine 'employees'-Tabelle wie vor Einfuehrung von Teilzeit, ohne
    weekly_hours/min_rest_hours.
    """
    migrations, verzeichnis, schema_url, schema = pg_leere_migrationen
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE employees(
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    max_shifts_per_month INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'employees'", (schema,))
            columns = {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()

    assert {'weekly_hours', 'min_rest_hours'} <= columns


def test_zwei_schemata_teilen_keine_daten(pg_db, monkeypatch):
    """Demonstriert die Isolation, auf die sich jeder andere Test in dieser
    Datei verlaesst, statt sie nur zu behaupten: zwei unabhaengig erzeugte
    Schemata auf derselben zugrunde liegenden Datenbank duerfen einander
    weder Tabellen noch Zeilen zeigen.
    """
    migrations, schema_url_a, schema_a = pg_db
    migrations.apply_pending()

    connection_a = psycopg2.connect(schema_url_a)
    try:
        with connection_a.cursor() as cursor:
            cursor.execute("INSERT INTO schedules (year, month, status) VALUES (2026, 5, 'draft')")
        connection_a.commit()
    finally:
        connection_a.close()

    base_url = resolve_test_database_url()
    with temporary_schema(base_url) as (schema_url_b, schema_b):
        assert schema_b != schema_a
        # Vor jeder Migration in Schema B: die Tabelle existiert dort noch gar nicht.
        assert 'schedules' not in tabellen(schema_url_b, schema_b)

        monkeypatch.setenv('DATABASE_URL', schema_url_b)
        migrations.apply_pending()
        assert 'schedules' in tabellen(schema_url_b, schema_b)

        connection_b = psycopg2.connect(schema_url_b)
        try:
            with connection_b.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM schedules')
                anzahl_b = cursor.fetchone()[0]
        finally:
            connection_b.close()
        # Schema A hat eine Zeile eingefuegt - Schema B darf sie nicht sehen.
        assert anzahl_b == 0

    connection_a = psycopg2.connect(schema_url_a)
    try:
        with connection_a.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM schedules')
            anzahl_a = cursor.fetchone()[0]
    finally:
        connection_a.close()
    # Und umgekehrt: was in Schema B passiert ist, hat Schema A unberuehrt gelassen.
    assert anzahl_a == 1


def test_table_columns_ist_schemaspezifisch_nicht_global(monkeypatch):
    """Postgres-spezifischer Fund: db.table_columns() fragt
    information_schema.columns nur nach table_name, ohne nach table_schema zu
    filtern (siehe db.py). Auf SQLite ist das folgenlos - eine Verbindung
    sieht ohnehin nur eine einzige Datei/Schema. Auf Postgres, wo mehrere
    Schemata in derselben Datenbank leben (wie in dieser Testsuite: ein
    Schema pro Test), mischt die fehlende Filterung Spalten unterschiedlicher
    gleichnamiger Tabellen zusammen, sobald zwei Schemata gleichzeitig
    existieren.

    Dieser Test legt zwei Schemata mit je einer eigenen, unterschiedlich
    breiten 'employees'-Tabelle an und fragt table_columns() fuer Schema A
    ab, waehrend Schema B noch existiert.
    """
    base_url = resolve_test_database_url()
    with temporary_schema(base_url) as (schema_url_a, schema_a), \
            temporary_schema(base_url) as (schema_url_b, schema_b):

        connection_b = psycopg2.connect(schema_url_b)
        try:
            with connection_b.cursor() as cursor:
                cursor.execute('CREATE TABLE employees(id SERIAL PRIMARY KEY, weekly_hours REAL)')
            connection_b.commit()
        finally:
            connection_b.close()

        connection_a = psycopg2.connect(schema_url_a)
        try:
            with connection_a.cursor() as cursor:
                cursor.execute('CREATE TABLE employees(id SERIAL PRIMARY KEY, name TEXT)')
            connection_a.commit()

            monkeypatch.setenv('DATABASE_URL', schema_url_a)
            sys.modules.pop('db', None)
            import db

            db_connection = db.get_db_connection()
            try:
                columns = db.table_columns(db_connection.cursor(), 'employees')
            finally:
                db_connection.close()
        finally:
            connection_a.close()

    assert columns == {'id', 'name'}, (
        f'table_columns() lieferte {columns} fuer Schema {schema_a} - erwartet nur '
        f"{{'id', 'name'}}. Vermutlich Spalten aus Schema {schema_b} mit hineingemischt, weil "
        'db.table_columns() information_schema.columns nicht nach table_schema filtert.'
    )


def test_advisory_lock_wird_gehalten_und_nach_freigabe_wieder_verfuegbar(pg_db):
    """Minimaler Beweis, dass der Advisory-Lock selbst tut, was er soll -
    unabhaengig vom Runner drumherum: eine zweite Sitzung darf denselben
    Schluessel nicht bekommen, waehrend eine erste ihn haelt, und muss ihn
    bekommen, sobald die erste ihn freigibt.

    Advisory-Locks sind datenbankweit, nicht schemaweit - die schema-scoped
    URL aus pg_db zeigt trotzdem auf dieselbe zugrunde liegende Datenbank wie
    jede andere Verbindung in dieser Testdatei, das Schema selbst spielt hier
    keine Rolle.
    """
    migrations, schema_url, _schema = pg_db
    schluessel = migrations._ADVISORY_LOCK_KEY

    haltende_verbindung = psycopg2.connect(schema_url)
    haltende_verbindung.autocommit = True
    pruef_verbindung = psycopg2.connect(schema_url)
    pruef_verbindung.autocommit = True
    try:
        with haltende_verbindung.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s)', (schluessel,))

        with pruef_verbindung.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', (schluessel,))
            assert cursor.fetchone()[0] is False, (
                'zweite Sitzung konnte denselben Advisory-Lock-Schluessel bekommen, '
                'obwohl die erste ihn noch haelt'
            )

        with haltende_verbindung.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', (schluessel,))

        with pruef_verbindung.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', (schluessel,))
            assert cursor.fetchone()[0] is True, (
                'zweite Sitzung bekam den Advisory-Lock-Schluessel nicht, '
                'obwohl die erste ihn zuvor freigegeben hat'
            )
            cursor.execute('SELECT pg_advisory_unlock(%s)', (schluessel,))
    finally:
        haltende_verbindung.close()
        pruef_verbindung.close()


def test_gleichzeitige_worker_wenden_dieselbe_migration_nicht_doppelt_an(pg_leere_migrationen):
    """Bildet die Race nach, die zum Advisory-Lock in _migration_lock() gefuehrt
    hat: zwei Gunicorn-Worker, die nach dem Forken beide app.py importieren
    und dabei beide apply_pending() gegen dieselbe Datenbank ausfuehren (siehe
    Modul-Docstring in migrations.py). Hier als zwei Threads mit je einer
    eigenen psycopg2-Verbindung nachgebaut - das ist naeher am echten
    Mehrprozess-Fall als an nebenlaeufigem Python-Code, weil jede Verbindung
    ihre eigene Postgres-Sitzung hat, genau wie zwei separate Worker-Prozesse.

    Damit die Race zuverlaessig eintritt statt nur gelegentlich (ein
    "hoffentlich gewinnt der Scheduler beide Threads gleichzeitig"-Test waere
    genau die Art von flakigem Test, die schlimmer ist als keiner): die
    Testmigration schlaeft 0.5s, bevor sie irgendetwas tut. Beide Threads
    starten binnen weniger Millisekunden - weit unter dieser Schlafzeit -,
    sodass ohne Lock garantiert beide schema_migrations lesen, bevor
    irgendeiner dort etwas eingetragen hat. Mit Lock blockiert der zweite
    Thread in pg_advisory_lock(), bis der erste committet und wieder
    freigegeben hat, und sieht die Migration danach schon als angewandt.
    """
    migrations, verzeichnis, _schema_url, _schema = pg_leere_migrationen
    (verzeichnis / '0001_race.py').write_text(
        "import time\n\n"
        "def up(cursor):\n"
        "    time.sleep(0.5)\n"
        "    cursor.execute('CREATE TABLE IF NOT EXISTS race_marker(id INTEGER PRIMARY KEY)')\n\n"
        "def down(cursor):\n"
        "    cursor.execute('DROP TABLE IF EXISTS race_marker')\n",
        encoding='utf-8',
    )

    fehler = []

    def worker():
        try:
            migrations.apply_pending()
        except Exception as exc:
            fehler.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not any(thread.is_alive() for thread in threads), (
        'mindestens ein Worker haengt noch fest - deutet auf einen Deadlock im Advisory-Lock hin'
    )
    assert fehler == [], (
        f'apply_pending() ist in mindestens einem Worker fehlgeschlagen: {fehler!r}. '
        'Ohne den Advisory-Lock waere das genau der IntegrityError aus dem UNIQUE-Verstoss '
        'auf schema_migrations.version, der beim Deploy den Gunicorn-Worker beim Boot toetet.'
    )
    assert migrations.applied_versions().count('0001_race') == 1
