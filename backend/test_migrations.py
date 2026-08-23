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
AVAILABILITY_PY_PATH = Path(__file__).resolve().parent / 'migrations' / '0004_employee_availability.py'
ASSIGNMENT_TIMES_PY_PATH = Path(__file__).resolve().parent / 'migrations' / '0005_assignment_times.py'
COVERAGE_PY_PATH = Path(__file__).resolve().parent / 'migrations' / '0006_coverage.py'
DERIVE_COVERAGE_PY_PATH = Path(__file__).resolve().parent / 'migrations' / '0007_derive_coverage.py'


def zurueck_bis(migrations, version):
    """Rollt zurueck, bis `version` an der Reihe war.

    Nicht rollback_last() einmal aufrufen: "die letzte ist meine" ist eine
    Annahme, die jede kuenftige Migration erneut bricht. Genau daran sind die
    Rundlauftests von 0007 und 0008 nacheinander gescheitert, als 0008 bzw.
    0009 dazukamen.
    """
    while True:
        zurueckgerollt = migrations.rollback_last()
        assert zurueckgerollt is not None, f'ohne {version} zurueckgerollt'
        if zurueckgerollt == version:
            return zurueckgerollt

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
ALLE_MIGRATIONEN_TABELLEN = (BASELINE_TABELLEN | {
    'login_attempts', 'employee_availability',
    'business_hours', 'business_hours_exceptions', 'coverage_requirements',
    'settings',
    'audit_log',
    'shift_swap_requests',
}) - {
    # 0010 entfernt sie wieder. Nach 0001 gibt es sie, am Ende nicht mehr -
    # deshalb steht sie oben in BASELINE_TABELLEN und hier in der Gegenmenge,
    # von Hand wie alles in dieser Liste (Fallstrick 5).
    'shift_requirements',
}


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
    """ux_assignment_slot_v2 statt ux_assignment_slot: 0005_assignment_times
    ersetzt den alten Index (siehe dort) - nach einem vollstaendigen Lauf
    aller Migrationen existiert nur noch die neue Form.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    assert {'ix_assignments_date_employee', 'ix_assignments_schedule',
            'ix_absences_date', 'ux_assignment_slot_v2'} <= indizes(db_file)


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

    (verzeichnis / '0004_employee_availability.py').write_text(
        AVAILABILITY_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        modus = connection.execute(
            "SELECT availability_mode FROM employees WHERE name = 'Anna'").fetchone()[0]
    finally:
        connection.close()

    assert modus == 'anytime'


def spalten(db_file, tabelle):
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute(f'PRAGMA table_info({tabelle})').fetchall()
    finally:
        connection.close()
    return {row[1] for row in rows}


def test_fenstermigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(fresh_db):
    """Der Rundlauf up -> down -> up, nicht nur die Ruecknahme allein.

    down() entfernt employees.availability_mode bewusst nicht (SQLite kennt
    DROP COLUMN erst ab 3.35 und auch dann nicht ueberall; die Begruendung
    steht in 0004_employee_availability.py). Genau deshalb muss der zweite
    Vorwaertslauf die Spalte vorfinden duerfen: mit einem blanken
    ALTER TABLE ADD COLUMN scheitert er hier an "duplicate column name" - und
    weil app.py init_db() beim Modulimport aufruft, waere das eine Anwendung,
    die nach einem einzigen "migrations.py down" gar nicht mehr startet.

    Vorbild fuer den Aufbau ist test_indexmigration_laesst_sich_zurueckrollen
    oben: nicht auf "die letzte Migration" verlassen, sondern zurueckrollen,
    bis 0004 weg ist.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    while '0004_employee_availability' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'employee_availability' not in tabellen(db_file)
    # Die Spalte ueberlebt die Ruecknahme - das ist die bewusste Entscheidung,
    # nicht der Fehler.
    assert 'availability_mode' in spalten(db_file, 'employees')

    erneut = migrations.apply_pending()

    assert '0004_employee_availability' in erneut
    assert 'employee_availability' in tabellen(db_file)
    assert 'availability_mode' in spalten(db_file, 'employees')


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


