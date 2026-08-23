"""Der Bestandsweg: eine gefuellte Datenbank vom Stand 0007 auf 0017 heben.

Der Weg auf eine LEERE Datenbank ist gut abgesichert - genau den faehrt der
backend-postgres-Job bei jedem Lauf. Ungeprueft war der andere: das Backup vom
22.08.2026 steht auf schema_migrations mit sieben Zeilen, also auf dem Stand
von 0007, und wer es zurueckspielt, laesst zehn Migrationen ueber echte Daten
laufen. Darunter der Tabellenneubau in 0012, das DROP in 0010 und die
Zustandsumstellung, die vorhandene Plaene anfasst.

Genau dieser Pfad zaehlt am 07.09.2026, wenn die Instanz ablaeuft und der
Bestand doch gebraucht wird.

**Nachgebaute Daten, nicht das echte Backup.** Der Dump enthaelt drei Namen und
zweiundsechzig Schichten im Klartext; er gehoert weder ins Repository noch in
einen CI-Lauf. Was hier steht, hat dieselbe Form - Mitarbeiter mit
Einschraenkungen, Schichtarten mit Bedarfszahlen, Zuweisungen, ein erzeugter
Plan - und laeuft durch dieselben Migrationen.

Der Aufbau folgt dem echten Verlauf: 0001-0006 anwenden, Daten einspielen, dann
0007 (das den Bedarf aus shift_requirements ableitet), und erst danach den Rest.
Ein Bestand, der schon abgeleitete Baender mitbraechte, pruefte die Ableitung
nicht mit.
"""

import shutil
import sys
from pathlib import Path

import psycopg2
import pytest

from pg_testsupport import resolve_test_database_url, temporary_schema

pytestmark = pytest.mark.skipif(
    not resolve_test_database_url(),
    reason='TEST_DATABASE_URL nicht gesetzt - Postgres-Tests uebersprungen (siehe pg_testsupport.py)',
)

MIGRATIONS = Path(__file__).resolve().parent / 'migrations'
BIS_0007 = ('0001_baseline.py', '0002_indexes.sql', '0002_indexes.down.sql',
            '0003_login_attempts.sql', '0003_login_attempts.down.sql',
            '0004_employee_availability.py', '0005_assignment_times.py',
            '0006_coverage.py', '0007_derive_coverage.py')


@pytest.fixture
def pg_bestand(monkeypatch, tmp_path):
    """Ein frisches Schema, in dem nur 0001-0006 angewandt sind.

    Ueber ein Verzeichnis mit den fraglichen Dateien statt ueber einen
    "bis Version X"-Schalter im Runner: der Runner soll keine Sonderwege fuer
    Tests bekommen, und das Kopieren bildet genau das ab, was ein
    Bestandssystem von damals hatte - die spaeteren Migrationen gab es dort
    schlicht nicht.
    """
    base_url = resolve_test_database_url()
    with temporary_schema(base_url) as (schema_url, schema):
        monkeypatch.setenv('DATABASE_URL', schema_url)
        monkeypatch.delenv('SCHICHTPLAN_DB_PATH', raising=False)
        for modul in ('db', 'migrations'):
            sys.modules.pop(modul, None)

        alt = tmp_path / 'stand_2026_08'
        alt.mkdir()
        for name in BIS_0007:
            if name.startswith('0007'):
                continue
            shutil.copy(MIGRATIONS / name, alt / name)

        import migrations
        monkeypatch.setattr(migrations, 'MIGRATIONS_DIR', alt)
        migrations.apply_pending()

        yield migrations, alt, schema_url, schema


