# Etappe 1 — Arbeitszeitfenster: Umsetzungsplan

**Ziel:** Mitarbeiter bekommen echte Uhrzeiten statt nur Wochentags- und Schichtart-Listen. „Anna arbeitet Mo–Fr von 08:00 bis 14:00" wird ausdrückbar, und der Planer respektiert es.

**Architektur:** Eine neue Tabelle `employee_availability` und ein Schalter `employees.availability_mode`. Der Planer bekommt eine zusätzliche Prüfung in `structurally_eligible()`; sein Suchkern bleibt unverändert. Kein Umbau des Schichtart-Modells — das kommt erst in Etappe 3.

**Tech-Stack:** Flask 3.1, SQLite lokal + Postgres in Produktion, React 19 + Vite, pytest 9.

**Spec:** [`docs/entwuerfe/2026-08-16-zeitachsen-dienstplan-design.md`](../specs/2026-08-16-zeitachsen-dienstplan-design.md), Abschnitte 4.4, 4.5 und Etappe 1.

## Globale Rahmenbedingungen

- **Keine neuen Abhängigkeiten**, weder Laufzeit (aktuell fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata) noch Frontend.
- **Alle 66 bestehenden Tests bleiben grün und warnungsfrei**, auch unter `-W error::DeprecationWarning`. Die 23 Tests in `backend/test_scheduler.py` bleiben zusätzlich **unverändert** — sie sind die Rückwärtskompatibilitätsgarantie.
- **Alle vier CI-Jobs müssen grün bleiben**, insbesondere `backend-postgres`.
- **Jede nutzersichtbare Meldung zweisprachig** — Backend über `backend/i18n.py` und `t(g.lang, key)`, Frontend über `frontend/src/i18n/translations.js`. Nie ein Literal.
- **Migrationen:** Datei muss `NNNN_name.sql` heißen (`0004_...`), ein abweichender Name wirft. **Kein literales `?` in SQL, auch nicht in Kommentaren** — die Dialektschicht ersetzt es bedingungslos durch `%s`. Das hat in Etappe 0 bereits einen Produktionsausfall verursacht.
- Wochentagskonvention: 0 = Montag … 6 = Sonntag.
- Zeiten sind `"HH:MM"`-Strings. `end <= start` bedeutet Überschreitung nach Mitternacht.
- **Sprache: der Datei folgen, die du anfasst.** Das Projekt ist hier gemischt, und das ist keine Nachlässigkeit, sondern Geschichte: die ursprünglichen Dateien (`scheduler.py`, `test_scheduler.py`, `app.py`, `db.py`) haben durchgehend englische Kommentare, die in Etappe 0 hinzugekommenen (`security.py`, `timeutil.py`, `migrations.py` und die neuen Testdateien) deutsche. Neue Dateien deshalb auf Deutsch, Ergänzungen in bestehenden englischen Dateien auf Englisch. Eine einzelne Datei in zwei Sprachen zu führen ist das einzige, was hier wirklich falsch ist — das Abschluss-Review von Etappe 0 hat genau diese Vermischung als Mangel notiert. Dokumentation (README) bleibt durchgehend Englisch, Commit-Nachrichten durchgehend Deutsch.
- Commit-Nachrichten auf Deutsch, Präfix `feat:`, `fix:`, `test:`, `chore:` oder `docs:`.
- Jede Aufgabe endet mit genau einem Commit und grüner CI.

## Die zentrale Semantik — einmal präzise, gilt für alle Aufgaben

**Der Modus-Schalter.** `employees.availability_mode` ist `'anytime'` (Standard) oder `'windows'`.

- `'anytime'`: alles wie heute. Keine Uhrzeit-Einschränkung. `unavailable_weekdays` und `unavailable_dates` gelten unverändert.
- `'windows'`: die Person ist **nur** innerhalb ihrer eingetragenen Fenster verfügbar. Ein Wochentag ohne Fenster heißt: an diesem Tag gar nicht. `unavailable_dates` und `employee_absences` gelten zusätzlich obendrauf und können nie etwas erlauben, sondern nur verbieten.

