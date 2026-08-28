# Etappe 2 — Individuelle Zeiten pro Zuweisung: Umsetzungsplan

**Ziel:** Eine Zuweisung trägt eigene Uhrzeiten. „Ben steht am 17.03. als 10:00–16:00 im Plan, obwohl die Frühschicht 06:00–14:00 läuft" wird ausdrückbar, und alle Prüfungen rechnen mit den tatsächlichen Zeiten. Gleichzeitig wird `shift_type_id` nullable, damit ein Block ohne Vorlage überhaupt existieren kann — die Voraussetzung für den Zuschnitt in Etappe 4.

**Architektur:** Zwei neue Spalten auf `shift_assignments` (`start_time`, `end_time`, beide NULL) plus eine Lockerung: `shift_type_id` wird nullable. Kein neues Konzept, keine neue Tabelle. Der eigentliche Umbau ist eine **Vereinheitlichung**: die Frage „welche Zeiten laufen für diese Zuweisung wirklich?" wird heute an fünf Stellen einzeln beantwortet und bekommt genau eine Funktion. Der Suchkern in `scheduler.py` bleibt unangetastet.

**Tech-Stack:** Flask 3.1, SQLite lokal + Postgres in Produktion, React 19 + Vite, pytest 9.

**Spec:** [`docs/entwuerfe/2026-08-16-zeitachsen-dienstplan-design.md`](../specs/2026-08-16-zeitachsen-dienstplan-design.md), Abschnitte 4.6, 4.7 und „Etappe 2".

## Globale Rahmenbedingungen

- **Keine neuen Abhängigkeiten**, weder Laufzeit (aktuell fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata) noch Frontend.
- **Alle 112 bestehenden Tests bleiben grün und warnungsfrei**, auch unter `-W error::DeprecationWarning`. Die 23 Tests in `backend/test_scheduler.py` bleiben zusätzlich **unverändert** — sie sind die Rückwärtskompatibilitätsgarantie. Werden sie rot, ist die Änderung falsch, nicht der Test.
- **Alle vier CI-Jobs müssen grün bleiben**, insbesondere `backend-postgres`. Lokal läuft nur SQLite; Postgres-Verhalten nie aus SQLite schließen.
- **Jede nutzersichtbare Meldung zweisprachig** — Backend über `backend/i18n.py` und `t(g.lang, key)`, Frontend über `frontend/src/i18n/translations.js`, `de` **und** `en`, mit echten Umlauten. Nie ein Literal.
- **Kein literales `?` in SQL, auch nicht in Kommentaren** — die Dialektschicht in `db.py` ersetzt es bedingungslos durch `%s`. Das hat in Etappe 0 einen Produktionsausfall verursacht. **Semikolons in SQL-Kommentaren** zerteilen die Datei am Splitter in `migrations.py`.
- **Eine Migration muss nach ihrer eigenen Rücknahme wieder vorwärts laufen.** Alles, was nicht `IF NOT EXISTS` kann — vor allem `ADD COLUMN` — gehört in eine `.py`-Migration mit `table_columns()`-Wächter, und jede solche Migration braucht einen Rundlauftest up → down → up. Das war der Critical aus dem Abschluss-Review von Etappe 1.
- Zeiten sind `"HH:MM"`-Strings. **`end <= start` bedeutet Überschreitung nach Mitternacht**, überall im Projekt (siehe `scheduler.shift_duration_minutes`).
- Wochentagskonvention: 0 = Montag … 6 = Sonntag.
- **Sprache: der Datei folgen, die du anfasst.** `app.py`, `db.py`, `scheduler.py`, `test_scheduler.py` und das Frontend sind englisch kommentiert; `security.py`, `timeutil.py`, `migrations.py`, die Migrationsdateien und die neueren Testdateien deutsch. Eine einzelne Datei in zwei Sprachen zu führen ist der eigentliche Fehler. README englisch.
- Commit-Nachrichten auf Deutsch, Präfix `feat:`, `fix:`, `test:`, `chore:` oder `docs:`.
- Jede Aufgabe endet mit genau **einem** Commit und grüner CI.

---

## Die zentrale Semantik — einmal präzise, gilt für alle Aufgaben

### Die Vorrangregel

Eine Zuweisung läuft an einem Datum zu **genau einem** Zeitpaar. Es wird in dieser Reihenfolge bestimmt:

1. **`shift_assignments.start_time`/`end_time`**, wenn gefüllt — die individuellen Zeiten genau dieser Person auf genau diesem Platz.
2. sonst **`shift_time_overrides`** für `(schedule_id, date, shift_type_id)` — die Ausnahme für diesen einen Tag, die für alle auf dieser Schicht gilt.
3. sonst **`shift_types.start_time`/`end_time`** — die übliche Zeit der Vorlage.

Beide neuen Spalten sind entweder **beide** gefüllt oder **beide** NULL. Ein halb gefülltes Paar ist ein Datenfehler und wird von der API abgelehnt (400), nicht stillschweigend zur Hälfte interpretiert.

Ein Block **ohne** Vorlage (`shift_type_id IS NULL`) **muss** eigene Zeiten tragen — für ihn gibt es keine Stufe 2 und keine Stufe 3, von denen er erben könnte. Auch das erzwingt die API.

**Alle bestehenden Zeilen bleiben durch diese Regel unverändert korrekt**, weil sie beide Spalten auf NULL haben und damit auf Stufe 2 bzw. 3 landen — genau dort, wo sie heute schon landen.

### Warum das die eigentliche Arbeit ist

Diese Frage wird in `backend/app.py` heute an **fünf** Stellen einzeln beantwortet, jedes Mal nach demselben Muster „Schichtart laden, dann `effective_shift_hours()` fragen":

- `fetch_schedule()` (`app.py:1274-1299`) — für die Anzeige, über einen vorab geladenen Override-Dict
- `constraint_warnings()`, Fensterprüfung (`app.py:1693-1703`)
- `constraint_warnings()`, Wochenstunden für die **bestehenden** Schichten der Woche (`app.py:1743-1755`)
- `constraint_warnings()`, Wochenstunden für die **vorgeschlagene** Schicht (`app.py:1757-1762`)
- `constraint_warnings()`, Ruhezeit für die eigene und beide Nachbarschichten (`app.py:1768-1796`)

Fünf Kopien derselben Logik sind heute schon grenzwertig; mit einer dritten Vorrangstufe werden sie zu fünf Gelegenheiten, sie unterschiedlich falsch zu machen. **Aufgabe 2 führt sie zusammen, bevor Aufgabe 3 und 4 die neue Stufe einziehen.** Diese Reihenfolge ist Absicht: erst aufräumen, dann erweitern.

### Was `shift_type_id IS NULL` in SQL bedeutet

`WHERE shift_type_id = ?` mit dem Wert `None` trifft **keine** Zeile — auch nicht die mit NULL. In SQL ist `NULL = NULL` unbekannt, nicht wahr. Jede Abfrage, die heute nach `shift_type_id` filtert, muss deshalb geprüft werden. Betroffen sind mindestens:

- `add_slot()` (`app.py:1594-1598`), das den nächsten `slot_index` sucht
- `effective_shift_hours()` (`app.py:1635-1638`)
- der UNIQUE-Index `ux_assignment_slot`

Für den Index löst das die Spec in 4.7 bereits: er wird zu `(schedule_id, date, COALESCE(shift_type_id, 0), slot_index)`. Postgres behandelt NULLs in einem UNIQUE-Index als voneinander verschieden — ohne `COALESCE` würde der Index für freie Blöcke schlicht nichts mehr garantieren. `0` ist als Ersatzwert sicher, weil `shift_types.id` bei beiden Dialekten bei 1 beginnt.

### Was NICHT in dieser Etappe passiert

- **Der Planer erzeugt weiterhin keine freien Blöcke und keine individuellen Zeiten.** `generate_schedule()` bleibt unverändert; die neuen Spalten bleiben bei jeder erzeugten Zuweisung NULL. Das Erzeugen von Blöcken mit eigenen Zeiten ist Etappe 4.
- **Es gibt keine Schaltfläche „freien Block anlegen".** Das Datenmodell und die API müssen freie Blöcke tragen können — das ist die Voraussetzung für Etappe 4 — und die Ansichten müssen sie **darstellen** können. Eine Eingabemaske, um sie von Hand zu erzeugen, verlangt niemand; sie käme mit Etappe 4 oder gar nicht. YAGNI.
- **`shift_time_overrides` bleibt bestehen.** Die Zeitänderung pro Datum für eine ganze Schicht ist der häufige Fall und bleibt, wie sie ist. Die neue Spalte ist der seltenere Fall daneben, nicht ihr Ersatz.
- **Keine Überlappungs- oder Plausibilitätsprüfung** zwischen den individuellen Zeiten und der Schichtart. Steht Ben auf der Frühschicht 06:00–14:00 mit eigenen Zeiten 20:00–23:00, ist das erlaubt und wird nicht kommentiert. Es ist Handarbeit von HR, und HR bleibt der Chef.

---

## Dateistruktur

| Datei | Verantwortung nach dieser Etappe |
|---|---|
| `backend/migrations/0005_assignment_times.py` | **neu** — die zwei Spalten, die Lockerung auf nullable, der ersetzte UNIQUE-Index. Dialektabhängig, deshalb `.py` |
| `backend/app.py` | `assignment_hours()` als einzige Zeitauflösung; `fetch_schedule()` und `constraint_warnings()` darauf umgestellt; `PUT /assignments/<id>` nimmt Zeiten entgegen |
| `backend/i18n.py` | neue Fehlermeldungen, `de` und `en` |
| `backend/test_migrations.py`, `backend/test_migrations_postgres.py` | Schema, Rundlauf, Bestandsdaten |
| `backend/test_api_assignment_times.py` | **neu** — Vorrangregel, Validierung, Auswirkung auf die Warnungen |
| `frontend/src/components/ShiftCell.jsx` | zeigt die tatsächlichen Zeiten pro Person; HR kann sie für eine Person ändern |
| `frontend/src/components/ScheduleGrid.jsx`, `CalendarView.jsx` | kommen mit `shift_type_id === null` klar |
| `frontend/src/i18n/translations.js` | neue Texte, `de` und `en` |
| `README.md` | beschreibt die Vorrangregel und die freien Blöcke |

`backend/scheduler.py` und `backend/test_scheduler.py` werden **nicht** angefasst.

---

## Aufgabe 1: Migration und Schema

**Files:**
- Create: `backend/migrations/0005_assignment_times.py`
- Modify: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`

**Interfaces:**
- Consumes: den Migrations-Runner aus Etappe 0 (`up(cursor)`/`down(cursor)`, siehe `backend/migrations.py:15` und `_run()` ab Zeile 228) sowie `db.table_columns()` und `db.use_postgres()`
- Produces: `shift_assignments.start_time`, `shift_assignments.end_time` (beide TEXT NULL), `shift_assignments.shift_type_id` nullable, Index `ux_assignment_slot_v2`

**Der schwierige Teil, vorab:** `shift_type_id` ist heute `INTEGER NOT NULL REFERENCES shift_types(id)` (`backend/migrations/0001_baseline.py:203`). Postgres kann das mit `ALTER TABLE ... ALTER COLUMN ... DROP NOT NULL` lockern. **SQLite kann das nicht** — dort führt kein Weg an einem Tabellenneubau vorbei: neue Tabelle anlegen, Daten kopieren, alte löschen, umbenennen. Die Migration ist deshalb dialektabhängig und muss eine `.py`-Datei sein.

Beim Neubau gehen **alle Indizes der Tabelle verloren**, weil `DROP TABLE` sie mitnimmt. Betroffen sind `ix_assignments_date_employee`, `ix_assignments_schedule` und `ux_assignment_slot` aus Migration `0002`. Sie müssen danach wieder angelegt werden — `ux_assignment_slot` gleich in seiner neuen Form.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `backend/test_migrations.py` ergänzen. Das Tabellen-Literal in dieser Datei ist **absichtlich fest verdrahtet** und darf nicht aus den Migrationsdateien abgeleitet werden — das war ein Befund aus Etappe 0. `shift_assignments` steht dort bereits drin, es kommt also keine Tabelle hinzu; geprüft werden Spalten und Nullability.

```python
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


def test_bestandszuweisungen_ueberleben_den_tabellenneubau(fresh_db):
    """Der SQLite-Pfad baut die Tabelle neu - die vorhandenen Zeilen muessen das ueberstehen.

    Deshalb wird hier bis 0004 migriert, DANN eingefuegt und erst danach 0005
    nachgeschoben. Andersherum wuerde der Test nur belegen, dass ein frischer
    Insert funktioniert - genau der Fehler, der in Etappe 1 gefunden wurde.
    """
    migrations, db_file = fresh_db
    for version in ('0001_baseline', '0002_indexes', '0003_login_attempts', '0004_employee_availability'):
        migrations.apply_one(version)

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

    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        zeile = connection.execute(
            'SELECT schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited, '
            'start_time, end_time FROM shift_assignments').fetchone()
    finally:
        connection.close()

    assert zeile == (1, '2026-03-17', 1, 0, 1, 1, None, None)


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

    Vorbild: test_fenstermigration_... aus Etappe 1, entstanden aus dem Critical
    des dortigen Abschluss-Reviews.
    """
    migrations, _ = fresh_db
    migrations.apply_pending()
    assert '0005_assignment_times' in migrations.applied_versions()

    migrations.rollback_last()
    assert '0005_assignment_times' not in migrations.applied_versions()

    migrations.apply_pending()
    assert '0005_assignment_times' in migrations.applied_versions()
```

**Vor dem Übernehmen:** `migrations.apply_one(version)` ist im Test oben eine Annahme. In `backend/migrations.py` nachsehen, wie die bestehenden Tests einzelne Versionen anwenden, und exakt den vorhandenen Weg benutzen. Gibt es keinen, stattdessen über `apply_pending()` vor dem Anlegen der `0005`-Datei staffeln — keine neue öffentliche Funktion im Runner nur für einen Test.

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
cd backend && ./venv/Scripts/python -m pytest test_migrations.py -q
```

Erwartet: die neuen Tests scheitern mit „no such column: start_time" bzw. einer `IntegrityError`, die ausbleibt. Prüfe, dass die Fehler genau das sind und nicht etwas anderes — ein Test, der aus dem falschen Grund rot ist, ist kein Rot-Nachweis.

- [ ] **Schritt 3: Die Migration schreiben**

`backend/migrations/0005_assignment_times.py`:

```python
"""Individuelle Zeiten pro Zuweisung, und Bloecke ohne Vorlage.