def test_zuweisung_hat_eigene_zeitspalten(fresh_db):
    """Individuelle Zeiten pro Zuweisung, beide NULL-bar."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {r[1]: r for r in connection.execute('PRAGMA table_info(shift_assignments)')}
    finally:
        connection.close()

    assert 'start_time' in spalten
    assert 'end_time' in spalten
    # notnull ist Feld 3 der PRAGMA-Zeile: 0 heisst NULL erlaubt.
    assert spalten['start_time'][3] == 0
    assert spalten['end_time'][3] == 0


def test_schichtart_ist_jetzt_optional(fresh_db):
    """Ein Block ohne Vorlage muss speicherbar sein - die Voraussetzung fuer Etappe 4."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO schedules (year, month) VALUES (2026, 3)")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, start_time, end_time) '
            "VALUES (1, '2026-03-17', NULL, 0, '10:00', '16:00')")
        connection.commit()
        zeile = connection.execute(
            'SELECT shift_type_id, start_time FROM shift_assignments').fetchone()
    finally:
        connection.close()

    assert zeile[0] is None
    assert zeile[1] == '10:00'


def test_bestandszuweisungen_ueberleben_den_tabellenneubau(leere_migrationen):
    """Der SQLite-Pfad baut die Tabelle neu - die vorhandenen Zeilen muessen das ueberstehen.

    migrations.apply_one(version) gibt es nicht - der Runner bietet nur
    applied_versions()/apply_pending()/rollback_last() (siehe migrations.py).
    Die Staffelung laeuft deshalb wie in
    test_availability_mode_hat_anytime_als_standard oben ueber ein isoliertes
    Migrationsverzeichnis, das erst bis 0004 befuellt wird: 0001-0004 werden
    hineinkopiert und angewandt, DANN wird eingefuegt, und erst danach kommt
    0005 dazu. Andersherum wuerde der Test nur belegen, dass ein frischer
    Insert nach einer bereits vollstaendigen Migration funktioniert - genau
    der Fehler, der in Etappe 1 gefunden wurde.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0003_login_attempts.sql').write_text(
        LOGIN_ATTEMPTS_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0004_employee_availability.py').write_text(
        AVAILABILITY_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO schedules (year, month) VALUES (2026, 3)")
        connection.execute("INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00')")
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited) '
            "VALUES (1, '2026-03-17', 1, 0, 1, 1)")
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0005_assignment_times.py').write_text(
        ASSIGNMENT_TIMES_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        zeile = connection.execute(
            'SELECT schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited, '
            'start_time, end_time FROM shift_assignments').fetchone()
    finally:
        connection.close()

    assert zeile == (1, '2026-03-17', 1, 0, 1, 1, None, None)


def test_fremdschluessel_ueberleben_den_tabellenneubau(fresh_db):
    """Der SQLite-Neubau in 0005_assignment_times.py schreibt die
    REFERENCES-Klauseln der neuen Tabelle von Hand aus - ein dabei verlorenes
    oder vertauschtes ON DELETE waere sonst nur durch Handpruefung auffindbar.
    PRAGMA foreign_keys ist bei einer blanken sqlite3.connect()-Verbindung per
    Default AUS (siehe test_fenster_werden_beim_loeschen_des_mitarbeiters_
    mitgeloescht oben) - ohne es hier explizit einzuschalten, loest keine der
    beiden Aktionen unten aus und der Test waere grundlos gruen.

    Zwei Verhalten: schedules -> shift_assignments ist CASCADE (der Plan
    reisst seine Zuweisungen mit), employees -> shift_assignments ist
    SET NULL, und zwar auf beiden Spalten, die auf employees zeigen
    (employee_id und absent_employee_id).
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute("INSERT INTO schedules (year, month) VALUES (2026, 3)")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00')")
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.execute("INSERT INTO employees (name) VALUES ('Berta')")
        connection.execute(
            'INSERT INTO shift_assignments '
            '(schedule_id, date, shift_type_id, slot_index, employee_id, absent_employee_id) '
            "VALUES (1, '2026-03-17', 1, 0, 1, 2)")
        connection.commit()

        connection.execute('DELETE FROM employees WHERE id IN (1, 2)')
        connection.commit()
        zeile = connection.execute(
            'SELECT employee_id, absent_employee_id FROM shift_assignments').fetchone()
        assert zeile == (None, None), (
            f'employee_id/absent_employee_id nach DELETE FROM employees: {zeile!r} - '
            'erwartet (None, None) durch ON DELETE SET NULL')

        connection.execute('DELETE FROM schedules WHERE id = 1')
        connection.commit()
        rest = connection.execute('SELECT COUNT(*) FROM shift_assignments').fetchone()[0]
    finally:
        connection.close()

    assert rest == 0