Der Schalter ist absichtlich explizit. Ohne ihn wäre „hat keine Fenster" mehrdeutig — überall verfügbar oder nirgends? — und jeder bestehende Datensatz müsste geraten werden.

**Die Enthaltensein-Prüfung.** Eine Schicht ist erlaubt, wenn sie **vollständig** in *ein* Fenster passt. Nicht teilweise — Teilabdeckung kommt erst in Etappe 4.

Gerechnet wird in Minuten ab Mitternacht des **Starttags**, mit derselben Mitternachtskonvention wie `shift_duration_minutes()`:

```
schicht_start = minuten(S)
schicht_ende  = minuten(E) + (1440 wenn E <= S sonst 0)
fenster_start = minuten(WS)
fenster_ende  = minuten(WE) + (1440 wenn WE <= WS sonst 0)

erlaubt  <=>  fenster_start <= schicht_start  und  schicht_ende <= fenster_ende
```

Beispiele, die alle als Tests auftauchen müssen:

| Fenster | Schicht | Ergebnis | warum |
|---|---|---|---|
| 08:00–14:00 | 08:00–14:00 | erlaubt | exakt gleich |
| 08:00–14:00 | 09:00–13:00 | erlaubt | echt enthalten |
| 08:00–14:00 | 06:00–14:00 | **verboten** | beginnt zu früh |
| 08:00–14:00 | 08:00–16:00 | **verboten** | endet zu spät |
| 08:00–14:00 | 22:00–06:00 | **verboten** | Nachtschicht, [1320,1800] ⊄ [480,840] |
| 20:00–06:00 | 22:00–06:00 | erlaubt | Fenster überschreitet Mitternacht mit |
| 20:00–06:00 | 19:00–23:00 | **verboten** | beginnt vor dem Fenster |

**Mehrere Fenster pro Wochentag** sind erlaubt (geteilter Dienst 08:00–12:00 **und** 16:00–20:00). Die Schicht muss in *mindestens eines* passen — nicht in die Vereinigung. Eine Schicht 11:00–17:00 passt bei diesen beiden Fenstern in keines und ist verboten, auch wenn sie „zusammen" abgedeckt wäre.

**Gültigkeitszeitraum.** `valid_from` und `valid_until` sind ISO-Daten oder `NULL` (unbegrenzt). Ein Fenster gilt für ein Slot-Datum `d`, wenn `(valid_from is NULL or valid_from <= d)` und `(valid_until is NULL or d <= valid_until)`. Beide Grenzen sind **einschließlich**.

**Der Wochentag eines Fensters ist der des Schichtbeginns**, auch bei Nachtschichten. Eine Schicht am Freitag 22:00–06:00 wird gegen die Freitagsfenster geprüft, nicht gegen die des Samstags.

## Dateistruktur

| Datei | Verantwortung | Aufgabe |
|---|---|---|
| `backend/migrations/0004_employee_availability.sql` | Tabelle + Spalte | 1 |
| `backend/migrations/0004_employee_availability.down.sql` | Rücknahme | 1 |
| `backend/test_migrations.py` | Migrationstests ergänzen | 1 |
| `backend/test_migrations_postgres.py` | Postgres-Gegenprobe | 1 |
| `backend/scheduler.py` | Fensterprüfung in der Eignung | 2 |
| `backend/test_scheduler_windows.py` | **neu** — Tests der Fensterlogik | 2 |
| `backend/app.py` | Serialisierung, Schreibpfad, Ladefunktion, Warnungen | 3, 4 |
| `backend/i18n.py` | neue Meldungen | 3, 4 |
| `backend/test_api_availability.py` | **neu** — API-Tests | 3, 4 |
| `frontend/src/pages/Employees.jsx` | Fenster-Editor | 5 |
| `frontend/src/i18n/translations.js` | Texte | 5 |
| `README.md` | Feature-Beschreibung | 6 |