def _bestand_einspielen(schema_url):
    """Daten in der Form, die der Dump vom 22.08. hat - nur mit erfundenen Namen."""
    connection = psycopg2.connect(schema_url)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO employees (name, email, active, max_shifts_per_month, "
                "weekly_hours, min_rest_hours, availability_mode) VALUES "
                "('A', 'a@example.invalid', 1, 20, 30, 11, 'anytime'), "
                "('B', 'b@example.invalid', 1, NULL, NULL, 11, 'anytime'), "
                "('C', 'c@example.invalid', 0, NULL, NULL, 11, 'anytime')")
            cursor.execute(
                "INSERT INTO shift_types (name, start_time, end_time, color) VALUES "
                "('Frueh', '06:00', '14:00', '#3366cc'), "
                "('Spaet', '14:00', '22:00', '#cc6633')")
            cursor.execute('SELECT id FROM shift_types ORDER BY id')
            arten = [r[0] for r in cursor.fetchall()]
            # Genau die Quelle, aus der 0007 die Baender ableitet.
            for art in arten:
                for weekday in range(7):
                    cursor.execute(
                        'INSERT INTO shift_requirements (shift_type_id, weekday, required_count) '
                        'VALUES (%s, %s, %s)', (art, weekday, 1 if weekday < 5 else 0))

            cursor.execute("INSERT INTO schedules (year, month, status) "
                           "VALUES (2026, 8, 'generated')")
            cursor.execute('SELECT id FROM schedules')
            plan = cursor.fetchone()[0]
            cursor.execute('SELECT id FROM employees ORDER BY id')
            leute = [r[0] for r in cursor.fetchall()]
            for tag in range(1, 21):
                cursor.execute(
                    'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, '
                    'slot_index, employee_id) VALUES (%s, %s, %s, 0, %s)',
                    (plan, '2026-08-%02d' % tag, arten[tag % 2], leute[tag % 2]))

            cursor.execute(
                'INSERT INTO employee_unavailable_weekdays (employee_id, weekday) '
                'VALUES (%s, 6)', (leute[0],))
    finally:
        connection.close()


def _zaehle(schema_url, sql, params=()):
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()[0]
    finally:
        connection.close()


