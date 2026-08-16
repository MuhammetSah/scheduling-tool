"""Der Migrations-Runner.

Der Runner ist die Stelle, an der ein Fehler still Daten kostet, deshalb wird
er direkt getestet statt nur ueber die App.
"""

import sqlite3
from pathlib import Path

import pytest

BASELINE_PATH = Path(__file__).resolve().parent / 'migrations' / '0001_baseline.py'
INDEXES_SQL_PATH = Path(__file__).resolve().parent / 'migrations' / '0002_indexes.sql'
LOGIN_ATTEMPTS_SQL_PATH = Path(__file__).resolve().parent / 'migrations' / '0003_login_attempts.sql'
AVAILABILITY_SQL_PATH = Path(__file__).resolve().parent / 'migrations' / '0004_employee_availability.sql'

# Die von 0001_baseline.py angelegten Tabellen, als Literal statt aus der
# Datei abgeleitet. 0001_baseline aendert sich per Konvention nie wieder
# (siehe dessen eigenes down(), das eine Ruecknahme verweigert) - jede
# Aenderung an ihr waere also per Definition ein Fehler. Wuerde die Erwartung
# stattdessen per Regex aus genau der Datei gelesen, die hier ausgefuehrt und
# geprueft wird, wuerden eine geloeschte CREATE TABLE-Anweisung und die
# tatsaechlich entstandene Tabellenmenge gemeinsam schrumpfen - die Assertion
# unten bliebe dann bei jedem denkbaren Fehler gruen. Nicht wieder auf eine
# Ableitung aus der Datei umstellen, so verlockend "DRY" das wirkt.
BASELINE_TABELLEN = {
    'employees',
    'users',
    'password_invitations',
    'employee_unavailable_weekdays',
    'employee_unavailable_dates',
    'employee_absences',
    'shift_types',
    'shift_requirements',
    'employee_allowed_shift_types',
    'schedules',
    'shift_time_overrides',
    'shift_assignments',
}

# Alle Tabellen aus dem echten Migrationsordner (0001-0004), nicht nur aus
# der Baseline - ebenfalls von Hand gepflegtes Literal statt aus den
# Migrationsdateien abgeleitet, aus demselben Grund wie BASELINE_TABELLEN
# oben. Verwendet von test_alle_migrationen_erzeugen_genau_die_erwarteten_tabellen
# unten, dem Gegenstueck zu test_baseline_erzeugt_genau_die_erwarteten_tabellen...
# fuer den vollstaendigen, echten Migrationsordner statt nur fuer 0001_baseline
# isoliert.
ALLE_MIGRATIONEN_TABELLEN = BASELINE_TABELLEN | {'login_attempts', 'employee_availability'}


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    db_file = tmp_path / 'migrationen.db'
    monkeypatch.setenv('SCHICHTPLAN_DB_PATH', str(db_file))
    monkeypatch.delenv('DATABASE_URL', raising=False)

    import sys
    for module in ('db', 'migrations'):
        sys.modules.pop(module, None)

    import migrations
    return migrations, db_file


@pytest.fixture
def leere_migrationen(fresh_db, tmp_path, monkeypatch):
    """Isoliertes, leeres Migrationsverzeichnis fuer Tests, die eigene
    Migrationsdateien anlegen - ohne backend/migrations/0001_baseline.py
    permanent um eine Testdatei zu erweitern.
    """
    migrations, db_file = fresh_db
    verzeichnis = tmp_path / 'test_migrations'
    verzeichnis.mkdir()
    monkeypatch.setattr(migrations, 'MIGRATIONS_DIR', verzeichnis)
    return migrations, verzeichnis, db_file


def tabellen(db_file):
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def test_frische_datenbank_bekommt_alle_tabellen(fresh_db):
    migrations, db_file = fresh_db

    angewandt = migrations.apply_pending()

    assert '0001_baseline' in angewandt
    assert {'employees', 'users', 'shift_types', 'shift_assignments',
            'schedules', 'schema_migrations'} <= tabellen(db_file)


def test_alle_migrationen_erzeugen_genau_die_erwarteten_tabellen(fresh_db):
    """Gegenstueck zu test_baseline_erzeugt_genau_die_erwarteten_tabellen...
    unten, aber fuer den echten Migrationsordner (0001-0004) statt fuer
    0001_baseline isoliert: erschoepfend statt stichprobenartig, damit eine
    still entfernte oder vergessene Tabelle (z.B. employee_availability aus
    0004) durch jeden Test faellt, der nur eine Teilmenge abfragt.
    """
    migrations, db_file = fresh_db

    migrations.apply_pending()

    erwartet = ALLE_MIGRATIONEN_TABELLEN | {'schema_migrations', 'sqlite_sequence'}
    assert tabellen(db_file) == erwartet