---

## Aufgabe 1: Migration und Schema

**Files:**
- Create: `backend/migrations/0004_employee_availability.sql`, `.down.sql`
- Modify: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`

**Interfaces:**
- Consumes: der Migrations-Runner aus Etappe 0
- Produces: Tabelle `employee_availability`, Spalte `employees.availability_mode`

- [ ] **Schritt 1: Tests schreiben**

In `backend/test_migrations.py` beim Tabellen-Literal die neue Tabelle ergänzen — **beachte:** dieses Literal ist bewusst fest verdrahtet und darf **nicht** wieder aus der Migrationsdatei abgeleitet werden, sonst wird der Test tautologisch (das war ein Befund aus Etappe 0).

Neue Tests:

```python
def test_availability_mode_hat_anytime_als_standard(fresh_db):
    """Bestandsdaten muessen unveraendert gueltig bleiben."""
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute("INSERT INTO employees (name) VALUES ('Anna')")
        connection.commit()
        modus = connection.execute(
            'SELECT availability_mode FROM employees WHERE name = ?', ('Anna',)).fetchone()[0]
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
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

`cd backend && ./venv/Scripts/python -m pytest test_migrations.py` — beide neuen Tests müssen scheitern, weil Tabelle und Spalte fehlen. Prüfe, dass der Fehler „no such table/column" lautet und nicht etwas anderes.

- [ ] **Schritt 3: Migration schreiben**

`backend/migrations/0004_employee_availability.sql`:

```sql
-- Arbeitszeitfenster: "Anna kann montags 08:00-14:00".
--
-- Mehrere Zeilen pro (employee_id, weekday) sind erlaubt und beschreiben
-- einen geteilten Dienst. Eine Schicht muss vollstaendig in EIN Fenster
-- passen, nicht in die Vereinigung mehrerer.
--
-- end_time <= start_time bedeutet Ueberschreitung nach Mitternacht, wie
-- ueberall sonst im Projekt (siehe scheduler.shift_duration_minutes).
--
-- valid_from/valid_until sind ISO-Daten oder NULL fuer unbegrenzt, beide
-- Grenzen einschliesslich. Damit laesst sich "ab September gilt etwas
-- anderes" abbilden, ohne die alte Zeile zu verlieren.
CREATE TABLE IF NOT EXISTS employee_availability(
    id {auto_id},
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT
);

CREATE INDEX IF NOT EXISTS ix_availability_employee
    ON employee_availability(employee_id, weekday);

-- 'anytime' = wie bisher, keine Uhrzeit-Einschraenkung. 'windows' = nur
-- innerhalb der Fenster oben. Der Schalter ist absichtlich explizit: ohne
-- ihn waere "hat keine Fenster" mehrdeutig, und jeder Bestandsdatensatz
-- muesste geraten werden. Der Standard haelt alle vorhandenen Mitarbeiter
-- unveraendert gueltig.
ALTER TABLE employees ADD COLUMN availability_mode TEXT NOT NULL DEFAULT 'anytime'
```

`backend/migrations/0004_employee_availability.down.sql`:

```sql
DROP INDEX IF EXISTS ix_availability_employee;
DROP TABLE IF EXISTS employee_availability
```

> **Zur Rücknahme:** Die Spalte `availability_mode` wird bewusst **nicht** entfernt. SQLite kann `DROP COLUMN` erst ab 3.35 und auch dann nicht in jeder Situation; eine zurückgebliebene Spalte mit sinnvollem Standard ist harmlos, ein gescheitertes Rückrollen nicht. Schreibe das als Kommentar in die Down-Datei.

- [ ] **Schritt 4: Postgres-Gegenprobe**

In `backend/test_migrations_postgres.py` einen Test ergänzen, der belegt, dass die Migration auch dort durchläuft und `availability_mode` den Standard trägt. Orientiere dich an den vorhandenen Tests derselben Datei.

- [ ] **Schritt 5: Suite und CI**