def test_indizes_ueberleben_den_tabellenneubau(fresh_db):
    """DROP TABLE nimmt die Indizes mit - sie muessen danach wieder da sein."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        namen = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'shift_assignments'")}
    finally:
        connection.close()

    assert 'ix_assignments_date_employee' in namen
    assert 'ix_assignments_schedule' in namen
    assert 'ux_assignment_slot_v2' in namen


def test_eindeutigkeit_greift_auch_ohne_schichtart(fresh_db):
    """Ohne COALESCE waeren zwei freie Bloecke auf demselben Platz erlaubt."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO schedules (year, month) VALUES (2026, 3)")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, start_time, end_time) '
            "VALUES (1, '2026-03-17', NULL, 0, '10:00', '16:00')")
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, start_time, end_time) '
                "VALUES (1, '2026-03-17', NULL, 0, '11:00', '17:00')")
            connection.commit()
    finally:
        connection.close()


def test_zeitmigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(fresh_db):
    """Rueckwaerts allein reicht nicht - die Migration muss danach wieder vorwaerts laufen.

    Mit einer Bestandszeile zwischen Ruecknahme und zweitem Vorwaertslauf,
    nicht auf einer leeren Datenbank: der SQLite-Zweig von up() ist ein
    Tabellenneubau (CREATE shift_assignments_neu, INSERT INTO ... SELECT,
    DROP, RENAME) - auf einer leeren Tabelle liefe das auch dann klaglos
    durch, wenn die Kopie eine Spalte verlieren wuerde. Nur eine echte Zeile
    zeigt, dass der zweite Durchlauf des Neubaus die Daten tatsaechlich
    unversehrt durchreicht.

    Vorbild: test_fenstermigration_... aus Etappe 1, entstanden aus dem Critical
    des dortigen Abschluss-Reviews.

    Nicht auf "die letzte Migration" verlassen (wie test_indexmigration_ und
    test_fenstermigration_ oben): spaetere Aufgaben haengen weitere
    Migrationen hinten an - inzwischen 0006_coverage -, und rollback_last()
    ohne Schleife wuerde dann die falsche Migration zurueckrollen.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    assert '0005_assignment_times' in migrations.applied_versions()

    while '0005_assignment_times' in migrations.applied_versions():
        migrations.rollback_last()
    assert '0005_assignment_times' not in migrations.applied_versions()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO schedules (year, month) VALUES (2026, 3)")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00')")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
            "VALUES (1, '2026-03-17', 1, 0)")
        connection.commit()
    finally:
        connection.close()

    migrations.apply_pending()
    assert '0005_assignment_times' in migrations.applied_versions()

    connection = sqlite3.connect(db_file)
    try:
        zeile = connection.execute(
            'SELECT schedule_id, date, shift_type_id, slot_index, start_time, end_time '
            'FROM shift_assignments').fetchone()
    finally:
        connection.close()

    assert zeile == (1, '2026-03-17', 1, 0, None, None)


def test_oeffnungszeiten_starten_rund_um_die_uhr_offen(fresh_db):
    """Der Standard darf kein bestehendes Verhalten aendern.

    Vor dieser Etappe gibt es keine Oeffnungszeiten, also darf ihre Einfuehrung
    nichts verbieten, was vorher erlaubt war. 00:00-00:00 ist nach der
    Mitternachtskonvention des Projekts der ganze Tag.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        zeilen = connection.execute(
            'SELECT weekday, open_time, close_time, closed FROM business_hours ORDER BY weekday'
        ).fetchall()
    finally:
        connection.close()

    assert zeilen == [(wd, '00:00', '00:00', 0) for wd in range(7)]


def test_genau_eine_oeffnungszeit_pro_wochentag(fresh_db):
    """UNIQUE(weekday) - ein zweiter Montag waere ein Datenfehler."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO business_hours (weekday, open_time, close_time, closed) "
                "VALUES (0, '08:00', '18:00', 0)")
            connection.commit()
    finally:
        connection.close()


def test_ausnahme_ist_pro_datum_eindeutig(fresh_db):
    """UNIQUE(date) - zwei Sonderregeln fuer denselben Tag waeren mehrdeutig."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute(
            "INSERT INTO business_hours_exceptions (date, open_time, close_time, closed, label) "
            "VALUES ('2026-12-24', '08:00', '14:00', 0, 'Heiligabend')")
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO business_hours_exceptions (date, open_time, close_time, closed, label) "
                "VALUES ('2026-12-24', '09:00', '13:00', 0, 'Zweite Regel fuer denselben Tag')")
            connection.commit()
    finally:
        connection.close()


