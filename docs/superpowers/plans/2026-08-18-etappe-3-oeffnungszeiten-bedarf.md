# Etappe 3 — Öffnungszeiten und Bedarf auf der Zeitachse: Umsetzungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe abzuarbeiten. Die Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Ziel:** Der Betrieb bekommt einen Rahmen und eine Bedarfskurve. Öffnungszeiten sagen, wann überhaupt gearbeitet wird; `coverage_requirements` sagt, wie viele Leute zu welcher Tageszeit da sein sollen — nicht mehr „montags braucht die Frühschicht 3 Leute", sondern „montags 08:00–12:00 zwei, 12:00–17:00 drei". Und der Plan meldet **Deckungslücken** auf der Zeitachse statt nur einer Zahl unbesetzter Schichten.

**Architektur:** Drei neue Tabellen, zwei neue Editoren, eine neue Auswertung. **Der Planer wird nicht angefasst.** Er baut seine Slots weiterhin aus `shift_requirements`; `coverage_requirements` wird in dieser Etappe *gepflegt und ausgewertet*, aber noch nicht geplant. Das ist Absicht — siehe „Was NICHT in dieser Etappe passiert".

**Tech-Stack:** Flask 3.1, SQLite lokal + Postgres in Produktion, React 19 + Vite, pytest 9. **Neu: Vitest + Testing Library** für das Frontend (siehe Task 8).

**Spec:** [`docs/superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md`](../specs/2026-08-16-zeitachsen-dienstplan-design.md), Abschnitte 4.1–4.3, 6, 7 und „Etappe 3".