Zwei Aenderungen an shift_assignments:

1. start_time/end_time. NULL heisst "erbt wie bisher" - erst ein Eintrag in
   shift_time_overrides fuer dieses Datum, sonst die Zeit der Schichtart.
   Gefuellt heisst "genau diese Person arbeitet auf diesem Platz genau diese
   Zeit". Alle Bestandszeilen haben NULL und bleiben damit unveraendert gueltig.

2. shift_type_id wird nullable. Ein Block ohne Vorlage traegt seine Zeiten
   selbst; er ist die Voraussetzung fuer den Zuschnitt in Etappe 4, wo der
   Planer Restbedarf erzeugt, fuer den es keine passende Schichtart gibt.

Warum .py und nicht .sql: Postgres lockert NOT NULL mit ALTER COLUMN, SQLite
kann das nicht und braucht einen Tabellenneubau. Ausserdem ist der ALTER fuer
die beiden neuen Spalten bedingt, damit die Migration nach ihrer eigenen
Ruecknahme wieder vorwaerts laeuft - die Lehre aus dem Abschluss-Review von
Etappe 1.

Der UNIQUE-Index wird ersetzt statt geaendert: Postgres behandelt NULLs in
einem UNIQUE-Index als voneinander verschieden, ux_assignment_slot wuerde fuer
Bloecke ohne Vorlage also gar nichts mehr garantieren. COALESCE(shift_type_id, 0)
faengt das ab; 0 ist sicher, weil shift_types.id bei beiden Dialekten bei 1
beginnt.
"""

from db import table_columns, use_postgres


def _add_time_columns(cursor):
    spalten = table_columns(cursor, 'shift_assignments')
    if 'start_time' not in spalten:
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN start_time TEXT')
    if 'end_time' not in spalten:
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN end_time TEXT')


def _rebuild_indexes(cursor):
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_assignments_date_employee '
                   'ON shift_assignments(date, employee_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_assignments_schedule '
                   'ON shift_assignments(schedule_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot_v2 '
                   'ON shift_assignments(schedule_id, date, COALESCE(shift_type_id, 0), slot_index)')


def up(cursor):
    _add_time_columns(cursor)

    # Der alte Index kennt COALESCE nicht und wuerde fuer NULL-Schichtarten
    # nichts mehr garantieren. Zuerst weg, damit der Neubau unten ihn nicht
    # versehentlich wieder mitbringt.
    cursor.execute('DROP INDEX IF EXISTS ux_assignment_slot')

    if use_postgres():
        cursor.execute('ALTER TABLE shift_assignments ALTER COLUMN shift_type_id DROP NOT NULL')
    else:
        # SQLite kennt kein ALTER COLUMN. Neubau nach dem offiziell empfohlenen
        # Ablauf: neue Tabelle, kopieren, tauschen. Die Spaltenliste ist
        # absichtlich ausgeschrieben und nicht aus PRAGMA abgeleitet - eine
        # abgeleitete Liste wuerde jede kuenftige Spalte stillschweigend
        # mitnehmen und diesen Neubau von einer weiteren Migration abhaengig
        # machen.
        cursor.execute('''
            CREATE TABLE shift_assignments_neu(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                shift_type_id INTEGER REFERENCES shift_types(id),
                slot_index INTEGER NOT NULL,
                employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                manually_edited INTEGER NOT NULL DEFAULT 0,
                absence_type TEXT,
                absent_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                start_time TEXT,
                end_time TEXT
            )
        ''')
        cursor.execute('''
            INSERT INTO shift_assignments_neu
                (id, schedule_id, date, shift_type_id, slot_index, employee_id,
                 manually_edited, absence_type, absent_employee_id, start_time, end_time)
            SELECT id, schedule_id, date, shift_type_id, slot_index, employee_id,
                   manually_edited, absence_type, absent_employee_id, start_time, end_time
            FROM shift_assignments
        ''')
        cursor.execute('DROP TABLE shift_assignments')
        cursor.execute('ALTER TABLE shift_assignments_neu RENAME TO shift_assignments')

    _rebuild_indexes(cursor)


def down(cursor):
    """Nimmt den Index zurueck und stellt den alten wieder her.

    Die beiden Zeitspalten bleiben stehen, und shift_type_id bleibt nullable -
    aus demselben Grund wie bei 0004: eine zurueckgebliebene Spalte mit NULL
    ist harmlos, und ein Rollback, der an einem nicht rueckbaubaren Schema
    scheitert, waere schlimmer als eine Lockerung, die bestehen bleibt. Der
    Vorwaertslauf ist dank der Waechter oben trotzdem wiederholbar.

    Achtung: existieren bereits Zeilen mit shift_type_id IS NULL, koennte der
    alte Index sie nicht mehr eindeutig halten. Da down() die Spalte nicht
    wieder auf NOT NULL zieht, ist das kein Fehlerfall, sondern nur der Grund,
    warum diese Ruecknahme bewusst unvollstaendig ist.
    """
    cursor.execute('DROP INDEX IF EXISTS ux_assignment_slot_v2')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot '
                   'ON shift_assignments(schedule_id, date, shift_type_id, slot_index)')
```

- [ ] **Schritt 4: Postgres-Gegenprobe**

In `backend/test_migrations_postgres.py` die Entsprechungen zu `test_zuweisung_hat_eigene_zeitspalten`, `test_schichtart_ist_jetzt_optional` und dem Rundlauftest ergänzen. Orientiere dich strikt an den vorhandenen Tests derselben Datei — sie zeigen, wie dort eine Wegwerf-Datenbank aufgebaut und wieder abgeräumt wird.

Für die Nullability liest du in Postgres nicht `PRAGMA`, sondern:

```python
cursor.execute(
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_name = 'shift_assignments' AND column_name = 'shift_type_id'")
assert cursor.fetchone()[0] == 'YES'
```

**Diese Tests laufen lokal nicht** (kein Postgres auf dem Rechner). Sie gelten als „nicht lokal verifiziert, der CI-Job `backend-postgres` ist die Probe" — eine behauptete Verifikation, die nicht stattgefunden hat, wäre der schwerste Fehler an dieser Stelle.

- [ ] **Schritt 5: Rot-Nachweis für den Rundlauf**

Entferne kurz die beiden `if ... not in spalten`-Wächter aus `_add_time_columns()`, lass **nur** den Rundlauftest laufen, halte die Ausgabe fest (erwartet: `duplicate column name: start_time`), und stelle die Wächter wieder her. Ohne diesen Nachweis ist nicht belegt, dass der Test am Wächter hängt.

- [ ] **Schritt 6: Suite und CI**

```bash
cd backend && ./venv/Scripts/python -m pytest -q
cd backend && ./venv/Scripts/python -W error::DeprecationWarning -m pytest -q
```

Beide grün und warnungsfrei. `git diff --stat backend/test_scheduler.py` muss leer sein. Dann pushen und die vier CI-Jobs abwarten — `backend-postgres` ist hier der wichtige.

- [ ] **Schritt 7: Commit**

```bash
git add backend/migrations/0005_assignment_times.py backend/test_migrations.py backend/test_migrations_postgres.py
git commit -m "feat: Schema fuer individuelle Zuweisungszeiten"
```

---

## Aufgabe 2: Die Zeitauflösung an genau einer Stelle

**Files:**
- Modify: `backend/app.py`
- Test: `backend/test_api_assignment_times.py` (neu)

**Interfaces:**
- Consumes: nichts aus Aufgabe 1 außer dem Schema
- Produces: `assignment_hours(cursor, row)` — nimmt eine Zeile (oder ein Dict) mit den Schlüsseln `schedule_id`, `date`, `shift_type_id`, `start_time`, `end_time` und liefert `(start, end)` als `"HH:MM"`-Strings oder `(None, None)`, wenn sich keine Zeit bestimmen lässt. **Aufgabe 3, 4 und 5 benutzen ausschließlich diese Funktion.**

Diese Aufgabe ist eine **reine Umstrukturierung**: nach ihr verhält sich die Anwendung exakt wie vorher, weil alle Zeilen `start_time IS NULL` haben. Genau deshalb kommt sie vor der Erweiterung — der Refactor lässt sich gegen die bestehende Testsuite absichern, und Aufgabe 3 bis 5 haben danach nur noch eine Stelle anzufassen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Neue Datei `backend/test_api_assignment_times.py`. Die Fixtures kommen aus `backend/conftest.py` — sieh dort nach, welche es gibt (`test_api_availability.py` aus Etappe 1 ist das nächstliegende Vorbild für den Aufbau: HR-Konto anlegen, einloggen, Mitarbeiter und Schichtart erzeugen, Plan generieren).

```python
def test_zuweisungszeiten_schlagen_den_datums_override(client, hr_login):
    """Die Vorrangregel, direkt an assignment_hours geprueft.

    Aufbau bewusst dreistufig, damit jede Stufe einzeln widerlegbar ist:
    Schichtart 06:00-14:00, Datums-Override 07:00-15:00, Zuweisungszeit
    10:00-16:00. Erwartet wird die Zuweisungszeit - waere die Reihenfolge
    falsch, kaeme eine der beiden anderen heraus, und beide sind verschieden.
    """
    from app import assignment_hours, get_db

    with client.application.app_context():
        cursor = get_db().cursor()
        zeile = {'schedule_id': 1, 'date': '2026-03-17', 'shift_type_id': 1,
                 'start_time': '10:00', 'end_time': '16:00'}
        assert assignment_hours(cursor, zeile) == ('10:00', '16:00')

        zeile_ohne_eigene = dict(zeile, start_time=None, end_time=None)
        assert assignment_hours(cursor, zeile_ohne_eigene) == ('07:00', '15:00')
```

Den Aufbau der drei Stufen (Schichtart, Override, Plan) legst du im Test selbst an — über die API, nicht mit direktem SQL, damit der Test denselben Weg nimmt wie die Anwendung. `PUT /schedules/<year>/<month>/shift-times` setzt den Datums-Override; sieh dir die Route in `app.py` an.

Ergänze außerdem:

```python
def test_block_ohne_vorlage_nutzt_seine_eigenen_zeiten(client, hr_login):
    """Fuer shift_type_id IS NULL gibt es keine Erbstufe - die eigenen Zeiten sind alles."""


def test_block_ohne_vorlage_und_ohne_zeiten_liefert_keine_zeit(client, hr_login):
    """(None, None) statt einer Ausnahme: der Aufrufer entscheidet, was das bedeutet.

    Diese Kombination kann die API nicht erzeugen (Aufgabe 5 lehnt sie ab), aber
    assignment_hours() darf an einer Altzeile nicht mit AttributeError sterben.
    """
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend && ./venv/Scripts/python -m pytest test_api_assignment_times.py -q
```

Erwartet: `ImportError: cannot import name 'assignment_hours' from 'app'`.

- [ ] **Schritt 3: Die Funktion schreiben**

In `backend/app.py`, direkt **neben** `effective_shift_hours()` (ab Zeile 1633), im selben Abschnitt:

```python
def assignment_hours(cursor, row):
    """The hours one assignment actually runs, by precedence.

    1. the assignment's own start_time/end_time, when set - this person, this
       slot, these hours
    2. otherwise a per-date override for the shift type, which applies to
       everyone on that shift that day
    3. otherwise the shift type's usual hours

    Returns (None, None) for a block that has neither its own times nor a shift
    type to inherit from. The API rejects that combination (see the validation
    in update_assignment), but a caller reading old or hand-edited rows should
    get a value it can test rather than an exception.

    `row` needs the keys schedule_id, date, shift_type_id, start_time and
    end_time - a sqlite3.Row and a plain dict both work.
    """
    if row['start_time'] and row['end_time']:
        return row['start_time'], row['end_time']

    shift_type_id = row['shift_type_id']
    if shift_type_id is None:
        return None, None

    cursor.execute('SELECT start_time, end_time FROM shift_types WHERE id = ?', (shift_type_id,))
    shift_type = cursor.fetchone()
    if not shift_type:
        return None, None

    return effective_shift_hours(
        cursor, row['schedule_id'], row['date'], shift_type_id,
        shift_type['start_time'], shift_type['end_time'])
```

`effective_shift_hours()` bleibt bestehen und behält seine Aufgabe: Stufe 2 gegen Stufe 3. `assignment_hours()` setzt Stufe 1 davor. Baue die Override-Abfrage **nicht** ein zweites Mal nach.

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend && ./venv/Scripts/python -m pytest test_api_assignment_times.py -q
```

- [ ] **Schritt 5: `constraint_warnings()` auf die Funktion umstellen**

`constraint_warnings()` bekommt heute `shift_type_id` als Parameter und leitet daraus überall die Zeiten ab. Das reicht ab jetzt nicht mehr — die Zeiten hängen an der Zuweisung, nicht an der Schichtart. Ändere die Signatur:

```python
def constraint_warnings(cursor, employee_id, assignment_date, shift_type_id, schedule_id,
                        exclude_assignment_id=None, start_time=None, end_time=None):
```

Die beiden neuen Parameter sind die **vorgeschlagenen** Zeiten für genau diese Prüfung. Alle drei Aufrufer (`update_assignment`, `swap_assignments`, `replacement_suggestions`) reichen sie in Aufgabe 5 durch; bis dahin bleiben sie `None`, und das Verhalten ändert sich nicht.

Ersetze die vier Stellen innerhalb der Funktion, die Zeiten bestimmen:

1. **Fensterprüfung** (`app.py:1693-1703`): statt Schichtart laden und `effective_shift_hours()` rufen:

```python
    if employee['availability_mode'] == 'windows':
        start_time_effective, end_time_effective = assignment_hours(cursor, {
            'schedule_id': schedule_id, 'date': assignment_date, 'shift_type_id': shift_type_id,
            'start_time': start_time, 'end_time': end_time,
        })
        if start_time_effective and end_time_effective:
```

Der Rest des Blocks (Fenster laden, `window_is_valid_on`, `window_contains_shift`, die beiden Meldungen) bleibt **wörtlich** wie er ist — nur eingerückt unter die neue Bedingung. Das ersetzt zugleich die `if shift_type_row:`-Bedingung, die es bisher trug.

2. **Wochenstunden, bestehende Schichten** (`app.py:1743-1755`): die Abfrage bekommt die neuen Spalten und wird zum `LEFT JOIN`, damit ein freier Block nicht aus der Wochenrechnung fällt:

```python
        cursor.execute('''
            SELECT sa.id, sa.date, sa.schedule_id, sa.shift_type_id, sa.start_time, sa.end_time
            FROM shift_assignments sa
            WHERE sa.employee_id = ? AND sa.date BETWEEN ? AND ?
        ''', (employee_id, week_start, week_end))
        total_minutes = 0
        for row in cursor.fetchall():
            if exclude_assignment_id is not None and row['id'] == exclude_assignment_id:
                continue
            start, end = assignment_hours(cursor, row)
            if start and end:
                total_minutes += shift_duration_minutes(start, end)
```

Der `JOIN shift_types` entfällt ersatzlos — `assignment_hours()` holt die Schichtart selbst, wenn sie gebraucht wird.

3. **Wochenstunden, vorgeschlagene Schicht** (`app.py:1757-1762`):

```python
        new_start, new_end = assignment_hours(cursor, {
            'schedule_id': schedule_id, 'date': assignment_date, 'shift_type_id': shift_type_id,
            'start_time': start_time, 'end_time': end_time,
        })
        if new_start and new_end:
            total_minutes += shift_duration_minutes(new_start, new_end)
```

4. **Ruhezeit** (`app.py:1768-1796`): die eigene Schicht wie unter 3.; für die beiden Nachbarn die Abfrage um die neuen Spalten erweitern und `assignment_hours(cursor, neighbor)` statt der Schichtart-Abfrage benutzen:

```python
            query = ('SELECT id, schedule_id, date, shift_type_id, start_time, end_time '
                     'FROM shift_assignments WHERE employee_id = ? AND date = ?')
```

und danach

```python
            n_start, n_end = assignment_hours(cursor, neighbor)
            if not n_start or not n_end:
                continue
```

- [ ] **Schritt 6: `fetch_schedule()` unangetastet lassen**

`fetch_schedule()` löst die Zeiten heute über einen vorab geladenen Override-Dict auf, um N+1-Abfragen zu vermeiden. Das ist richtig so und wird in **Aufgabe 3** angepasst, nicht hier. Fass es in dieser Aufgabe nicht an.

- [ ] **Schritt 7: Gesamte Suite laufen lassen**

```bash
cd backend && ./venv/Scripts/python -m pytest -q
cd backend && ./venv/Scripts/python -W error::DeprecationWarning -m pytest -q
```

**Alle bestehenden Tests müssen unverändert grün sein.** Das ist der eigentliche Beweis dieser Aufgabe: eine Umstrukturierung, die das Verhalten nicht ändert. Wird hier etwas rot, ist die Zusammenführung falsch, nicht der Test.

- [ ] **Schritt 8: Commit**

```bash
git add backend/app.py backend/test_api_assignment_times.py
git commit -m "refactor: Zeitaufloesung einer Zuweisung an einer Stelle buendeln"
```

---

## Aufgabe 3: Die Ansicht zeigt die tatsächlichen Zeiten

**Files:**
- Modify: `backend/app.py` (`fetch_schedule`)
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Consumes: `assignment_hours()` aus Aufgabe 2
- Produces: `fetch_schedule()` liefert pro Zuweisung zusätzlich `assignment_time_set` (bool) und liefert Zeilen mit `shift_type_id IS NULL`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_plan_zeigt_die_individuelle_zeit_statt_der_schichtart(client, hr_login):
    """Ben steht mit seinen eigenen Zeiten im Plan, seine Kollegin mit denen der Schichtart."""


def test_block_ohne_vorlage_erscheint_im_plan(client, hr_login):
    """Vor dieser Aenderung fiel er durch den inneren JOIN heraus - lautlos.

    Aufbau: ein regulaerer Platz und ein freier Block am selben Datum. Geprueft
    wird, dass BEIDE zurueckkommen; ohne den LEFT JOIN kaeme nur der regulaere,
    und ein Test, der nur den freien Block zaehlt, koennte das nicht von
    "gar nichts geladen" unterscheiden.
    """


def test_freier_block_hat_keinen_schichtartnamen_aber_eine_zeit(client, hr_login):
    """shift_type_name ist None, start_time/end_time sind gefuellt."""
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Erwartet: der freie Block fehlt in `assignments`, und die individuelle Zeit wird von der Schichtart-Zeit überschrieben.

- [ ] **Schritt 3: Die Abfrage umstellen**

In `fetch_schedule()` (`app.py:1274-1299`):

```python
    cursor.execute('''
        SELECT sa.id, sa.date, sa.shift_type_id, sa.slot_index, sa.employee_id, sa.manually_edited,
               sa.absence_type, sa.absent_employee_id, sa.start_time, sa.end_time,
               st.name AS shift_type_name, st.color AS shift_type_color,
               st.start_time AS type_start_time, st.end_time AS type_end_time,
               e.name AS employee_name, ae.name AS absent_employee_name
        FROM shift_assignments sa
        LEFT JOIN shift_types st ON st.id = sa.shift_type_id
        LEFT JOIN employees e ON e.id = sa.employee_id
        LEFT JOIN employees ae ON ae.id = sa.absent_employee_id
        WHERE sa.schedule_id = ?
        ORDER BY sa.date, COALESCE(sa.start_time, st.start_time), sa.slot_index
    ''', (schedule['id'],))
```

Zwei Dinge sind hier absichtlich anders als bisher:

- Die Schichtart-Zeiten heißen jetzt `type_start_time`/`type_end_time`, damit sie nicht mit den Zuweisungszeiten kollidieren, die unter `start_time`/`end_time` aus derselben Zeile kommen. **Ohne diese Umbenennung liefern beide Dialekte stillschweigend unterschiedliche Werte** — welche Spalte bei doppeltem Namen gewinnt, ist nicht garantiert.
- `ORDER BY` sortiert nach der tatsächlich früheren Zeit, mit `COALESCE`, damit ein freier Block ohne Schichtart nicht ans Ende rutscht.

Die Schleife darunter:

```python
    assignments = []
    for row in cursor.fetchall():
        a = dict(row)
        a['manually_edited'] = bool(a['manually_edited'])
        # Three layers, outermost first: this assignment's own hours, then a
        # per-date override for the shift type, then the type's usual hours.
        # The flags tell the browser which layer won, so it can mark a cell
        # that deviates without re-deriving the rule.
        override = overrides.get((a['date'], a['shift_type_id']))
        a['default_start_time'] = a['type_start_time']
        a['default_end_time'] = a['type_end_time']
        a['assignment_time_set'] = bool(a['start_time'] and a['end_time'])
        a['time_overridden'] = override is not None
        if not a['assignment_time_set']:
            if override:
                a['start_time'] = override['start_time']
                a['end_time'] = override['end_time']
            else:
                a['start_time'] = a['type_start_time']
                a['end_time'] = a['type_end_time']
        del a['type_start_time'], a['type_end_time']
        assignments.append(a)
```

**Achte auf die Bedeutung von `time_overridden`:** es sagt weiterhin „für dieses Datum und diese Schichtart existiert ein Override", nicht „diese Zuweisung weicht ab". Das Frontend nutzt es heute genau so (`ShiftCell.jsx:71,86-90`). Die neue Abweichung heißt `assignment_time_set` und ist ein eigenes Feld — vermische die beiden nicht.

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

- [ ] **Schritt 5: Gesamte Suite**

Beide Läufe grün und warnungsfrei, `test_scheduler.py` unverändert.

- [ ] **Schritt 6: Commit**

```bash
git add backend/app.py backend/test_api_assignment_times.py
git commit -m "feat: Plan liefert die tatsaechlichen Zeiten und Bloecke ohne Vorlage"
```

---

## Aufgabe 4: Die Warnungen kommen mit fehlender Schichtart klar

**Files:**
- Modify: `backend/app.py` (`constraint_warnings`, `add_slot`, `effective_shift_hours`)
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Consumes: `assignment_hours()` aus Aufgabe 2, die umgestellte Abfrage aus Aufgabe 3
- Produces: keine neue Signatur

Aufgabe 2 hat die Zeitauflösung gebündelt. Was bleibt, sind die Stellen, die `shift_type_id` für etwas **anderes** als Zeiten benutzen und dabei annehmen, dass es nie NULL ist.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_freier_block_loest_keine_schichtart_warnung_aus(client, hr_login):
    """Ein Mitarbeiter mit eingeschraenkten Schichtarten darf auf einen Block ohne Vorlage.

    Diskriminierung: derselbe Mitarbeiter bekommt im selben Test auf einer
    NICHT erlaubten Schichtart sehr wohl die Warnung. Ohne diesen Gegenpart
    wuerde der Test auch dann gruen sein, wenn die Pruefung komplett fehlte.
    """


def test_freier_block_zaehlt_in_die_wochenstunden(client, hr_login):
    """Er ist Arbeitszeit wie jede andere - der alte innere JOIN haette ihn verschluckt."""


def test_freier_block_zaehlt_in_die_ruhezeit(client, hr_login):
    """Ein Block 22:00-06:00 am Vortag muss die Ruhezeitwarnung ausloesen."""


def test_zweiter_freier_block_am_selben_tag_bekommt_den_naechsten_platz(client, hr_login):
    """add_slot mit shift_type_id NULL: 'WHERE shift_type_id = NULL' trifft nichts,
    der zweite Block bekaeme sonst wieder slot_index 0 und liefe in den
    UNIQUE-Index."""
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

- [ ] **Schritt 3: Die Schichtart-Prüfung überspringen, wenn es keine gibt**

In `constraint_warnings()` (`app.py:1687-1691`):

```python
    # A block without a template isn't any shift type, so a restriction on
    # which types this person may work has nothing to say about it.
    if shift_type_id is not None:
        cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
        if cursor.fetchone():
            cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ? AND shift_type_id = ?',
                           (employee_id, shift_type_id))
            if not cursor.fetchone():
                warnings.append(t(g.lang, 'warn_restricted_shift_types', name=employee['name']))
```

- [ ] **Schritt 4: `effective_shift_hours()` gegen NULL absichern**

Die Funktion wird von `assignment_hours()` nur noch mit einer echten Schichtart gerufen, ist aber weiterhin öffentlich im Modul. Ein Wächter am Anfang kostet nichts und verhindert, dass ein künftiger Aufrufer eine Abfrage absetzt, die per Konstruktion nie trifft:

```python
def effective_shift_hours(cursor, schedule_id, iso_date, shift_type_id, default_start, default_end):
    """A shift type's actual hours on one date: a per-date override if one exists, else its usual hours.

    For an assignment, prefer assignment_hours() - it puts the assignment's own
    times in front of these two layers.
    """
    if shift_type_id is None:
        return default_start, default_end
```

- [ ] **Schritt 5: `add_slot()` für Blöcke ohne Vorlage**

In `add_slot()` (`app.py:1590-1605`) sind zwei Stellen betroffen. Die Existenzprüfung darf NULL durchlassen, und die `MAX(slot_index)`-Abfrage braucht `IS NULL` statt `= ?`:

```python
    if shift_type_id is not None:
        cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
        if not cursor.fetchone():
            return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    # "WHERE shift_type_id = NULL" matches nothing in SQL - not even the NULL
    # rows - so a block without a template would keep getting slot_index 0 and
    # collide with the unique index on its second insert.
    if shift_type_id is None:
        cursor.execute(
            'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
            'WHERE schedule_id = ? AND date = ? AND shift_type_id IS NULL',
            (schedule_id, iso_date))
    else:
        cursor.execute(
            'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
            'WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
            (schedule_id, iso_date, shift_type_id))
    next_index = cursor.fetchone()['highest'] + 1
```

Ein freier Block, der über `add_slot` entsteht, **muss** Zeiten mitbringen. Die Validierung dafür schreibt Aufgabe 5; hier reicht es, `start_time`/`end_time` aus dem Body entgegenzunehmen und mit einzufügen.

- [ ] **Schritt 6: Test laufen lassen, Erfolg bestätigen**

- [ ] **Schritt 7: Gesamte Suite und Commit**

```bash
git add backend/app.py backend/test_api_assignment_times.py
git commit -m "feat: Warnungen und Platzvergabe kommen ohne Schichtart aus"
```

---

## Aufgabe 5: Zeiten über die API setzen

**Files:**
- Modify: `backend/app.py` (`update_assignment`, `swap_assignments`, `replacement_suggestions`, `add_slot`), `backend/i18n.py`
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Consumes: `assignment_hours()`, die erweiterte `constraint_warnings()`-Signatur aus Aufgabe 2
- Produces: `PUT /assignments/<id>` nimmt optional `start_time`/`end_time`

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_zeiten_setzen_speichert_und_warnt_bei_bedarf(client, hr_login):
    """Die Zuweisung wird gespeichert (200) und die Warnung bezieht sich auf die NEUE Zeit.

    Aufbau: Anna hat ein Fenster 08:00-14:00 und steht auf der Frueh-schicht
    06:00-14:00, also bereits ausserhalb. Wird die Zuweisung auf 09:00-13:00
    gesetzt, muss die Warnung VERSCHWINDEN - das beweist, dass die Pruefung mit
    der neuen Zeit rechnet und nicht mit der der Schichtart.
    """


def test_halb_gefuelltes_zeitpaar_ist_400(client, hr_login):
    """start_time ohne end_time - kein stilles Halb-Interpretieren."""


def test_zeiten_zuruecksetzen_faellt_auf_die_schichtart_zurueck(client, hr_login):
    """Beide Felder explizit null -> die Zuweisung erbt wieder."""


def test_block_ohne_vorlage_ohne_zeiten_ist_400(client, hr_login):
    """Er hat nichts, von dem er erben koennte."""


def test_ungueltiges_zeitformat_ist_400(client, hr_login):
    """'25:00' und 'abends' - beide mit der uebersetzten Meldung, nicht nur mit dem Status."""
```

Der letzte Test prüft die **Meldung**, nicht nur den Status. In Etappe 1 wurden zwei Tests zurückgestellt, die nur den Status prüften; mach diesen Fehler nicht noch einmal.

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

- [ ] **Schritt 3: Meldungsschlüssel ergänzen**

In `backend/i18n.py`, im Stil der vorhandenen Einträge, `de` und `en` mit echten Umlauten:

```python
    'assignment_time_invalid': {
        'de': 'Ungültige Uhrzeit "{value}". Erwartet wird HH:MM.',
        'en': 'Invalid time "{value}". Expected HH:MM.',
    },
    'assignment_times_need_both': {
        'de': 'Start- und Endzeit müssen zusammen gesetzt oder zusammen leer sein.',
        'en': 'Start and end time must be set together or left empty together.',
    },
    'assignment_without_shift_type_needs_times': {
        'de': 'Ein Block ohne Schichtart braucht eigene Zeiten — er hat keine Vorlage, von der er sie erben könnte.',
        'en': 'A block without a shift type needs its own hours — it has no template to inherit them from.',
    },
```

Sieh nach, ob `availability_time_invalid` aus Etappe 1 dasselbe leistet wie `assignment_time_invalid`. Wenn ja, **nimm den vorhandenen Schlüssel** und lege keinen zweiten mit identischem Text an.

- [ ] **Schritt 4: Validierung und Speichern in `update_assignment()`**

```python
def parse_assignment_times(data):
    """The optional start/end pair from a request body, validated as a pair.

    Returns (start, end) with both set or both None. Raises ValueError with a
    translated message otherwise - the caller turns that into a 400, the same
    way replace_employee_constraints does.
    """
    start_time = data.get('start_time') or None
    end_time = data.get('end_time') or None

    if (start_time is None) != (end_time is None):
        raise ValueError(t(g.lang, 'assignment_times_need_both'))
    for value in (start_time, end_time):
        if value is not None and not is_valid_time(value):
            raise ValueError(t(g.lang, 'assignment_time_invalid', value=value))
    return start_time, end_time
```

`is_valid_time()` existiert bereits in `app.py` (es wird von der Fenster-Validierung aus Etappe 1 benutzt) — such es und benutze es, statt eine zweite Formatprüfung zu schreiben. Findest du keine, benutze dieselbe Prüfung, die `replace_employee_constraints()` verwendet.

In `update_assignment()` danach:

```python
    try:
        start_time, end_time = parse_assignment_times(data)
    except ValueError as err:
        return jsonify({'message': str(err)}), 400

    if assignment['shift_type_id'] is None and start_time is None:
        return jsonify({'message': t(g.lang, 'assignment_without_shift_type_needs_times')}), 400

    warnings = constraint_warnings(
        cursor, employee_id, assignment['date'], assignment['shift_type_id'], assignment['schedule_id'],
        exclude_assignment_id=assignment_id, start_time=start_time, end_time=end_time,
    )

    cursor.execute(
        'UPDATE shift_assignments SET employee_id = ?, start_time = ?, end_time = ?, manually_edited = 1 '
        'WHERE id = ?',
        (employee_id, start_time, end_time, assignment_id))
```

**Achtung, bewusste Entscheidung:** die Zeiten werden bei jedem `PUT` mitgeschrieben, auch wenn der Aufrufer sie weglässt — dann auf NULL. Das ist konsistent mit `employee_id`, das dieselbe „was nicht gesendet wird, gilt als leer"-Semantik hat und dessen Kommentar (`app.py:1817-1820`) genau das begründet. Schreib diese Konsequenz als Kommentar dazu, damit ein späterer Leser sie nicht für ein Versehen hält: **wer nur den Mitarbeiter tauschen will, muss die Zeiten mitschicken.** Das Frontend in Aufgabe 6 tut das.

- [ ] **Schritt 5: `swap_assignments()` und `replacement_suggestions()` durchreichen**

Beide rufen `constraint_warnings()` und müssen die Zeiten der jeweiligen Zuweisung mitgeben, sonst prüfen sie gegen die Schichtart-Zeit statt gegen die tatsächliche:

```python
    warnings += constraint_warnings(cursor, b['employee_id'], a['date'], a['shift_type_id'], a['schedule_id'],
                                    exclude_assignment_id=a['id'],
                                    start_time=a['start_time'], end_time=a['end_time'])
```

Beim Tausch bleiben die Zeiten am **Platz**, nicht an der Person — getauscht werden die Mitarbeiter, nicht die Blöcke. Ändere daran nichts.

In `replacement_suggestions()` analog mit `assignment['start_time']`/`assignment['end_time']`.

- [ ] **Schritt 6: `add_slot()` abschließen**

Dieselbe Validierung, und die Zeiten mit einfügen:

```python
    if shift_type_id is None and start_time is None:
        return jsonify({'message': t(g.lang, 'assignment_without_shift_type_needs_times')}), 400
```

- [ ] **Schritt 7: Test laufen lassen, gesamte Suite, Commit**

```bash
git add backend/app.py backend/i18n.py backend/test_api_assignment_times.py
git commit -m "feat: individuelle Zeiten ueber die API setzen"
```

---

## Aufgabe 6: Frontend

**Files:**
- Modify: `frontend/src/components/ShiftCell.jsx`, `frontend/src/components/ScheduleGrid.jsx`, `frontend/src/components/CalendarView.jsx`, `frontend/src/i18n/translations.js`, ggf. `frontend/src/App.css`
- Nicht anfassen: Backend

Es gibt weiterhin **keine Frontend-Testinfrastruktur, und in dieser Aufgabe kommt keine dazu.** Verifikation ist `npm run lint`, `npm run build` und das tatsächliche Bedienen der Oberfläche.

- [ ] **Schritt 1: Zeiten pro Person anzeigen**

`ShiftCell.jsx` zeigt heute **ein** Zeitpaar für die ganze Zelle (`sample = sorted[0]`, Zeile 44 und 86-91) — der Kommentar oben in der Datei begründet das ausdrücklich: „if the early shift finishes early on one day it finishes early for everyone on it". Diese Annahme trägt ab jetzt nicht mehr.

Neue Aufteilung:

- Die **Zellenzeile** oben zeigt weiterhin die Zeit der Schicht an diesem Datum (Stufe 2 bzw. 3) und behält den vorhandenen Bearbeiten-Knopf für den Datums-Override. Sie ändert sich nicht.
- Jede **Personenzeile** (`AssignmentSlot`) zeigt zusätzlich ihre eigene Zeit — **aber nur, wenn `slot.assignment_time_set` wahr ist.** Sonst bliebe dieselbe Zeit sinnlos in jeder Zeile stehen.

- [ ] **Schritt 2: Zeiten pro Person bearbeiten**

In `AssignmentSlot` ein Bearbeiten-Knopf neben dem vorhandenen `✎`-Muster der Zelle. Aufgeklappt zwei `<input type="time">`, „OK" und — wenn `assignment_time_set` — ein „Standard"-Knopf, der beide Felder auf `null` setzt und die Zuweisung damit wieder erben lässt. Genau dasselbe Muster, das die Zelle für den Datums-Override schon hat (`ShiftCell.jsx:60-84`); folge ihm, erfinde keinen zweiten Stil.

Gespeichert wird über den vorhandenen `onReassign`-Weg, der `PUT /assignments/<id>` ruft. **Wichtig:** dieser Aufruf muss ab jetzt `start_time` und `end_time` mitschicken, auch wenn nur der Mitarbeiter gewechselt wird — die Route schreibt beide Felder bei jedem `PUT`, und ein Aufruf ohne sie würde die individuellen Zeiten stillschweigend löschen. Sieh dir `SchedulePage.jsx` an, wo `onReassign` definiert ist, und erweitere die Signatur so, dass der aktuelle Stand der Zeiten immer mitgeht.

Das ist der Punkt, an dem diese Aufgabe am ehesten still kaputtgeht. Prüf ihn in der laufenden Oberfläche ausdrücklich: individuelle Zeit setzen, danach **nur** den Mitarbeiter wechseln, neu laden — die Zeit muss noch da sein.

- [ ] **Schritt 3: Blöcke ohne Vorlage darstellen**

`ScheduleGrid.jsx` gruppiert nach `shift_type_id` (Zeile 35-36) und rendert eine Spalte je Schichtart. Ein Block mit `shift_type_id === null` fällt heute in eine Gruppe mit dem Schlüssel `null` und hat keine Spalte.

Gib ihm eine: eine zusätzliche, letzte Spalte, die nur erscheint, wenn es an mindestens einem Tag des Monats einen solchen Block gibt. Überschrift aus `translations.js` (`schedule.freeBlockColumn`, `de: "Dienst"`, `en: "Shift"`), neutrale Farbe statt `shift_type_color`.

`CalendarView.jsx` gruppiert dynamisch (Zeile 80-81) und braucht nur zwei Rückfallwerte: `slots[0].shift_type_name` ist `null` → derselbe Text, und `slots[0].shift_type_color` ist `null` → eine neutrale Farbe aus dem Stylesheet.

**Eine Schaltfläche zum Anlegen eines freien Blocks kommt hier nicht dazu.** Sie steht nicht im Umfang dieser Etappe; erzeugt werden solche Blöcke erst vom Planer in Etappe 4.

- [ ] **Schritt 4: Texte**

Alle neuen Zeichenketten in `frontend/src/i18n/translations.js`, `de` und `en`, mit echten Umlauten. In Etappe 0 war eine Meldung transliteriert und fiel erst im Review auf.

- [ ] **Schritt 5: Lint, Build, Durchstich, Commit**

```bash
cd frontend && npm run lint && npm run build
```

Starte beide Server und bediene die Oberfläche:

```bash
cd backend && ./venv/Scripts/python app.py
cd frontend && npm run dev
```

Diese Durchstiche willst du selbst gesehen haben:

1. Einer Person auf einer Schicht eigene Zeiten geben, speichern, neu laden — nur ihre Zeile zeigt die neue Zeit, die Kollegin auf derselben Schicht die alte.
2. Bei derselben Person **nur** den Mitarbeiter wechseln, neu laden — die individuelle Zeit steht noch.
3. „Standard" drücken, neu laden — die Zeile erbt wieder die Zeit der Schicht.
4. Den Datums-Override der ganzen Zelle ändern — die Person mit eigener Zeit bleibt davon unberührt, alle anderen ziehen mit.

**Am Ende trennen, was tatsächlich ausgeführt und gesehen wurde, von dem, was nur durchdacht ist.** Eine ehrliche Lücke ist in Ordnung; eine behauptete Verifikation, die nicht stattgefunden hat, ist der schwerste Fehler.

```bash
git commit -m "feat: individuelle Zeiten pro Person in der Planansicht"
```

---

## Aufgabe 7: Dokumentation

**Files:** `README.md`, `docs/HANDOFF.md`

- [ ] **Schritt 1:** Im Abschnitt zum Planer bzw. zur Planansicht die **Vorrangregel** beschreiben: eigene Zeiten der Zuweisung, sonst Datums-Override der Schicht, sonst die übliche Zeit der Schichtart. Mit dem Grund, warum es drei Stufen sind und nicht zwei — die mittlere gilt für alle auf der Schicht, die obere für genau eine Person.

- [ ] **Schritt 2:** Blöcke ohne Schichtart erklären: dass sie existieren können, eigene Zeiten tragen **müssen**, in den Ansichten neutral erscheinen — und dass sie in dieser Etappe noch von niemandem erzeugt werden. Das Datenmodell geht dem Planer voraus, weil Etappe 4 sonst Schema und Algorithmus gleichzeitig ändern müsste.

- [ ] **Schritt 3:** Die Roadmap fortschreiben: Etappe 2 ist erledigt, als Nächstes kommen Öffnungszeiten und Bedarf auf der Zeitachse, danach der Zuschnitt.

- [ ] **Schritt 4:** `docs/HANDOFF.md` auf den neuen Stand bringen — Statustabelle, abgeschlossene Etappe, und die Warnung aus dem Etappe-1-Handoff **entfernen**, dass `constraint_warnings()` nicht-nullbare Schichtzeiten voraussetzt: genau das hat diese Etappe behoben.

- [ ] **Schritt 5: Commit**

```bash
git add README.md docs/HANDOFF.md
git commit -m "docs: individuelle Zuweisungszeiten beschreiben"
```

---

## Abnahme für Etappe 2

- [ ] Alle vier CI-Jobs grün, inklusive `backend-postgres`
- [ ] Die 23 Tests in `backend/test_scheduler.py` unverändert und grün
- [ ] Suite warnungsfrei unter `-W error::DeprecationWarning`
- [ ] `migrations.py status` zeigt `0005` als angewandt, und der Rundlauf up → down → up läuft durch
- [ ] Eine Zuweisung ohne eigene Zeiten verhält sich exakt wie vor dieser Etappe — dieselbe Anzeige, dieselben Warnungen
- [ ] Eine Zuweisung mit eigenen Zeiten wird in Anzeige, Wochenstunden, Ruhezeit und Fensterprüfung mit **diesen** Zeiten gerechnet
- [ ] Ein Block mit `shift_type_id IS NULL` lässt sich anlegen, erscheint im Plan, zählt in die Wochenstunden und löst keine Schichtart-Warnung aus
- [ ] Ein Wechsel des Mitarbeiters über die Oberfläche löscht die individuellen Zeiten nicht
- [ ] Ein halb gefülltes Zeitpaar und ein vorlagenloser Block ohne Zeiten werden mit 400 und übersetzter Meldung abgelehnt