def test_bedarfsbaender_starten_leer(fresh_db):
    """Task 1 legt nur die Tabelle an, ohne Bedarf abzuleiten - das war die
    Abgrenzung zwischen Task 1 und Task 3.

    Seit Task 3 (0007_derive_coverage.py) existiert die Ableitung, aber
    fresh_db hat nach der Baseline-Migration keine Schichtarten - und ohne
    Schichtarten leitet 0007 nichts ab (siehe deren eigener Waechter). Der
    Test bleibt deshalb bewusst unveraendert gueltig; die eigentliche Probe
    auf die Ableitung selbst steht in
    test_bedarf_wird_aus_den_schichtarten_abgeleitet weiter unten, und die
    Probe auf "keine Schichtarten -> kein Bedarf" nochmal explizit in
    test_ableitung_ohne_schichtarten_erzeugt_nichts.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        anzahl = connection.execute('SELECT COUNT(*) FROM coverage_requirements').fetchone()[0]
    finally:
        connection.close()

    assert anzahl == 0


def test_bedarf_wird_aus_den_schichtarten_abgeleitet(leere_migrationen):
    """Der eigentliche Beweis dieser Migration: dieselbe Kurve wie vorher.

    Aufbau bewusst mit ZWEI Schichtarten an DEMSELBEN Wochentag, die sich
    ueberlappen - nur so zeigt sich, ob summiert wird. Zwei sich nicht
    beruehrende Schichtarten wuerden auch bei einer falschen Implementierung
    zufaellig richtig herauskommen.

    Staffelung: bis 0006 migrieren, DANN Schichtarten und Bedarf einfuegen,
    DANN 0007 nachschieben. Andersherum prueft der Test nichts - dasselbe
    Muster wie test_bestandszuweisungen_ueberleben_den_tabellenneubau oben,
    das isolierte Migrationsverzeichnis kommt von der leere_migrationen-Fixture.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0003_login_attempts.sql').write_text(
        LOGIN_ATTEMPTS_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0004_employee_availability.py').write_text(
        AVAILABILITY_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0005_assignment_times.py').write_text(
        ASSIGNMENT_TIMES_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0006_coverage.py').write_text(COVERAGE_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        # Frueh und Mittag ueberlappen sich montags (weekday=0) von 12:00 bis
        # 14:00 - genau dieses Stueck muss in der abgeleiteten Kurve die Summe
        # beider required_count tragen (2+3=5), nicht nur eine der beiden.
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '08:00', '14:00')")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Mittag', '12:00', '17:00')")
        connection.execute(
            'INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (1, 0, 2)')
        connection.execute(
            'INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (2, 0, 3)')
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0007_derive_coverage.py').write_text(
        DERIVE_COVERAGE_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    angewandt = migrations.apply_pending()
    assert '0007_derive_coverage' in angewandt

    connection = sqlite3.connect(db_file)
    try:
        baender = connection.execute(
            'SELECT weekday, start_time, end_time, required_count FROM coverage_requirements '
            'ORDER BY weekday, start_time'
        ).fetchall()
    finally:
        connection.close()

    assert baender == [
        (0, '08:00', '12:00', 2),
        (0, '12:00', '14:00', 5),
        (0, '14:00', '17:00', 3),
    ]


