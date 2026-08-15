"""Der Migrations-Runner.

Der Runner ist die Stelle, an der ein Fehler still Daten kostet, deshalb wird
er direkt getestet statt nur ueber die App.
"""

import sqlite3

import pytest


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


def test_zweiter_lauf_aendert_nichts(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.apply_pending() == []


def test_angewandte_versionen_werden_protokolliert(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.applied_versions() == sorted(migrations.applied_versions())
    assert '0001_baseline' in migrations.applied_versions()


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