def test_baseline_erzeugt_genau_die_erwarteten_tabellen_nicht_nur_eine_teilmenge(leere_migrationen):
    """0001_baseline aendert sich per Definition nie wieder (siehe dessen
    eigenes down(), das eine Ruecknahme verweigert) - gerade deshalb lohnt
    sich eine erschoepfende statt einer stichprobenartigen Pruefung: eine
    still entfernte Tabelle (z.B. employee_allowed_shift_types oder
    shift_time_overrides) faellt sonst durch jeden Test, der nur eine
    Teilmenge der Tabellen abfragt.

    Laeuft isoliert nur mit 0001_baseline (leere_migrationen), nicht mit dem
    echten Migrationsordner - 0002/0003 duerften sonst jede spaetere,
    voellig legitime neue Tabelle zu einem Fehlschlag hier machen.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')

    migrations.apply_pending()

    # schema_migrations legt der Runner selbst an (_ensure_version_table);
    # sqlite_sequence ist SQLite's eigene Buchfuehrung fuer die
    # AUTOINCREMENT-Spalten, die {auto_id} erzeugt - beides gehoert nicht zur
    # Tabellenliste der Migration selbst, taucht aber unvermeidlich mit auf.
    erwartet = BASELINE_TABELLEN | {'schema_migrations', 'sqlite_sequence'}
    assert tabellen(db_file) == erwartet


def test_zweiter_lauf_aendert_nichts(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.apply_pending() == []


def test_angewandte_versionen_werden_protokolliert(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.applied_versions() == sorted(migrations.applied_versions())
    assert '0001_baseline' in migrations.applied_versions()


def test_init_db_protokolliert_angewandte_migrationen(fresh_db, caplog):
    """Auf Renders Free-Plan gibt es keine Shell und damit kein migrations.py
    status - dieses Log ist dort die einzige Stelle, an der nach einem Deploy
    sichtbar wird, dass (und welche) Migration gerade lief.
    """
    migrations, _ = fresh_db
    import db as db_module

    with caplog.at_level('INFO', logger='db'):
        db_module.init_db()

    assert '0001_baseline' in caplog.text


def test_init_db_protokolliert_wenn_nichts_offen_ist(fresh_db, caplog):
    migrations, _ = fresh_db
    import db as db_module
    db_module.init_db()
    caplog.clear()

    with caplog.at_level('INFO', logger='db'):
        db_module.init_db()

    assert 'Keine Migrationen ausstehend' in caplog.text


def test_down_datei_ohne_up_skript_wird_nicht_still_als_angewandt_protokolliert(leere_migrationen):
    """available_versions() erkennt eine Version auch an einer .down.sql
    ohne zugehoeriges Up-Skript. Ohne die Pruefung in apply_pending() wuerde
    das als 'angewandt' protokolliert, obwohl nie etwas ausgefuehrt wurde -
    und jeder spaetere Lauf wuerde die Migration fuer immer ueberspringen.
    """
    migrations, verzeichnis, _ = leere_migrationen
    (verzeichnis / '0001_ohne_up.down.sql').write_text('SELECT 1', encoding='utf-8')

    with pytest.raises(RuntimeError):
        migrations.apply_pending()

    assert migrations.applied_versions() == []


def test_fehlgeschlagene_migration_wird_vollstaendig_zurueckgerollt(leere_migrationen):
    """Eine mehrschrittige SQL-Migration, deren zweite Anweisung ungueltig
    ist, darf keine Spur hinterlassen: weder die Wirkung der ersten,
    erfolgreichen Anweisung noch einen Eintrag in schema_migrations.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_zwei_schritte.sql').write_text(
        'CREATE TABLE bleibt_nicht(id INTEGER PRIMARY KEY); '
        'DAS IST KEIN GUELTIGES SQL;',
        encoding='utf-8',
    )

    with pytest.raises(Exception):
        migrations.apply_pending()

    assert migrations.applied_versions() == []
    assert 'bleibt_nicht' not in tabellen(db_file)