def test_ableitung_laesst_bestehende_baender_unangetastet(fresh_db):
    """Wer schon Baender gepflegt hat, verliert sie nicht.

    Die Migration darf nur ableiten, wenn coverage_requirements leer ist.
    Sonst wuerde ein zweiter Lauf - etwa nach einem Rollback - von Hand
    gepflegte Baender ueberschreiben.

    Diskriminierend nur, weil ausser dem handgepflegten Band auch echte
    Schichtdaten fuer denselben Wochentag vorliegen: faellt der Waechter aus,
    wuerde der zweite up()-Lauf eine zusaetzliche, abgeleitete Zeile daneben
    einfuegen, und die Zeilenmenge unten stimmt nicht mehr.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    assert '0007_derive_coverage' in migrations.applied_versions()

    # Erst zurueckrollen, dann die Testdaten anlegen. Seit 0010 gibt es
    # shift_requirements am Ende der Migrationskette nicht mehr - und die
    # Aussage dieses Tests ist ohnehin "Altbestand liegt vor, WENN 0007
    # laeuft", also gehoeren die Daten an genau diese Stelle.
    zurueck_bis(migrations, '0007_derive_coverage')

    connection = sqlite3.connect(db_file)
    try:
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '08:00', '14:00')")
        connection.execute(
            'INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (1, 0, 2)')
        connection.commit()
    finally:
        connection.close()
    assert '0007_derive_coverage' not in migrations.applied_versions()

    connection = sqlite3.connect(db_file)
    try:
        # Handgepflegtes Band, bewusst anders als das, was aus den
        # Schichtdaten oben abgeleitet wuerde (08:00-14:00 mit 2).
        connection.execute(
            "INSERT INTO coverage_requirements (weekday, start_time, end_time, required_count) "
            "VALUES (0, '00:00', '23:59', 1)")
        connection.commit()
    finally:
        connection.close()

    erneut = migrations.apply_pending()
    assert '0007_derive_coverage' in erneut

    connection = sqlite3.connect(db_file)
    try:
        baender = connection.execute(
            'SELECT weekday, start_time, end_time, required_count FROM coverage_requirements'
        ).fetchall()
    finally:
        connection.close()

    assert baender == [(0, '00:00', '23:59', 1)]


def test_ableitung_ohne_schichtarten_erzeugt_nichts(fresh_db):
    """Eine frische Installation hat keine Schichtarten - und danach keinen Bedarf."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        schichtarten = connection.execute('SELECT COUNT(*) FROM shift_types').fetchone()[0]
        baender = connection.execute('SELECT COUNT(*) FROM coverage_requirements').fetchone()[0]
    finally:
        connection.close()

    assert schichtarten == 0
    assert baender == 0