Voller Lauf, dann pushen und die vier CI-Jobs abwarten.

- [ ] **Schritt 6: Commit**

```bash
git add backend/migrations/0004_employee_availability.sql backend/migrations/0004_employee_availability.down.sql backend/test_migrations.py backend/test_migrations_postgres.py
git commit -m "feat: Schema fuer Arbeitszeitfenster"
```

---

## Aufgabe 2: Fensterprüfung im Planer

Der Kern der Etappe. Reine Funktionen, keine Datenbank — hier entscheidet sich die Korrektheit.

**Files:**
- Modify: `backend/scheduler.py`
- Create: `backend/test_scheduler_windows.py`

**Interfaces:**
- Produces:
  - `scheduler.time_to_minutes(hhmm: str) -> int`
  - `scheduler.window_contains_shift(window: dict, start_time: str, end_time: str) -> bool`
  - `structurally_eligible()` berücksichtigt zusätzlich `employee['availability_mode']` und `employee['availability']`
- Das Employee-Dictionary bekommt zwei neue Schlüssel:
  - `availability_mode`: `'anytime'` oder `'windows'`
  - `availability`: Liste von `{'weekday': int, 'start_time': str, 'end_time': str, 'valid_from': str|None, 'valid_until': str|None}`

**Rückwärtskompatibilität, zwingend:** Fehlen beide Schlüssel, muss sich alles verhalten wie heute. Die 23 unveränderten Scheduler-Tests liefern sie nicht — sie sind der Beweis. Nutze `employee.get('availability_mode', 'anytime')`.

- [ ] **Schritt 1: Tests schreiben**

`backend/test_scheduler_windows.py` — decke jede Zeile der Tabelle aus „Die zentrale Semantik" oben ab, plus:

```python
def test_ohne_modus_verhaelt_sich_alles_wie_bisher():
    """Ein Mitarbeiter-Dict ohne die neuen Schluessel darf nie eingeschraenkt werden."""

def test_anytime_ignoriert_vorhandene_fenster():
    """Wer auf 'anytime' steht, ist auch dann frei, wenn Fenster eingetragen sind -
    der Schalter entscheidet, nicht die Anwesenheit von Zeilen."""

def test_windows_ohne_fenster_fuer_diesen_wochentag_verbietet():
    """Kein Fenster am Dienstag heisst dienstags gar nicht."""

def test_zwei_fenster_am_selben_tag_schicht_muss_in_eines_passen():
    """08:00-12:00 und 16:00-20:00; eine Schicht 11:00-17:00 passt in keines,
    obwohl sie von der Vereinigung ueberdeckt waere."""

def test_gueltigkeitszeitraum_grenzen_sind_einschliessend():
    """valid_from == Slotdatum und valid_until == Slotdatum gelten beide noch."""

def test_nachtschicht_wird_gegen_den_wochentag_des_beginns_geprueft():
    """Freitag 22:00-06:00 gegen Freitagsfenster, nicht gegen Samstag."""

def test_slot_ohne_zeiten_wird_nicht_eingeschraenkt():
    """build_slots() setzt start_time/end_time auf None, wenn die Schichtart
    keine Zeiten hat. Dann gibt es nichts zu pruefen - so wie die
    Ruhezeit-Pruefung es auch haelt."""
```

Der letzte ist wichtig: `build_slots()` erlaubt `start_time=None`, und die bestehende Ruhezeitprüfung behandelt das als „nichts zu prüfen". Die Fensterprüfung muss sich genauso verhalten, sonst brechen die 23 alten Tests.

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

Erwartet: `ImportError`/`AttributeError` für die neuen Funktionen.

- [ ] **Schritt 3: Implementieren**

In `backend/scheduler.py`, bei den übrigen Zeit-Hilfsfunktionen:

```python
def time_to_minutes(hhmm):
    """Minuten seit Mitternacht fuer "HH:MM"."""
    stunden, _, minuten = hhmm.partition(':')
    return int(stunden) * 60 + int(minuten)


def window_contains_shift(window, start_time, end_time):
    """Passt die Schicht vollstaendig in dieses eine Fenster?

    Vollstaendig, nicht teilweise: Teilabdeckung ist Etappe 4. Gerechnet wird
    in Minuten ab Mitternacht des Starttags, mit derselben
    Mitternachtskonvention wie shift_duration_minutes() - ein Ende kleiner
    oder gleich dem Start liegt am Folgetag und bekommt 1440 aufgeschlagen.
    Dadurch vergleicht sich eine Nachtschicht korrekt mit einem Fenster, das
    Mitternacht ebenfalls ueberschreitet.
    """
    schicht_start = time_to_minutes(start_time)
    schicht_ende = time_to_minutes(end_time)
    if schicht_ende <= schicht_start:
        schicht_ende += 24 * 60

    fenster_start = time_to_minutes(window['start_time'])
    fenster_ende = time_to_minutes(window['end_time'])
    if fenster_ende <= fenster_start:
        fenster_ende += 24 * 60

    return fenster_start <= schicht_start and schicht_ende <= fenster_ende
```

Und in `structurally_eligible()`, **nach** den bestehenden Prüfungen und vor `return True`:

```python
    if employee.get('availability_mode') == 'windows':
        # Ohne bekannte Schichtzeiten gibt es nichts zu pruefen - dieselbe
        # Haltung wie bei der Ruhezeit (siehe rest_period_ok).
        if slot.get('start_time') and slot.get('end_time'):
            passende = [
                fenster for fenster in employee.get('availability', ())
                if fenster['weekday'] == slot['weekday']
                and window_is_valid_on(fenster, slot['date'])
            ]
            if not any(window_contains_shift(f, slot['start_time'], slot['end_time'])
                       for f in passende):
                return False
```

Dazu die Gültigkeitsprüfung:

```python
def window_is_valid_on(window, iso_date):
    """Gilt dieses Fenster an diesem Datum? Beide Grenzen einschliesslich.

    Reiner Zeichenkettenvergleich - ISO-Daten sortieren lexikographisch
    korrekt, und die Grenzen kommen aus derselben Quelle wie das Slotdatum.
    """
    gueltig_ab = window.get('valid_from')
    gueltig_bis = window.get('valid_until')
    if gueltig_ab and iso_date < gueltig_ab:
        return False
    if gueltig_bis and iso_date > gueltig_bis:
        return False
    return True
```

- [ ] **Schritt 4: Grün, plus die 23 alten Tests**

`cd backend && ./venv/Scripts/python -m pytest` — die 23 Scheduler-Tests **müssen** unverändert grün sein. Werden sie rot, ist der Rückwärtskompatibilitätspfad falsch, nicht der Test.

- [ ] **Schritt 5: Commit**

```bash
git add backend/scheduler.py backend/test_scheduler_windows.py
git commit -m "feat: Planer respektiert Arbeitszeitfenster"
```

---

## Aufgabe 3: API — Fenster lesen und schreiben

**Files:**
- Modify: `backend/app.py` (`serialize_employee`, `replace_employee_constraints`, `create_employee`, `update_employee`, `load_employees_for_scheduling`)
- Modify: `backend/i18n.py`
- Create: `backend/test_api_availability.py`

**Interfaces:**
- `GET /employees` und `GET /employees/<id>` liefern zusätzlich `availability_mode` und `availability`
- `POST /employees` und `PUT /employees/<id>` nehmen beide entgegen; `availability` **ersetzt komplett**, wie die übrigen Constraint-Listen
- `load_employees_for_scheduling()` liefert beide Felder an den Planer

- [ ] **Schritt 1: Tests schreiben**

`backend/test_api_availability.py`, mit der `hr_client`-Fixture. Deckung:

- Anlegen ohne die neuen Felder → `availability_mode == 'anytime'`, `availability == []` (Bestandsverhalten)
- Anlegen mit Fenstern → kommen zurück, sortiert nach Wochentag und Startzeit
- `PUT` ersetzt die Fensterliste vollständig, entfernt also weggelassene
- Ungültiger Modus → 400 mit übersetzter Meldung
- `weekday` außerhalb 0–6 → 400
- Ungültige Uhrzeit (`"25:00"`, `"8:00"`, `"abc"`) → 400
- `valid_until` vor `valid_from` → 400
- Nicht-HR-Konto → 403
- Ein Ende gleich dem Start (`22:00`–`22:00`) → **400**: das wäre nach der Mitternachtsregel ein 24-Stunden-Fenster und ist mit hoher Wahrscheinlichkeit ein Tippfehler. Lieber ablehnen als still etwas Absurdes speichern.

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

- [ ] **Schritt 3: Meldungen ergänzen**

In `backend/i18n.py`:

```python
    'availability_mode_invalid': {
        'de': 'Unbekannter Verfügbarkeitsmodus. Erlaubt sind "anytime" und "windows".',
        'en': 'Unknown availability mode. Allowed values are "anytime" and "windows".',
    },
    'availability_time_invalid': {
        'de': 'Ungültige Uhrzeit "{value}". Erwartet wird HH:MM.',
        'en': 'Invalid time "{value}". Expected HH:MM.',
    },
    'availability_window_empty': {
        'de': 'Start- und Endzeit eines Fensters dürfen nicht gleich sein.',
        'en': 'A window\'s start and end time must differ.',
    },
    'availability_valid_range_invalid': {
        'de': 'Das Gültigkeitsende darf nicht vor dem Gültigkeitsbeginn liegen.',
        'en': 'The validity end date must not be before its start date.',
    },
```

- [ ] **Schritt 4: `app.py` erweitern**

`serialize_employee()` um die Fensterabfrage ergänzen (`ORDER BY weekday, start_time`) und beide Felder in das zurückgegebene Dictionary aufnehmen.

`replace_employee_constraints()` um einen Block für `availability` ergänzen — löschen und neu einfügen, wie die übrigen Listen es tun. Validiere dabei jeden Eintrag und wirf `ValueError` mit der passenden übersetzten Meldung; die aufrufenden Routen fangen das bereits ab und antworten mit 400.

Für die Zeitprüfung ist `valid_time()` bereits in `app.py` vorhanden — nutze sie, statt eine zweite zu schreiben.

`create_employee()` und `update_employee()` müssen `availability_mode` schreiben; validiere gegen `('anytime', 'windows')`.

`load_employees_for_scheduling()` muss beide Felder mitliefern, damit Aufgabe 2 überhaupt wirkt.

- [ ] **Schritt 5: Suite, CI, Commit**

```bash
git commit -m "feat: Arbeitszeitfenster ueber die API pflegen"
```

---

## Aufgabe 4: Warnung bei Handkorrektur

Der Planer verbietet; die Handkorrektur warnt nur. Das ist die durchgehende Haltung des Projekts — HR darf immer übersteuern, aber nie versehentlich.

**Files:**
- Modify: `backend/app.py` (`constraint_warnings`), `backend/i18n.py`, `backend/test_api_availability.py`

- [ ] **Schritt 1: Test schreiben**

Ein Mitarbeiter im `windows`-Modus wird per `PUT /assignments/<id>` auf eine Schicht außerhalb seines Fensters gesetzt. Erwartet: **200** (die Zuweisung greift) **und** eine Warnung in `warnings`, die den Namen und die Fensterzeiten nennt. Zusätzlich: derselbe Fall im `anytime`-Modus erzeugt **keine** Warnung.

- [ ] **Schritt 2: Meldung ergänzen**

```python
    'warn_outside_availability': {
        'de': '{name} arbeitet {weekday} normalerweise nur {windows}.',
        'en': '{name} normally only works {weekday} {windows}.',
    },
```