def test_migrationsdatei_mit_falschem_namen_wird_nicht_still_ignoriert(leere_migrationen):
    migrations, verzeichnis, _ = leere_migrationen
    (verzeichnis / '0002-falscher-trenner.sql').write_text('SELECT 1', encoding='utf-8')

    with pytest.raises(ValueError):
        migrations.available_versions()


def test_ruecknahme_ohne_migrationen_gibt_none(fresh_db):
    migrations, _ = fresh_db

    assert migrations.rollback_last() is None


def indizes(db_file):
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def test_indizes_werden_angelegt(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    assert {'ix_assignments_date_employee', 'ix_assignments_schedule',
            'ix_absences_date', 'ux_assignment_slot'} <= indizes(db_file)


def test_derselbe_platz_kann_nicht_doppelt_belegt_werden(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 3, 'generated')")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00')")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
            'VALUES (1, ?, 1, 0)', ('2026-03-02',))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
                'VALUES (1, ?, 1, 0)', ('2026-03-02',))
    finally:
        connection.close()


def test_indexmigration_laesst_sich_zurueckrollen(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    # Nicht auf "die letzte Migration" verlassen: spaetere Aufgaben haengen
    # weitere Migrationen hinten an, und dieser Test soll davon unberuehrt
    # bleiben. Stattdessen zurueckrollen, bis 0002 weg ist.
    while '0002_indexes' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'ix_assignments_date_employee' not in indizes(db_file)
    assert '0002_indexes' not in migrations.applied_versions()


def test_semikolon_in_kommentar_erzeugt_kein_leeres_sql_fragment(leere_migrationen):
    """Ein woertliches ; in einem -- Kommentar (wie urspruenglich in
    0002_indexes.sql) trennt die Datei wie jedes andere Semikolon. Das dabei
    entstehende Fragment enthaelt nur Kommentartext - auf Postgres waere das
    ein Fehler; siehe _has_sql() in migrations.py. Es darf nicht als eigene
    Anweisung an cursor.execute() gehen.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_kommentar_mit_semikolon.sql').write_text(
        '-- Beispielhinweis mit eingebautem Semikolon: siehe Dokumentation;\n'
        '-- und eine weitere Kommentarzeile danach.\n'
        'CREATE TABLE test_leeres_fragment(id INTEGER PRIMARY KEY)',
        encoding='utf-8',
    )

    statements = migrations._statements(verzeichnis / '0001_kommentar_mit_semikolon.sql')
    assert len(statements) == 1
    assert 'CREATE TABLE test_leeres_fragment' in statements[0]

    angewandt = migrations.apply_pending()

    assert '0001_kommentar_mit_semikolon' in angewandt
    assert '0001_kommentar_mit_semikolon' in migrations.applied_versions()
    assert 'test_leeres_fragment' in tabellen(db_file)


def test_availability_mode_hat_anytime_als_standard(leere_migrationen):
    """Bestandsdaten muessen unveraendert gueltig bleiben: eine Mitarbeiter-
    zeile, die schon VOR 0004 existierte, muss danach denselben Standard
    tragen wie ein neu eingefuegter Datensatz - nicht bloss ein Insert, das
    erst nach einer bereits vollstaendigen Migration passiert (das haette
    auch einen fehlenden DEFAULT nicht bemerkt, weil die Spalte dann schon
    da waere, bevor irgendetwas eingefuegt wird).

    Baut deshalb die echte Reihenfolge nach: erst 0001-0003 anwenden, dann
    die Zeile einfuegen, dann erst 0004 obendrauf - genau der Ablauf, den
    ein bestehendes Produktionsdeployment beim naechsten Start durchlaeuft.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0003_login_attempts.sql').write_text(
        LOGIN_ATTEMPTS_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0004_employee_availability.sql').write_text(
        AVAILABILITY_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        modus = connection.execute(
            "SELECT availability_mode FROM employees WHERE name = 'Anna'").fetchone()[0]
    finally:
        connection.close()

    assert modus == 'anytime'


def test_fenster_werden_beim_loeschen_des_mitarbeiters_mitgeloescht(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.execute(
            'INSERT INTO employee_availability (employee_id, weekday, start_time, end_time) '
            'VALUES (1, 0, ?, ?)', ('08:00', '14:00'))
        connection.commit()
        connection.execute('DELETE FROM employees WHERE id = 1')
        connection.commit()
        rest = connection.execute('SELECT COUNT(*) FROM employee_availability').fetchone()[0]
    finally:
        connection.close()

    assert rest == 0