def test_ableitungsmigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(leere_migrationen):
    """Rundlauf up -> down -> up: nach der Ruecknahme entsteht dieselbe Kurve erneut.

    Staffelung wie test_bedarf_wird_aus_den_schichtarten_abgeleitet: erst bis
    0006 migrieren, dann Schichtarten und Bedarf einfuegen, dann 0007
    nachschieben - sonst liefe der erste Vorwaertslauf schon auf leerem
    Bestand, und der Rundlauf wuerde nichts pruefen (Pflicht laut Vorgabe:
    Rundlauf mit Bestandsdaten, nicht auf leerer Datenbank). Eine Zeile in
    employees - von 0007 nie beruehrt - begleitet den Rundlauf, um zu zeigen,
    dass down() wirklich nur coverage_requirements trifft (siehe dortiger
    Docstring) und sonst nichts.
    """
    migrations, verzeichnis, db_file = leere_migrationen
    (verzeichnis / '0001_baseline.py').write_text(BASELINE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0002_indexes.sql').write_text(INDEXES_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0003_login_attempts.sql').write_text(
        LOGIN_ATTEMPTS_SQL_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0004_employee_availability.py').write_text(
        AVAILABILITY_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0005_assignment_times.py').write_text(
        ASSIGNMENT_TIMES_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    (verzeichnis / '0006_coverage.py').write_text(COVERAGE_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '08:00', '14:00')")
        connection.execute(
            'INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (1, 0, 2)')
        connection.commit()
    finally:
        connection.close()

    (verzeichnis / '0007_derive_coverage.py').write_text(
        DERIVE_COVERAGE_PY_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        vorher = connection.execute(
            'SELECT weekday, start_time, end_time, required_count FROM coverage_requirements '
            'ORDER BY weekday, start_time'
        ).fetchall()
    finally:
        connection.close()
    assert vorher == [(0, '08:00', '14:00', 2)]

    zurueckgerollt = migrations.rollback_last()
    assert zurueckgerollt == '0007_derive_coverage'

    connection = sqlite3.connect(db_file)
    try:
        anzahl = connection.execute('SELECT COUNT(*) FROM coverage_requirements').fetchone()[0]
    finally:
        connection.close()
    assert anzahl == 0

    erneut = migrations.apply_pending()
    assert '0007_derive_coverage' in erneut

    connection = sqlite3.connect(db_file)
    try:
        nachher = connection.execute(
            'SELECT weekday, start_time, end_time, required_count FROM coverage_requirements '
            'ORDER BY weekday, start_time'
        ).fetchall()
        mitarbeiter = connection.execute('SELECT name FROM employees').fetchall()
    finally:
        connection.close()

    assert nachher == vorher
    assert mitarbeiter == [('Anna',)]


def test_bedarfsmigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(fresh_db):
    """Rueckwaerts allein reicht nicht - die Migration muss danach wieder vorwaerts laufen.

    Vorbild: test_zeitmigration_... aus Etappe 2. Bestandszeile einfuegen, damit
    der zweite Vorwaertslauf nicht auf einer leeren Datenbank laeuft.

    Anders als beim Vorbild ueberlebt keine der drei neuen Tabellen die
    Ruecknahme selbst (down() nimmt sie vollstaendig zurueck, siehe
    0006_coverage.py) - die Bestandszeile geht deshalb nicht in eine von
    ihnen, sondern in employees, das schon vor dieser Migration existiert und
    von ihrem down() unberuehrt bleibt.

    Nicht auf "die letzte Migration" verlassen (wie test_indexmigration_ und
    test_fenstermigration_ oben): eine spaetere Aufgabe koennte weitere
    Migrationen hinter 0006_coverage anhaengen, und ein einzelnes
    rollback_last() wuerde dann die falsche Migration zurueckrollen - genau
    der Fehler, der test_zeitmigration_... oben erst durch das Hinzufuegen
    dieser Migration sichtbar wurde.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    assert '0006_coverage' in migrations.applied_versions()

    while '0006_coverage' in migrations.applied_versions():
        migrations.rollback_last()
    assert '0006_coverage' not in migrations.applied_versions()

    # Alle drei, nicht nur business_hours: up() legt mit CREATE TABLE IF NOT
    # EXISTS an, also verschwaende ein vergessenes DROP TABLE in down() keinen
    # Fehler - der Rundlauf saehe trotzdem gruen aus, und die Tabelle behielte
    # ihren alten Inhalt ueber einen Rollback hinweg.
    verblieben = tabellen(db_file) & {
        'business_hours', 'business_hours_exceptions', 'coverage_requirements'}
    assert verblieben == set(), f'down() hat stehen gelassen: {sorted(verblieben)}'

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.commit()
    finally:
        connection.close()

    erneut = migrations.apply_pending()
    assert '0006_coverage' in erneut

    connection = sqlite3.connect(db_file)
    try:
        zeilen = connection.execute(
            'SELECT weekday, open_time, close_time, closed FROM business_hours ORDER BY weekday'
        ).fetchall()
    finally:
        connection.close()

    assert zeilen == [(wd, '00:00', '00:00', 0) for wd in range(7)]


# ---------- 0008_max_daily_hours ----------


def test_0008_ergaenzt_die_taegliche_hoechstarbeitszeit(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {zeile[1] for zeile in connection.execute('PRAGMA table_info(employees)')}
    finally:
        connection.close()

    assert 'max_daily_hours' in spalten


def test_0008_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    """Der Rundlauf, an dem 0004 im Abschluss-Review von Etappe 1 gescheitert waere.

    ADD COLUMN kann kein IF NOT EXISTS, und down() laesst die Spalte bewusst
    stehen (SQLite kann DROP COLUMN nicht verlaesslich). Ohne den
    table_columns()-Waechter in up() wuerde der zweite Vorwaertslauf an
    'duplicate column name' scheitern - und weil app.py die Migrationen beim
    Modulimport ausfuehrt, waere das eine Anwendung, die nicht mehr startet.
    """
    migrations, _db_file = fresh_db
    migrations.apply_pending()
    assert '0008_max_daily_hours' in migrations.applied_versions()

    zurueck_bis(migrations, '0008_max_daily_hours')

    assert '0008_max_daily_hours' not in migrations.applied_versions()
    assert '0008_max_daily_hours' in migrations.apply_pending()


def test_0008_setzt_bestandszeilen_auf_zehn_stunden(fresh_db):
    """Bestandsmitarbeiter bekommen die Obergrenze aus Paragraph 3 ArbZG.

    Der Mitarbeiter wird VOR der Migration angelegt - nur so prueft der Test
    den DEFAULT der Spaltenergaenzung und nicht den einer spaeteren Einfuegung.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    zurueck_bis(migrations, '0008_max_daily_hours')

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("INSERT INTO employees (name, active) VALUES ('Anna', 1)")
        connection.commit()
    finally:
        connection.close()

    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        zeile = connection.execute(
            "SELECT max_daily_hours FROM employees WHERE name = 'Anna'").fetchone()
    finally:
        connection.close()

    assert zeile['max_daily_hours'] == 10


# ---------- 0009_break_minutes ----------


def test_0009_ergaenzt_die_ruhepause(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {zeile[1] for zeile in connection.execute('PRAGMA table_info(shift_assignments)')}
    finally:
        connection.close()

    assert 'break_minutes' in spalten


def test_0009_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    migrations, _db_file = fresh_db
    migrations.apply_pending()
    assert '0009_break_minutes' in migrations.applied_versions()

    zurueck_bis(migrations, '0009_break_minutes')

    assert '0009_break_minutes' not in migrations.applied_versions()
    assert '0009_break_minutes' in migrations.apply_pending()


def test_0009_laesst_bestandszeilen_auf_null(fresh_db):
    """Der ganze Punkt der Nullbarkeit.

    NULL heisst "nicht abweichend geregelt" und wird als gesetzliche
    Mindestpause gelesen. Ein DEFAULT 0 wuerde daraus die Aussage "keine
    Pause" machen - und damit jede Bestandszeile ruecckwirkend auf einen Plan
    festlegen, den Paragraph 4 so nicht zulaesst.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    zurueck_bis(migrations, '0009_break_minutes')

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 9, 'generated')")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Tag', '08:00', '16:00')")
        connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
            "VALUES (1, '2026-09-01', 1, 0)")
        connection.commit()
    finally:
        connection.close()

    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        zeile = connection.execute(
            'SELECT break_minutes FROM shift_assignments').fetchone()
    finally:
        connection.close()

    assert zeile['break_minutes'] is None


# ---------- 0010_drop_shift_requirements ----------


def test_0010_entfernt_die_alte_bedarfstabelle(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        tabellen = {zeile[0] for zeile in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()

    assert 'shift_requirements' not in tabellen


def test_0010_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    """Rundlauf up -> down -> up.

    Bei einer Migration, die etwas ENTFERNT, laeuft er andersherum als sonst:
    down() legt die Tabelle wieder an, der zweite Vorwaertslauf entfernt sie
    erneut. Ohne den Waechter in up() scheiterte er am fehlenden Objekt.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    zurueck_bis(migrations, '0010_drop_shift_requirements')

    connection = sqlite3.connect(db_file)
    try:
        tabellen = {zeile[0] for zeile in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert 'shift_requirements' in tabellen

    assert '0010_drop_shift_requirements' in migrations.apply_pending()


def test_0010_stellt_beim_rollback_eine_leere_tabelle_her(fresh_db):
    """Die Daten sind fort - bei einem DROP nicht anders zu haben.

    Der Test haelt es fest, damit niemand die zurueckgerollte Tabelle fuer
    vollstaendig haelt.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    zurueck_bis(migrations, '0010_drop_shift_requirements')

    connection = sqlite3.connect(db_file)
    try:
        anzahl = connection.execute('SELECT COUNT(*) FROM shift_requirements').fetchone()[0]
    finally:
        connection.close()

    assert anzahl == 0


# ---------- 0011_settings ----------


def test_0011_legt_die_einstellungstabelle_an(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {zeile[1] for zeile in connection.execute('PRAGMA table_info(settings)')}
    finally:
        connection.close()

    # id ist Pflicht, nicht Zierde: die Dialektschicht haengt an jedes INSERT
    # ein RETURNING id an, und eine Tabelle ohne die Spalte ist auf Postgres
    # nicht beschreibbar. Auf SQLite faellt das nicht auf - deshalb steht es
    # hier als Erwartung.
    assert spalten == {'id', 'name', 'value'}


def test_0011_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    zurueck_bis(migrations, '0011_settings')

    connection = sqlite3.connect(db_file)
    try:
        tabellen = {zeile[0] for zeile in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert 'settings' not in tabellen

    assert '0011_settings' in migrations.apply_pending()


# ---------- 0012_publish_state ----------


def test_0012_veroeffentlicht_bestandsplaene(fresh_db):
    """Die Richtung, auf die es ankommt.

    Eine Migration darf nicht aendern, was Leute gestern sehen konnten. Auf
    'draft' zu setzen liesse alle laufenden Plaene verschwinden, bis jemand
    sie einzeln freigibt.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    zurueck_bis(migrations, '0012_publish_state')

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 3, 'generated')")
        connection.commit()
    finally:
        connection.close()

    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        zeile = connection.execute('SELECT status, published_at FROM schedules').fetchone()
    finally:
        connection.close()

    assert zeile['status'] == 'published'
    assert zeile['published_at'] is not None


def test_0012_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    migrations, _db_file = fresh_db
    migrations.apply_pending()

    zurueck_bis(migrations, '0012_publish_state')

    assert '0012_publish_state' in migrations.apply_pending()


def test_0012_dreht_die_zustaende_beim_rollback_zurueck(fresh_db):
    """Sonst faende der Bestand nach einem Rollback Werte vor, die die alte
    Fassung nicht kennt."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 4, 'draft')")
        connection.commit()
    finally:
        connection.close()

    zurueck_bis(migrations, '0012_publish_state')

    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        zustaende = {z['status'] for z in connection.execute('SELECT status FROM schedules')}
    finally:
        connection.close()

    assert zustaende == {'generated'}


# ---------- 0013_audit_log ----------


def test_0013_legt_das_protokoll_an(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {zeile[1] for zeile in connection.execute('PRAGMA table_info(audit_log)')}
    finally:
        connection.close()

    assert spalten == {'id', 'at', 'user_id', 'username', 'method', 'path', 'status'}


def test_0013_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    migrations, _db_file = fresh_db
    migrations.apply_pending()

    zurueck_bis(migrations, '0013_audit_log')

    assert '0013_audit_log' in migrations.apply_pending()


def test_0013_haelt_eintraege_ohne_fremdschluessel_auf_users(fresh_db):
    """Ein Protokoll, dessen Eintraege sich loeschen lassen, indem man das Konto
    loescht, ist keines.

    Geprueft ueber eine user_id, die es gar nicht gibt: mit Fremdschluessel
    waere das ein Fehler, ohne einen ist es genau der Zustand, den ein
    geloeschtes Konto hinterlaesst.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute(
            "INSERT INTO audit_log (at, user_id, username, method, path, status) "
            "VALUES ('2026-08-23 10:00:00', 9999, 'hr', 'PUT', '/assignments/1', 200)")
        connection.commit()
        anzahl = connection.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    finally:
        connection.close()

    assert anzahl == 1


# ---------- 0014_anonymisation ----------


def test_0014_ergaenzt_den_anonymisierungszeitpunkt(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        spalten = {zeile[1] for zeile in connection.execute('PRAGMA table_info(employees)')}
    finally:
        connection.close()

    assert 'anonymized_at' in spalten


def test_0014_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts(fresh_db):
    migrations, _db_file = fresh_db
    migrations.apply_pending()

    zurueck_bis(migrations, '0014_anonymisation')

    assert '0014_anonymisation' in migrations.apply_pending()


# ---------- 0015_swap_requests ----------


def test_tauschantraege_laufen_rund(fresh_db):
    """Rundlauf, und die Gegenprobe, dass down() beide Indizes mitnimmt.

    Ein vergessenes DROP INDEX bliebe bei CREATE INDEX IF NOT EXISTS unbemerkt
    - derselbe Fehler, den der 0006-Rundlauf seit Etappe 6c auch prueft.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()
    assert 'shift_swap_requests' in tabellen(db_file)
    assert {'ix_swap_requests_requester', 'ix_swap_requests_partner'} <= indizes(db_file)

    while '0015_swap_requests' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'shift_swap_requests' not in tabellen(db_file)
    assert not ({'ix_swap_requests_requester', 'ix_swap_requests_partner'} & indizes(db_file))

    assert '0015_swap_requests' in migrations.apply_pending()
    assert 'shift_swap_requests' in tabellen(db_file)


def test_ein_antrag_faellt_mit_seiner_schicht_weg(fresh_db):
    """ON DELETE CASCADE: ein Antrag auf einen geloeschten Platz ist kein
    Antrag mehr, sondern Muell.

    Auf SQLite braucht das eingeschaltete Fremdschluessel - die Anwendung
    setzt PRAGMA foreign_keys ein, dieser Test also auch.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        anna = connection.execute("INSERT INTO employees (name) VALUES ('Anna')").lastrowid
        berta = connection.execute("INSERT INTO employees (name) VALUES ('Berta')").lastrowid
        schedule_id = connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 9, 'published')").lastrowid
        eine = connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            "employee_id, start_time, end_time) VALUES (?, '2026-09-07', NULL, 0, ?, "
            "'06:00', '14:00')", (schedule_id, anna)).lastrowid
        andere = connection.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            "employee_id, start_time, end_time) VALUES (?, '2026-09-14', NULL, 1, ?, "
            "'06:00', '14:00')", (schedule_id, berta)).lastrowid
        connection.execute(
            'INSERT INTO shift_swap_requests (requester_employee_id, requester_assignment_id, '
            'partner_employee_id, partner_assignment_id, status, created_at) '
            "VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)",
            (anna, eine, berta, andere))
        connection.commit()

        connection.execute('DELETE FROM shift_assignments WHERE id = ?', (eine,))
        connection.commit()

        verblieben = connection.execute(
            'SELECT COUNT(*) FROM shift_swap_requests').fetchone()[0]
        assert verblieben == 0
    finally:
        connection.close()