`{windows}` ist die zusammengesetzte Liste der Fenster dieses Wochentags, z.B. `08:00–14:00`, oder bei mehreren `08:00–12:00, 16:00–20:00`. Gibt es für den Wochentag gar kein Fenster, brauchst du eine zweite Meldung — formuliere sie so, dass sie nicht behauptet, es gäbe Zeiten.

- [ ] **Schritt 3: In `constraint_warnings()` einbauen**

Nutze die tatsächlichen Zeiten der Zuweisung, also `effective_shift_hours()` — dieselbe Funktion, die die Ruhezeitprüfung schon verwendet, damit eine per Datum überschriebene Uhrzeit korrekt berücksichtigt wird.

- [ ] **Schritt 4: Suite, CI, Commit**

---

## Aufgabe 5: Frontend

**Files:**
- Modify: `frontend/src/pages/Employees.jsx`, `frontend/src/i18n/translations.js`

- [ ] **Schritt 1: Umschalter**

Im Mitarbeiterformular eine Auswahl zwischen „Immer verfügbar" und „Feste Zeiten". Im `anytime`-Modus bleibt das Formular wie heute; im `windows`-Modus erscheint der Fenster-Editor und die Wochentags-Auswahl „arbeitet nicht an" wird ausgeblendet — im Fenster-Modus ist sie redundant und ihre Anwesenheit würde verwirren.

- [ ] **Schritt 2: Fenster-Editor**

Ein Raster über die sieben Wochentage. Pro Tag beliebig viele Zeilen mit Von- und Bis-Feld (`<input type="time">`) und einer Entfernen-Schaltfläche. Ein „Fenster hinzufügen" pro Tag. Optional pro Fenster zwei Datumsfelder für den Gültigkeitszeitraum, eingeklappt, weil sie der Sonderfall sind.

- [ ] **Schritt 3: In der Liste anzeigen**

Bei Mitarbeitern im Fenster-Modus ein Abzeichen mit den Zeiten, so wie es die übrigen Constraints bereits machen.

- [ ] **Schritt 4: Texte**

Alle neuen Zeichenketten in beiden Sprachen, mit Umlauten — in Etappe 0 war eine Meldung transliteriert und fiel erst im Review auf.

- [ ] **Schritt 5: Lint, Build, Commit**

Es gibt weiterhin keine Frontend-Testinfrastruktur. Sie kommt **nicht** in dieser Aufgabe dazu. Am Ende festhalten, was tatsächlich verifiziert und was nur durchdacht ist; beide Server zu starten und die Oberfläche zu bedienen gehört ausdrücklich dazu — in Etappe 0 wurde der schwerwiegendste Frontend-Fehler genau so gefunden.

---

## Aufgabe 6: Dokumentation

**Files:** `README.md`

- [ ] Den Abschnitt zur Mitarbeiterverwaltung um die Fenster erweitern, mit der Erklärung, wie sich die beiden Modi unterscheiden und warum die Prüfung „vollständig enthalten" ist und nicht „überlappt".
- [ ] Im Abschnitt zum Planer ergänzen, dass Fenster eine harte Bedingung sind, Handkorrekturen aber nur warnen.
- [ ] Die Roadmap aktualisieren: Öffnungszeiten und Bedarf auf der Zeitachse sind Etappe 3, der Zuschnitt Etappe 4.
- [ ] Commit `docs: Arbeitszeitfenster im README beschreiben`

---

## Abnahme für Etappe 1

- [ ] Alle vier CI-Jobs grün, inklusive `backend-postgres`
- [ ] Die 23 Tests in `backend/test_scheduler.py` unverändert und grün
- [ ] Suite warnungsfrei unter `-W error::DeprecationWarning`
- [ ] Ein Mitarbeiter im `anytime`-Modus verhält sich exakt wie vor dieser Etappe
- [ ] „Anna, Mo–Fr 08:00–14:00" lässt sich anlegen, und der Planer setzt sie auf keine Schicht, die darüber hinausgeht
- [ ] Eine Handkorrektur außerhalb des Fensters ist möglich und warnt dabei
- [ ] `migrations.py status` zeigt `0004` als angewandt
