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
ALLE_MIGRATIONEN_TABELLEN = BASELINE_TABELLEN | {
    'login_attempts', 'employee_availability',
    'business_hours', 'business_hours_exceptions', 'coverage_requirements',
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
    """Task 1 legt nur die Tabelle an. Die Ableitung ist Task 3.

    Dieser Test ist die Abgrenzung zwischen den beiden Aufgaben und darf nach
    Task 3 angepasst werden - aber bewusst und mit Begruendung, nicht nebenbei.
    """
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        anzahl = connection.execute('SELECT COUNT(*) FROM coverage_requirements').fetchone()[0]
    finally:
        connection.close()

    assert anzahl == 0


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