def _spalten(schema_url, schema, tabelle):
    connection = psycopg2.connect(schema_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_schema = %s AND table_name = %s', (schema, tabelle))
            return {r[0] for r in cursor.fetchall()}
    finally:
        connection.close()


@pytest.fixture
def gehobener_bestand(pg_bestand):
    """Der Bestand nach 0007, danach auf den heutigen Stand gehoben."""
    migrations, alt, schema_url, schema = pg_bestand
    _bestand_einspielen(schema_url)

    # 0007 leitet die Baender aus shift_requirements ab - deshalb erst jetzt.
    shutil.copy(MIGRATIONS / '0007_derive_coverage.py', alt / '0007_derive_coverage.py')
    migrations.apply_pending()
    assert migrations.applied_versions()[-1] == '0007_derive_coverage'

    migrations.MIGRATIONS_DIR = MIGRATIONS
    neu = migrations.apply_pending()
    return migrations, schema_url, schema, neu


# ---------- Der Sprung selbst ----------


def test_der_sprung_von_0007_auf_heute_laeuft_durch(gehobener_bestand):
    """Der Kern: zehn Migrationen ueber gefuellte Tabellen, ohne Fehler."""
    migrations, _schema_url, _schema, neu = gehobener_bestand

    assert '0008_max_daily_hours' in neu
    assert '0017_qualifications' in neu
    assert migrations.applied_versions()[-1] == '0017_qualifications'


def test_kein_mitarbeiter_geht_verloren(gehobener_bestand):
    """Die Gegenprobe, die zaehlt: ein Sprung, der durchlaeuft und dabei
    Zeilen verliert, waere schlimmer als einer, der abbricht."""
    _migrations, schema_url, _schema, _neu = gehobener_bestand

    assert _zaehle(schema_url, 'SELECT COUNT(*) FROM employees') == 3
    assert _zaehle(schema_url, 'SELECT COUNT(*) FROM shift_assignments') == 20
    assert _zaehle(schema_url, 'SELECT COUNT(*) FROM employee_unavailable_weekdays') == 1


def test_die_abgeleiteten_baender_ueberleben_das_drop_in_0010(gehobener_bestand):
    """0010 wirft shift_requirements weg. Inhaltlich lebt der Bedarf in
    coverage_requirements weiter - wenn 0007 ihn vorher wirklich abgeleitet hat
    und 0010 ihn nicht mitnimmt.

    Fuenf Baender, nicht vierzehn: coverage_curve() verschmilzt die
    Fruehschicht 06:00-14:00 und die Spaetschicht 14:00-22:00 zu einem
    durchgehenden Band 06:00-22:00 mit Bedarf 1, und die Wochenendzeilen mit
    Bedarf 0 ergeben gar nichts. Genau das ist der Punkt der Ableitung -
    nachgerechnet mit coverage_curve() statt geraten.
    """
    _migrations, schema_url, schema, _neu = gehobener_bestand

    assert _zaehle(schema_url, 'SELECT COUNT(*) FROM coverage_requirements') == 5
    assert _zaehle(
        schema_url,
        "SELECT COUNT(*) FROM coverage_requirements "
        "WHERE start_time = '06:00' AND end_time = '22:00' AND required_count = 1") == 5
    # table_columns() liefert fuer eine fehlende Tabelle eine leere Menge.
    assert _spalten(schema_url, schema, 'shift_requirements') == set()


# ---------- Was die einzelnen Migrationen am Bestand tun ----------


def test_0008_gibt_jedem_bestand_eine_tagesgrenze(gehobener_bestand):
    """NOT NULL DEFAULT 10 auf einer gefuellten Tabelle: die vorhandenen
    Zeilen muessen den Vorgabewert bekommen, nicht NULL."""
    _migrations, schema_url, _schema, _neu = gehobener_bestand

    assert _zaehle(schema_url,
                   'SELECT COUNT(*) FROM employees WHERE max_daily_hours = 10') == 3
    assert _zaehle(schema_url,
                   'SELECT COUNT(*) FROM employees WHERE max_daily_hours IS NULL') == 0


def test_0012_macht_aus_erzeugten_plaenen_veroeffentlichte(gehobener_bestand):
    """Der Bestand kannte nur 'generated'. Bliebe ein Plan darauf stehen,
    faende ihn nach der Umstellung weder der Entwurfs- noch der
    Veroeffentlichungspfad - er waere unsichtbar.
    """
    _migrations, schema_url, _schema, _neu = gehobener_bestand

    assert _zaehle(schema_url,
                   "SELECT COUNT(*) FROM schedules WHERE status = 'published'") == 1
    assert _zaehle(schema_url,
                   'SELECT COUNT(*) FROM schedules WHERE published_at IS NULL') == 0
    assert _zaehle(schema_url,
                   "SELECT COUNT(*) FROM schedules WHERE status = 'generated'") == 0


def test_die_neuen_spalten_stehen_und_sind_leer(gehobener_bestand):
    """0009, 0014 und 0016 haengen NULL-bare Spalten an. Ein Vorgabewert waere
    hier eine Behauptung ueber Bestand, den niemand geprueft hat."""
    _migrations, schema_url, schema, _neu = gehobener_bestand

    zuweisung = _spalten(schema_url, schema, 'shift_assignments')
    assert {'break_minutes', 'break_start'} <= zuweisung
    assert 'anonymized_at' in _spalten(schema_url, schema, 'employees')

    assert _zaehle(schema_url,
                   'SELECT COUNT(*) FROM shift_assignments WHERE break_minutes IS NOT NULL') == 0
    assert _zaehle(schema_url,
                   'SELECT COUNT(*) FROM employees WHERE anonymized_at IS NOT NULL') == 0


def test_die_neuen_tabellen_stehen_leer_daneben(gehobener_bestand):
    """0011, 0013, 0015 und 0017 legen Tabellen an. Auf einem Bestand duerfen
    sie leer sein - und vorhanden."""
    _migrations, schema_url, _schema, _neu = gehobener_bestand

    for tabelle in ('settings', 'audit_log', 'shift_swap_requests',
                    'qualifications', 'employee_qualifications',
                    'shift_type_qualifications'):
        assert _zaehle(schema_url, 'SELECT COUNT(*) FROM ' + tabelle) == 0


# ---------- Und danach laeuft die Anwendung darauf ----------


def test_die_anwendung_liest_den_gehobenen_bestand(gehobener_bestand):
    """Migrationen, die durchlaufen, sind die halbe Antwort.

    Die andere ist, ob die heutige Anwendung mit dem gehobenen Bestand
    zurechtkommt - serialize_employee() liest inzwischen Spalten und Tabellen,
    die es am 22.08. nicht gab.
    """
    _migrations, _schema_url, _schema, _neu = gehobener_bestand

    for modul in ('db', 'app'):
        sys.modules.pop(modul, None)
    import app as anwendung

    anwendung.app.config['TESTING'] = True
    client = anwendung.app.test_client()
    client.post('/register', json={'username': 'hr', 'password': 'passwort-123',
                                   'role': 'hr'})

    leute = client.get('/employees')
    assert leute.status_code == 200, leute.json
    # Alle drei: die Liste blendet Grabsteine aus (anonymized_at), nicht
    # Inaktive - eine inaktive Person bleibt sichtbar und bearbeitbar.
    assert len(leute.json) == 3
    assert all('qualifications' in person for person in leute.json)

    plan = client.get('/schedules/2026/8')
    assert plan.status_code == 200, plan.json
    assert len(plan.json['assignments']) == 20