**Setzt auf:** Etappe 2 (`etappe-2-individuelle-zeiten`, PR #13). Die Deckungslücken-Rechnung braucht `assignment_hours()` aus Etappe 2 — eine Zuweisung mit eigenen Zeiten deckt genau diese Zeiten ab, nicht die der Schichtart.

## Globale Rahmenbedingungen

- **Keine neuen Laufzeitabhängigkeiten** (aktuell fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata). Im Frontend kommen in Task 8 **Entwicklungsabhängigkeiten** dazu — das ist die einzige Ausnahme und nur dort erlaubt.
- **Alle 142 bestehenden Tests bleiben grün und warnungsfrei**, auch unter `-W error::DeprecationWarning`. Die 23 Tests in `backend/test_scheduler.py` bleiben zusätzlich **unverändert** — sie sind die Rückwärtskompatibilitätsgarantie.
- **Alle CI-Jobs müssen grün bleiben**, insbesondere `backend-postgres`. Lokal läuft nur SQLite; Postgres-Verhalten nie aus SQLite schließen.
- **Jede nutzersichtbare Meldung zweisprachig** — Backend über `backend/i18n.py` und `t(g.lang, key)`, Frontend über `frontend/src/i18n/translations.js`, `de` **und** `en`, mit echten Umlauten. Nie ein Literal.
- **Kein literales `?` in SQL, auch nicht in Kommentaren** — die Dialektschicht in `db.py` ersetzt es bedingungslos durch `%s`. Das hat in Etappe 0 einen Produktionsausfall verursacht. **Semikolons in SQL-Kommentaren** zerteilen die Datei am Splitter in `migrations.py`.
- **Eine Migration muss nach ihrer eigenen Rücknahme wieder vorwärts laufen.** Alles, was nicht `IF NOT EXISTS` kann, gehört in eine `.py`-Migration mit `table_columns()`-Wächter, und jede solche Migration braucht einen Rundlauftest up → down → up. Das war der Critical aus dem Abschluss-Review von Etappe 1.
- **`WHERE spalte = ?` mit `None` trifft in SQL keine Zeile**, auch nicht die mit NULL. Das war ein Fallstrick in Etappe 2.
- Zeiten sind `"HH:MM"`-Strings. **`end <= start` bedeutet Überschreitung nach Mitternacht**, überall im Projekt.
- Wochentagskonvention: 0 = Montag … 6 = Sonntag.
- **Sprache: der Datei folgen, die du anfasst.** `app.py`, `db.py`, `scheduler.py`, `test_scheduler.py` und das Frontend sind englisch kommentiert; `security.py`, `timeutil.py`, `migrations.py`, die Migrationsdateien und die neueren Testdateien deutsch. README englisch, `docs/HANDOFF.md` deutsch.
- Commit-Nachrichten auf Deutsch, Präfix `feat:`, `fix:`, `test:`, `chore:` oder `docs:`, mit angehängtem `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Jede Aufgabe endet mit genau **einem** Commit und grüner CI.

---

## Die zentrale Semantik — einmal präzise, gilt für alle Aufgaben

### Die Minutenachse

Alles in dieser Etappe rechnet in **Minuten ab Mitternacht des Wochentags, dem die Zeile zugeordnet ist**, mit derselben Mitternachtskonvention wie überall sonst:

```
start_min = minuten(S)
end_min   = minuten(E) + (1440 wenn E <= S sonst 0)
```

Ein Band `22:00–06:00` auf `weekday = 0` (Montag) belegt damit `[1320, 1800)` und beschreibt die Nacht von Montag auf Dienstag. Das ist dieselbe Regel, die `window_contains_shift()` seit Etappe 1 benutzt — **nicht duplizieren**, sondern `scheduler.time_to_minutes()` wiederverwenden.

### `business_hours` — der Rahmen

Genau **eine Zeile pro Wochentag**, sieben insgesamt, per `UNIQUE(weekday)` erzwungen. `closed = 1` heißt geschlossen; `open_time`/`close_time` werden dann ignoriert.

**Der Standard nach der Migration ist „rund um die Uhr offen":** alle sieben Zeilen mit `open_time = '00:00'`, `close_time = '00:00'`, `closed = 0`. Nach der Minutenregel ist das `[0, 1440)` — der ganze Tag. Das ist der einzige Standard, der **kein** bestehendes Verhalten ändert: heute gibt es keine Öffnungszeiten, also darf ihre Einführung nichts verbieten, was vorher erlaubt war.

`business_hours_exceptions` schlägt für ein einzelnes Datum die Wochentagsregel, `UNIQUE(date)`.

**Öffnungszeiten sind in dieser Etappe eine Validierungsgrenze, keine Planerbedingung.** Sie beschränken, welche Bedarfsbänder gesetzt werden dürfen (siehe unten) und rahmen die Anzeige. Sie verbieten **keine** bestehende Zuweisung und lösen **keine** Warnung aus. Ein Betrieb, der heute Schichten außerhalb seiner künftigen Öffnungszeiten hat, bleibt unverändert lauffähig.

### `coverage_requirements` — der Bedarf

```
id, weekday INTEGER (0-6), start_time TEXT, end_time TEXT, required_count INTEGER
```

**Nicht überlappend, absolute Besetzungsstärke.** „08:00–12:00 → 2, 12:00–17:00 → 3" heißt: zwischen 12 und 17 sollen *insgesamt* drei Leute da sein, nicht 2+3.

Drei Regeln, die das Backend erzwingt:

1. **Bänder desselben Wochentags dürfen sich nicht überlappen** (400). Geprüft auf der Minutenachse, also inklusive der über Mitternacht gezogenen. Lücken sind erlaubt und bedeuten „kein Bedarf".
2. **Ein Band muss innerhalb der Öffnungszeit seines Wochentags liegen** (400). An einem geschlossenen Tag ist gar kein Band erlaubt.
3. `required_count >= 0`.

**Bewusst nicht geprüft: Überlappung über die Wochentagsgrenze hinweg.** Ein Band Montag 22:00–06:00 und eines Dienstag 00:00–08:00 beschreiben denselben realen Zeitraum doppelt. Das zu erkennen hieße, die Woche als einen zusammenhängenden 10080-Minuten-Ring zu behandeln — machbar, aber es macht jede Fehlermeldung schwer verständlich („Ihr Band von Dienstag kollidiert mit einem von Montag"), und der Fall entsteht nur, wenn jemand ihn absichtlich baut. Er wird als bekannte Grenze dokumentiert, nicht abgefangen.

### Die Ableitung aus dem Alten

`coverage_requirements` wird beim Aufsetzen **einmalig aus `shift_requirements` berechnet**, damit ein bestehender Betrieb nicht bei null anfängt:

Für jeden Wochentag: an jedem Zeitpunkt die Summe der `required_count` aller Schichtarten, die diesen Zeitpunkt überdecken. Aufeinanderfolgende Zeitpunkte mit gleicher Summe werden zu einem Band zusammengefasst. Summe 0 erzeugt **kein** Band.

Das Ergebnis ist per Konstruktion überlappungsfrei und bildet den bisherigen Bedarf exakt ab. Beispiel: Frühschicht 06:00–14:00 mit 2, Spätschicht 14:00–22:00 mit 3 ergibt `[06:00–14:00 → 2, 14:00–22:00 → 3]`. Überlappen sich zwei Schichtarten (Früh 06:00–14:00 mit 2, Zwischendienst 10:00–18:00 mit 1), entsteht `[06:00–10:00 → 2, 10:00–14:00 → 3, 14:00–18:00 → 1]`.

**Diese Ableitung ist eine reine Funktion und wird als solche getestet** (Task 2), bevor sie irgendetwas in die Datenbank schreibt.

### Deckungslücken

Eine Deckungslücke ist ein Zeitabschnitt eines konkreten Datums, in dem **weniger Leute eingeplant sind, als der Bedarf verlangt**.

Gerechnet wird gegen die **tatsächlichen** Zeiten der Zuweisungen — also über `assignment_hours()` aus Etappe 2, damit eine Person mit individueller Zeit genau ihre Zeit abdeckt und nicht die der Schichtart. Eine Zuweisung ohne Mitarbeiter (`employee_id IS NULL`) deckt **nichts** ab; eine, die durch eine Abwesenheit freigeworden ist, ebenso wenig.

`GET /schedules/<year>/<month>` liefert zusätzlich:

```json
"coverage_gaps": [{"date": "2026-03-17", "start_time": "12:00", "end_time": "14:00", "missing": 1}]
```

Benachbarte Abschnitte mit gleichem `missing` werden zusammengefasst. Ist der Bedarf gedeckt oder übererfüllt, entsteht kein Eintrag.

**Die Ausnahmen des Datums gelten mit:** fällt ein Datum auf einen `business_hours_exceptions`-Eintrag mit `closed = 1`, gibt es an diesem Tag keinen Bedarf und damit keine Lücke — auch wenn für den Wochentag Bänder hinterlegt sind.

---

## Was NICHT in dieser Etappe passiert

- **Der Planer bleibt unangetastet.** `build_slots()` baut weiterhin aus `shift_requirements`, `structurally_eligible()` und der Suchkern bleiben, wie sie sind. `coverage_requirements` wird gepflegt und ausgewertet, aber nicht geplant. Die Umstellung des Planers auf Bedarfsbänder ist **Etappe 4** und kommt zusammen mit dem Zuschnitt, weil beide denselben Umbau brauchen.
- **`shift_requirements` bleibt bestehen** und bleibt die Bedarfsquelle des Planers. Die Spec sieht ihre Entfernung erst nach Etappe 4 vor. Bis dahin existieren beide Modelle nebeneinander — das ist gewollt und die Rückfallebene, falls der neue Pfad Probleme macht.
- **Keine Warnung bei Zuweisungen außerhalb der Öffnungszeit.** Öffnungszeiten rahmen den Bedarf, nicht die Handkorrektur. HR bleibt der Chef; das ist die durchgehende Linie des Projekts.
- **Keine automatische Neuberechnung der Bedarfskurve**, wenn sich `shift_requirements` später ändert. Die Ableitung läuft einmalig bei der Migration. Danach ist `coverage_requirements` von Hand gepflegt — sonst hätte man zwei Quellen, die sich gegenseitig überschreiben.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `backend/migrations/0006_coverage.py` | **neu** — die drei Tabellen, die sieben `business_hours`-Standardzeilen, die einmalige Ableitung aus `shift_requirements` |
| `backend/coverage.py` | **neu** — die reine Rechenlogik: Bedarfskurve ableiten, Bänder auf Überlappung prüfen, Deckungslücken berechnen. Kein Flask, kein SQL, damit sie ohne Datenbank testbar ist |
| `backend/app.py` | die vier neuen Routengruppen, `coverage_gaps` in `fetch_schedule()` |
| `backend/i18n.py` | neue Meldungen, `de` und `en` |
| `backend/test_coverage.py` | **neu** — die reine Logik, ohne Datenbank |
| `backend/test_api_coverage.py` | **neu** — Routen, Validierung, Lücken über HTTP |
| `backend/test_migrations.py`, `test_migrations_postgres.py` | Schema, Rundlauf, die abgeleiteten Bänder |
| `frontend/src/pages/BusinessHours.jsx` | **neu** — Öffnungszeiten je Wochentag plus Ausnahmenliste |
| `frontend/src/pages/CoverageEditor.jsx` | **neu** — Bedarfsbänder als Balken über den Tag |
| `frontend/src/components/CoverageGaps.jsx` | **neu** — die Lückenliste im Plan |
| `frontend/src/i18n/translations.js`, `App.jsx`, `App.css` | Texte, Routen, Stil |
| `frontend/vitest.config.js`, `frontend/src/test/` | **neu** — Testinfrastruktur (Task 8) |
| `README.md`, `docs/HANDOFF.md` | Dokumentation |

`backend/scheduler.py` und `backend/test_scheduler.py` werden **nicht** angefasst.

---

## Die Aufgaben im Überblick

| # | Aufgabe | Warum in dieser Reihenfolge |
|---|---|---|
| 1 | Schema: die drei Tabellen | Fundament, ohne Ableitung — die kommt erst, wenn ihre Logik getestet ist |
| 2 | `coverage.py`: Bedarfskurve als reine Funktion | Muss vor der Datenmigration stehen, sonst schreibt ungetestete Logik in die Datenbank |
| 3 | Datenmigration: Ableitung anwenden | Benutzt Task 2, nachdem sie bewiesen ist |
| 4 | API: Öffnungszeiten und Ausnahmen | Unabhängig von 5, liefert aber die Grenze, die 5 prüft |
| 5 | API: Bedarfsbänder mit Validierung | Braucht die Öffnungszeiten aus 4 |
| 6 | Deckungslücken berechnen und ausliefern | Braucht 5 und `assignment_hours()` aus Etappe 2 |
| 7 | Frontend: beide Editoren | Braucht 4 und 5 |
| 8 | Vitest aufsetzen und die Editoren testen | Nach 7, damit es echte Komponenten zu testen gibt |
| 9 | Dokumentation | Zuletzt, wenn alles steht |

Jede Aufgabe bekommt ihren eigenen Task-Brief über `scripts/task-brief`. Die detaillierten Schritte je Aufgabe stehen unten.

---

## Task 1: Schema für Öffnungszeiten und Bedarf

**Files:**
- Create: `backend/migrations/0006_coverage.py`
- Modify: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`

**Interfaces:**
- Consumes: den Migrations-Runner aus Etappe 0 (`up(cursor)`/`down(cursor)`), `db.table_columns()`, `db.use_postgres()`
- Produces: die Tabellen `business_hours`, `business_hours_exceptions`, `coverage_requirements`; sieben `business_hours`-Zeilen mit dem Standard „rund um die Uhr offen"

**Diese Aufgabe legt die Tabellen an und füllt `business_hours` mit dem Standard — sie leitet noch KEINEN Bedarf ab.** Das ist Task 3, nachdem Task 2 die Rechenlogik bewiesen hat.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `backend/test_migrations.py` das fest verdrahtete Tabellen-Literal um die drei neuen Namen ergänzen — **nicht** aus den Migrationsdateien ableiten, das war ein Befund aus Etappe 0. Dazu:

```python
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


def test_bedarfsbaender_starten_leer(fresh_db):
    """Task 1 legt nur die Tabelle an. Die Ableitung ist Task 3.

    Dieser Test ist die Abgrenzung zwischen den beiden Aufgaben und darf nach
    Task 3 angepasst werden - aber bewusst und mit Begruendung, nicht nebenbei.
    """


def test_bedarfsmigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(fresh_db):
    """Rueckwaerts allein reicht nicht - die Migration muss danach wieder vorwaerts laufen.

    Vorbild: test_zeitmigration_... aus Etappe 2. Bestandszeile einfuegen, damit
    der zweite Vorwaertslauf nicht auf einer leeren Datenbank laeuft.
    """
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
cd backend && ./venv/Scripts/python -m pytest test_migrations.py -q
```

Erwartet: „no such table: business_hours" und Verwandtes. Prüfe, dass die Fehler genau das sind.

- [ ] **Schritt 3: Die Migration schreiben**

`backend/migrations/0006_coverage.py`. Sie ist eine `.py`-Migration, weil sie Zeilen einfügt und dabei wiederholbar bleiben muss. Kernpunkte, die im Code stehen müssen:

- Alle drei `CREATE TABLE` mit `IF NOT EXISTS`, `{auto_id}` selbst aufgelöst wie in `0001_baseline.py` (`_auto_id()`-Muster mit `use_postgres()`).
- `business_hours`: `weekday INTEGER NOT NULL UNIQUE`, `open_time TEXT NOT NULL`, `close_time TEXT NOT NULL`, `closed INTEGER NOT NULL DEFAULT 0`.
- `business_hours_exceptions`: `date TEXT NOT NULL UNIQUE`, `open_time TEXT`, `close_time TEXT`, `closed INTEGER NOT NULL DEFAULT 0`, `label TEXT`. Zeiten sind hier nullbar, weil ein geschlossener Feiertag keine braucht.
- `coverage_requirements`: `weekday INTEGER NOT NULL`, `start_time TEXT NOT NULL`, `end_time TEXT NOT NULL`, `required_count INTEGER NOT NULL DEFAULT 0`, plus ein Index auf `weekday`.
- **Die sieben Standardzeilen wiederholbar einfügen.** `INSERT` ist nicht idempotent — nach `down()` und erneutem `up()` stünden sonst vierzehn Zeilen da, bzw. der `UNIQUE`-Index würde werfen. Prüfe vorher, ob schon Zeilen existieren, und füge nur die fehlenden ein. Schreib den Grund als Kommentar dazu; genau dieses Muster war der Critical aus Etappe 1.

`down()`: die drei Tabellen mit `DROP TABLE IF EXISTS` zurücknehmen. Weil sie in dieser Etappe neu entstehen, ist das eine vollständige Rücknahme — anders als bei `0004` und `0005`, wo Spalten bewusst stehen blieben. Schreib auch das als Kommentar dazu, damit die Abweichung vom Muster nicht wie ein Versehen aussieht.

- [ ] **Schritt 4: Postgres-Gegenprobe**

In `backend/test_migrations_postgres.py` Entsprechungen für den Standard, die Eindeutigkeit und den Rundlauf ergänzen. Orientiere dich strikt an den vorhandenen Tests derselben Datei. **Lokal nicht ausführbar** — weise das im Bericht ehrlich als „nicht lokal verifiziert, `backend-postgres` in der CI ist die Probe" aus.

- [ ] **Schritt 5: Rot-Nachweis für die Wiederholbarkeit**

Entferne kurz die Prüfung, die doppelte Standardzeilen verhindert, lass **nur** den Rundlauftest laufen, halte die echte Ausgabe fest, stelle sie wieder her.

- [ ] **Schritt 6: Suite, CI, Commit**

```bash
git commit -m "feat: Schema fuer Oeffnungszeiten und Bedarfsbaender"
```

---

## Task 2: Die Bedarfskurve als reine Funktion

**Files:**
- Create: `backend/coverage.py`, `backend/test_coverage.py`

**Interfaces:**
- Produces:
  - `coverage_curve(shift_types)` — nimmt eine Liste von `{'start_time', 'end_time', 'required_count'}` **eines** Wochentags, liefert eine nach `start_min` sortierte, überlappungsfreie Liste von `{'start_time', 'end_time', 'required_count'}` mit `required_count > 0`
  - `bands_overlap(bands)` — `True`, wenn sich zwei Bänder derselben Liste auf der Minutenachse überschneiden
  - `band_within(band, open_time, close_time)` — liegt das Band vollständig in der Öffnungszeit?

**Warum eine eigene Datei:** diese Rechnung ist die einzige Stelle der Etappe, die man ohne Datenbank, ohne Flask und ohne HTTP vollständig durchtesten kann. Sie gehört deshalb dorthin, wo sie genau so testbar ist. `backend/scheduler.py` ist das Vorbild — auch dort steht die Rechnung getrennt von der Anbindung.

**Wiederverwenden statt nachbauen:** `scheduler.time_to_minutes()` existiert seit Etappe 1 und macht die Umrechnung inklusive Mitternachtsregel. Importiere sie. Eine zweite Umrechnung wäre genau der Fehler, den Etappe 2 an anderer Stelle beseitigt hat.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

`backend/test_coverage.py`. Diese Tests brauchen keine Fixtures — reine Funktionen, direkte Aufrufe.

```python
def test_zwei_anschliessende_schichten_ergeben_zwei_baender():
    """Der Normalfall: Frueh 06:00-14:00 mit 2, Spaet 14:00-22:00 mit 3."""
    assert coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 3},
    ]) == [
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 3},
    ]


def test_ueberlappende_schichten_werden_summiert():
    """Frueh 06:00-14:00 mit 2 und Zwischendienst 10:00-18:00 mit 1.

    Erwartet drei Baender: 06-10 zwei, 10-14 drei, 14-18 eins. Das ist der Test,
    der belegt, dass die Kurve summiert statt nebeneinanderzustellen.
    """


def test_gleiche_summe_wird_zu_einem_band_zusammengefasst():
    """Zwei anschliessende Schichten mit gleichem Bedarf ergeben EIN Band, nicht zwei.

    Ohne Zusammenfassung waere die Ausgabe zwar nicht falsch, aber die
    Ueberlappungspruefung spaeter arbeitet auf dieser Form - und ein Editor, der
    zwei Baender zeigt, wo eines gemeint ist, verwirrt.
    """


def test_nachtschicht_erzeugt_ein_band_ueber_mitternacht():
    """22:00-06:00 mit 2 ergibt genau ein Band 22:00-06:00, nicht zwei Stuecke."""


def test_bedarf_null_erzeugt_kein_band():
    """Eine Schichtart, die an diesem Wochentag niemanden braucht, taucht nicht auf."""


def test_leere_eingabe_ergibt_leere_kurve():


def test_bands_overlap_erkennt_echte_ueberschneidung():
    """08:00-12:00 und 11:00-15:00 ueberlappen. Gegenprobe: 08:00-12:00 und
    12:00-16:00 beruehren sich nur und ueberlappen NICHT - die Grenze ist
    halboffen [start, end)."""


def test_bands_overlap_erkennt_ueberschneidung_ueber_mitternacht():
    """22:00-06:00 und 05:00-08:00 ueberlappen auf der Minutenachse."""


def test_band_within_prueft_vollstaendige_enthaltung():
    """08:00-12:00 liegt in 08:00-18:00. 07:00-12:00 nicht. Gegenprobe noetig,
    sonst prueft der Test nur, dass irgendetwas True zurueckgibt."""
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Erwartet: `ModuleNotFoundError: No module named 'coverage'` — **Achtung:** es gibt ein PyPI-Paket namens `coverage`. Prüfe, dass der Fehler wirklich auf die fehlende lokale Datei zeigt und nicht versehentlich ein installiertes Paket trifft. Ist `coverage` im venv installiert, benenne das Modul in `coverage_model.py` um und passe diesen Plan im Bericht an — ein Namenskonflikt mit einem installierten Paket ist ein echter Fallstrick, kein Detail.

- [ ] **Schritt 3: Die Funktionen schreiben**

Vorgehen für `coverage_curve()`: Ereignispunkte statt Raster. Sammle alle `start_min` und `end_min` als Kandidatengrenzen, sortiere sie, und bilde für jedes Paar aufeinanderfolgender Grenzen ein Intervall. Für jedes Intervall die Summe der `required_count` aller Schichtarten, die es überdecken. Dann benachbarte Intervalle mit gleicher Summe verschmelzen und die mit Summe 0 verwerfen.

Das ist derselbe Ereignispunkt-Trick, den die Spec für Etappe 4 vorsieht — er hält die Kombinatorik klein und kommt ohne willkürliche Rasterweite aus.

Kommentarsprache: **deutsch**, wie die anderen neu angelegten Backend-Module (`security.py`, `timeutil.py`).

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

- [ ] **Schritt 5: Gesamte Suite und Commit**

```bash
git commit -m "feat: Bedarfskurve aus Schichtarten ableiten"
```

---

## Task 3: Die Ableitung anwenden

**Files:**
- Create: `backend/migrations/0007_derive_coverage.py`
- Modify: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`

**Interfaces:**
- Consumes: `coverage_curve()` aus Task 2, die Tabellen aus Task 1

**Warum eine eigene Migration statt Task 1 zu erweitern:** eine Schemamigration und eine Datenmigration haben verschiedene Risiken und verschiedene Rücknahmen. Getrennt lässt sich die Ableitung zurücknehmen, ohne die Tabellen zu verlieren — und wenn die Kurve sich als falsch herausstellt, ist das eine Zeile im Rollback statt einer Rekonstruktion.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_bedarf_wird_aus_den_schichtarten_abgeleitet(fresh_db):
    """Der eigentliche Beweis dieser Migration: dieselbe Kurve wie vorher.

    Aufbau bewusst mit ZWEI Schichtarten an DEMSELBEN Wochentag, die sich
    ueberlappen - nur so zeigt sich, ob summiert wird. Zwei sich nicht
    beruehrende Schichtarten wuerden auch bei einer falschen Implementierung
    zufaellig richtig herauskommen.

    Staffelung: bis 0006 migrieren, DANN Schichtarten und Bedarf einfuegen,
    DANN 0007 nachschieben. Andersherum prueft der Test nichts.
    """


def test_ableitung_laesst_bestehende_baender_unangetastet(fresh_db):
    """Wer schon Baender gepflegt hat, verliert sie nicht.

    Die Migration darf nur ableiten, wenn coverage_requirements leer ist.
    Sonst wuerde ein zweiter Lauf - etwa nach einem Rollback - von Hand
    gepflegte Baender ueberschreiben.
    """


def test_ableitung_ohne_schichtarten_erzeugt_nichts(fresh_db):
    """Eine frische Installation hat keine Schichtarten - und danach keinen Bedarf."""


def test_ableitungsmigration_laesst_sich_zurueckrollen_und_danach_erneut_anwenden(fresh_db):
```

- [ ] **Schritt 2: Fehlschlag bestätigen**

- [ ] **Schritt 3: Die Migration schreiben**

`up(cursor)`: für jeden Wochentag 0–6 die Schichtarten mit ihrem `required_count` dieses Wochentags laden (`shift_types` join `shift_requirements`), durch `coverage_curve()` schicken, Ergebnis einfügen.

**Zwei Punkte, die im Code stehen müssen:**

- **Nur ableiten, wenn `coverage_requirements` leer ist.** Sonst überschreibt ein zweiter Lauf von Hand gepflegte Bänder. Das ist zugleich die Wiederholbarkeit: nach `down()` und erneutem `up()` wird sauber neu abgeleitet.
- **`down()` löscht nur die Bänder**, nicht die Tabelle — die gehört Task 1.

Der Import von `coverage_curve` in einer Migration ist ungewöhnlich, aber richtig: die Alternative wäre, die Kurvenlogik in der Migration zu duplizieren, und dann driften Migration und Anwendung auseinander. Schreib den Grund als Kommentar dazu.

- [ ] **Schritt 4: Postgres-Gegenprobe, Rot-Nachweis, Suite, CI, Commit**

```bash
git commit -m "feat: bestehenden Schichtbedarf in Bedarfsbaender ueberfuehren"
```

---

## Task 4: API für Öffnungszeiten und Ausnahmen

**Files:**
- Modify: `backend/app.py`, `backend/i18n.py`
- Test: `backend/test_api_coverage.py` (neu)

**Interfaces:**
- Produces: `GET/PUT /business-hours`, `GET/POST/DELETE /business-hours/exceptions`, plus `business_hours_for(cursor, iso_date)` — liefert `(open_time, close_time, closed)` für ein Datum, Ausnahme schlägt Wochentag

Alle Schreibrouten sind `@hr_required`. `GET` ebenfalls — Öffnungszeiten sind Betriebsdaten, kein Mitarbeiterinhalt.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_oeffnungszeiten_kommen_als_sieben_zeilen(hr_client):
    """Immer sieben, immer nach Wochentag sortiert - auch frisch nach der Migration."""


def test_oeffnungszeiten_setzen_ersetzt_vollstaendig(hr_client):
    """Gleiche Semantik wie die bestehenden Constraint-Listen."""


def test_geschlossener_tag_braucht_keine_zeiten(hr_client):


def test_ausnahme_schlaegt_den_wochentag(hr_client):
    """Der 03.10. ist geschlossen, obwohl freitags offen ist.

    Geprueft ueber business_hours_for() UND ueber die Route - beide Wege muessen
    dasselbe sagen.
    """


def test_zweite_ausnahme_fuer_dasselbe_datum_ist_400(hr_client):


def test_nicht_hr_konto_bekommt_403(hr_client, employee_client):
```

- [ ] **Schritt 2 bis 5:** Fehlschlag bestätigen, Routen und `business_hours_for()` schreiben, Meldungsschlüssel in `i18n.py` (`de` und `en`, echte Umlaute), Tests grün, Suite, CI.

- [ ] **Schritt 6: Commit**

```bash
git commit -m "feat: Oeffnungszeiten und Ausnahmen ueber die API pflegen"
```

---

## Task 5: API für Bedarfsbänder

**Files:**
- Modify: `backend/app.py`, `backend/i18n.py`
- Test: `backend/test_api_coverage.py`

**Interfaces:**
- Consumes: `bands_overlap()`, `band_within()` aus Task 2, `business_hours_for()` aus Task 4
- Produces: `GET/PUT /coverage-requirements`

`PUT` nimmt die Bänder **aller** Wochentage entgegen und ersetzt den Bestand vollständig — dieselbe Semantik wie die übrigen Listen im Projekt. Das macht die Überlappungsprüfung einfach, weil sie den Endzustand sieht statt einer Folge von Einzeländerungen.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_baender_setzen_und_lesen(hr_client):


def test_ueberlappende_baender_sind_400(hr_client):
    """08:00-12:00 und 11:00-15:00 am selben Wochentag. Meldung woertlich pruefen.

    Gegenprobe im selben Test: 08:00-12:00 und 12:00-16:00 gehen durch - die
    Grenze ist halboffen. Ohne diese Haelfte wuerde der Test auch dann gruen
    sein, wenn die Pruefung jede zweite Angabe ablehnt.
    """


def test_band_ausserhalb_der_oeffnungszeit_ist_400(hr_client):
    """Oeffnung 08:00-18:00, Band 07:00-12:00. Meldung woertlich pruefen."""


def test_band_an_einem_geschlossenen_tag_ist_400(hr_client):


def test_negativer_bedarf_ist_400(hr_client):


def test_baender_verschiedener_wochentage_stoeren_sich_nicht(hr_client):
    """Montag 08:00-12:00 und Dienstag 08:00-12:00 sind beide erlaubt."""


def test_nicht_hr_konto_bekommt_403(hr_client, employee_client):
```

- [ ] **Schritt 2 bis 5:** wie gehabt.

- [ ] **Schritt 6: Commit**

```bash
git commit -m "feat: Bedarfsbaender ueber die API pflegen"
```

---

## Task 6: Deckungslücken

**Files:**
- Modify: `backend/coverage.py`, `backend/app.py`
- Test: `backend/test_coverage.py`, `backend/test_api_coverage.py`

**Interfaces:**
- Consumes: `assignment_hours()` aus Etappe 2, `business_hours_for()` aus Task 4
- Produces: `coverage_gaps(bands, covered_intervals)` in `coverage.py`; `coverage_gaps` im Ergebnis von `fetch_schedule()`

**Die Trennung ist wichtig:** die Rechnung gehört nach `coverage.py` und bekommt fertige Intervalle übergeben — sie fragt selbst keine Datenbank. `app.py` sammelt die Intervalle (über `assignment_hours()`) und reicht sie hinein. So bleibt der schwierige Teil ohne Datenbank testbar.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben — erst die reine Rechnung**

```python
def test_volle_deckung_erzeugt_keine_luecke():


def test_fehlende_person_erzeugt_eine_luecke_mit_der_richtigen_zahl():
    """Bedarf 3 von 12:00-17:00, zwei Personen da -> eine Luecke, missing = 1."""


def test_teilweise_deckung_erzeugt_nur_den_ungedeckten_abschnitt():
    """Bedarf 08:00-16:00 fuer 2, eine Person 08:00-12:00, eine 08:00-16:00
    -> Luecke nur 12:00-16:00 mit missing = 1."""


def test_benachbarte_luecken_mit_gleicher_zahl_werden_zusammengefasst():


def test_uebererfuellung_erzeugt_keine_luecke():
    """Vier Personen bei Bedarf 3 - kein Eintrag, und schon gar kein negativer."""
```

Dann die HTTP-Seite:

```python
def test_plan_meldet_deckungsluecken(hr_client):


def test_individuelle_zeit_deckt_genau_ihre_zeit_ab(hr_client):
    """Der Anschluss an Etappe 2: eine Person mit eigener Zeit 10:00-16:00 deckt
    10:00-16:00 ab, nicht die 06:00-14:00 ihrer Schichtart.

    Diskriminierung: der Bedarf ist so gelegt, dass beide Lesarten zu
    VERSCHIEDENEN Luecken fuehren. Ein Aufbau, bei dem beides dieselbe Luecke
    ergibt, prueft nichts.
    """


def test_unbesetzter_platz_deckt_nichts_ab(hr_client):


def test_geschlossener_ausnahmetag_hat_keine_luecke(hr_client):
    """Auch wenn fuer den Wochentag Baender hinterlegt sind."""
```

- [ ] **Schritt 2 bis 5:** wie gehabt. Achte darauf, dass `fetch_schedule()` durch diese Erweiterung **keine N+1-Abfragen** bekommt — die Bänder und die Öffnungszeiten werden einmal geladen, nicht pro Tag.

- [ ] **Schritt 6: Commit**

```bash
git commit -m "feat: Deckungsluecken auf der Zeitachse melden"
```

---

## Task 7: Frontend — die beiden Editoren

**Files:**
- Create: `frontend/src/pages/BusinessHours.jsx`, `frontend/src/pages/CoverageEditor.jsx`, `frontend/src/components/CoverageGaps.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/i18n/translations.js`, `frontend/src/App.css`, `frontend/src/pages/SchedulePage.jsx`

- [ ] **Schritt 1: Öffnungszeiten** — sieben Zeilen, je zwei `<input type="time">` und ein „geschlossen"-Schalter, der die Zeitfelder ausblendet. Darunter die Ausnahmenliste mit Datum, optionalem Label, Zeiten oder „geschlossen".

- [ ] **Schritt 2: Bedarfsbänder** — pro Wochentag eine Zeile mit den Bändern als Balken über den Tag. Hinzufügen, Entfernen, Von/Bis/Anzahl. **Überlappungen prüft der Browser vor dem Absenden** — das ist die eine Stelle, an der eine zweite Prüfung erwünscht ist, weil ein Balkeneditor sofort zeigen muss, dass zwei Balken kollidieren, statt es erst nach dem Speichern zu erfahren. Nutze dafür dieselbe Regel wie das Backend; **die Fehlermeldung bleibt aber die des Backends**, wenn doch etwas durchrutscht.

- [ ] **Schritt 3: Deckungslücken** — die Liste im Plan, statt nur der Zahl unbesetzter Schichten. Format „Di 17.03., 12:00–14:00: 1 Person fehlt", zweisprachig.

- [ ] **Schritt 4: Texte** in `de` und `en`, echte Umlaute, kein Literal im JSX.

- [ ] **Schritt 5: Lint, Build, Durchstich, Commit**

Starte beide Server und bediene die Oberfläche. Diese Durchstiche willst du selbst gesehen haben: Öffnungszeit ändern und neu laden; einen Tag auf geschlossen setzen und sehen, dass der Bedarfseditor dort keine Bänder mehr zulässt; zwei überlappende Bänder anlegen und die Ablehnung sehen; eine Deckungslücke im Plan erscheinen und nach dem Besetzen verschwinden sehen.

**Trenne im Bericht ausdrücklich, was du ausgeführt und gesehen hast, von dem, was du nur durchdacht hast.**

```bash
git commit -m "feat: Editoren fuer Oeffnungszeiten und Bedarf"
```

---

## Task 8: Frontend-Testinfrastruktur

**Files:**
- Create: `frontend/vitest.config.js`, `frontend/src/test/setup.js`, Tests zu den beiden Editoren
- Modify: `frontend/package.json`, `.github/workflows/ci.yml`

Das Frontend hat seit Etappe 0 **keine** Testinfrastruktur. Das war eine bewusste Entscheidung mit einem Ablaufdatum: die Spec nennt Etappe 3 als spätesten Zeitpunkt, und der Bedarfseditor mit seiner Überlappungsprüfung ist genau die Komponente, für die Klicken allein nicht mehr reicht.

- [ ] **Schritt 1:** Vitest und `@testing-library/react` als **Entwicklungsabhängigkeiten** ergänzen, gepinnt wie alles andere im Projekt. Das ist die einzige erlaubte Abhängigkeitserweiterung dieser Etappe.

- [ ] **Schritt 2:** `vitest.config.js` und ein Setup, das die `jsdom`-Umgebung und die Testing-Library-Matcher einrichtet.

- [ ] **Schritt 3:** Tests für den Bedarfseditor — der Überlappungsfall, der Grenzfall „berühren sich nur", das Hinzufügen und Entfernen eines Bandes, und dass ein geschlossener Tag keine Bänder zulässt.

- [ ] **Schritt 4:** Tests für die Öffnungszeiten — der „geschlossen"-Schalter blendet die Zeitfelder aus und löscht sie nicht.

- [ ] **Schritt 5:** `npm test` in die CI aufnehmen, als eigener Schritt im vorhandenen `frontend`-Job.

- [ ] **Schritt 6: Commit**

```bash
git commit -m "test: Frontend-Testinfrastruktur mit Vitest aufsetzen"
```

---

## Task 9: Dokumentation

**Files:** `README.md`, `docs/HANDOFF.md`

- [ ] Öffnungszeiten und Bedarfsbänder im README erklären, mit der Begründung, warum der Bedarf **absolut** ist und nicht additiv, und warum Bänder sich nicht überlappen dürfen.
- [ ] Beschreiben, dass `shift_requirements` weiterhin die Quelle des Planers ist und `coverage_requirements` in dieser Etappe nur gepflegt und ausgewertet wird — mit dem Hinweis, dass die Umstellung Etappe 4 ist. **Eine Dokumentation, die suggeriert, der Planer folge schon den Bändern, wäre irreführend.**
- [ ] Die bekannte Grenze festhalten: Überlappung über die Wochentagsgrenze hinweg wird nicht geprüft.
- [ ] Die Roadmap fortschreiben, `docs/HANDOFF.md` auf Etappe 3 bringen, die zurückgestellten Befunde ergänzen.
- [ ] Commit `docs: Oeffnungszeiten und Bedarf beschreiben`

---

## Abnahme für Etappe 3

- [ ] Alle CI-Jobs grün, inklusive `backend-postgres` und dem neuen Frontend-Testschritt
- [ ] Die 23 Tests in `backend/test_scheduler.py` unverändert und grün
- [ ] Suite warnungsfrei unter `-W error::DeprecationWarning`
- [ ] `migrations.py status` zeigt `0006` und `0007` als angewandt, beide rundlauffest
- [ ] Ein Betrieb ohne gepflegte Öffnungszeiten verhält sich exakt wie vor dieser Etappe
- [ ] Der bestehende Schichtbedarf ist als Bänder sichtbar und bildet dieselbe Kurve ab
- [ ] Überlappende Bänder und Bänder außerhalb der Öffnungszeit werden mit 400 und übersetzter Meldung abgelehnt
- [ ] Der Plan meldet Deckungslücken mit Datum, Zeitraum und fehlender Anzahl
- [ ] Eine Zuweisung mit individueller Zeit aus Etappe 2 deckt genau ihre Zeit ab
- [ ] Der Planer erzeugt unverändert dieselben Pläne wie vor dieser Etappe
