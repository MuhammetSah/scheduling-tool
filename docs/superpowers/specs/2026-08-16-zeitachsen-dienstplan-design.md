# Design: Produktionsreife + Zeitachsen-Dienstplan

**Datum:** 2026-08-16
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** Entwurf zur Review

---

## 1. Ziel

Zwei Dinge, in dieser Reihenfolge:

1. **Fundament**, damit das Projekt echten Betrieb aushält — eigene Versionierung, CI, Migrationen, Security-Härtung, Fehlerbehandlung.
2. **Zeitachsen-Modell** für die Planung: Öffnungszeiten rahmen den Betrieb, der Personalbedarf wird über den Tagesverlauf definiert, und Mitarbeiter haben eigene Arbeitszeitfenster (z.B. „immer 10:00–16:00"), die der Planer respektiert — notfalls, indem er einen Block auf das Fenster **zuschneidet**, statt die Person zu verwerfen.

Die Reihenfolge ist bewusst: Etappe 2 ändert das Datenbankschema an mehreren Stellen. Ohne Migrationssystem und laufende Tests im CI wäre das ein Blindflug.

## 2. Ausgangslage

Das bestehende Modell plant in **Slots**: `shift_requirements` sagt „montags braucht die Frühschicht 3 Leute", `build_slots()` macht daraus drei Stühle, und ein Backtracking-Suchlauf setzt Leute darauf. Die Zeiten kommen immer von der Schichtart (`shift_types.start_time/end_time`), optional pro Datum überschrieben (`shift_time_overrides`).

Verfügbarkeit kennt heute drei grobe Formen:

- `employee_unavailable_weekdays` — „nie mittwochs"
- `employee_unavailable_dates` — „am 12.03. nicht"
- `employee_allowed_shift_types` — „nur Frühschicht"

Was fehlt: **Uhrzeiten pro Mitarbeiter**. „Anna kann Mo–Fr 08:00–14:00" lässt sich nicht ausdrücken, außer man baut für jede denkbare Zeitspanne eine eigene Schichtart.

### Was gut ist und bleibt

- Der Backtracking-Kern mit Branch-and-Bound und lexikografischem Ziel (erst Lücken, dann Fairness) ist solide und gemessen gut. Er wird **nicht** ersetzt.
- Ruhezeit-Prüfung inkl. Mitternachtsüberschreitung ist korrekt.
- „Warnung statt Verbot" bei Handkorrekturen — HR bleibt der Chef. Das ist auch der Industriestandard (Papershift erlaubt Admins ausdrücklich, über Verfügbarkeiten hinweg zu planen).
- Rollentrennung HR / Mitarbeiter wird serverseitig durchgesetzt, nicht nur per ausgeblendetem Button.
- Einladungs-Flow: niemand setzt das Passwort eines anderen.

## 3. Referenz: wie andere Tools es lösen

Recherchiert bei Papershift und Deputy:

| Aspekt | Branchenüblich | Heute im Tool |
|---|---|---|
| Schicht als Objekt | Frei anlegbar mit eigenen Zeiten; „Frühschicht" ist eine **Vorlage** | Schichtart **ist** die Struktur |
| Verfügbarkeit | Zeitfenster von–bis, als wiederkehrende Serie, binär (kann/kann nicht) | Wochentag- und Schichtart-Listen, keine Uhrzeit |
| Zuschnitt | **Passiert nicht automatisch** — Konflikt wird angezeigt, Mensch legt passende Schicht an | Entfällt |
| Bedarf über den Tag | „demand-based scheduling": Bedarfskurve → Schichtvorschläge, Reste als „Open Shifts" | Anzahl pro Schichtart pro Wochentag |
| Öffnungszeiten | Eigenes Konzept, rahmt Ansicht und Validierung | Existiert nicht |

**Unser Alleinstellungsmerkmal:** der automatische Zuschnitt. Anna deckt von der Frühschicht 06:00–14:00 eben nur 08:00–14:00 ab, der Rest bleibt als *benannte* Lücke stehen. Andere Tools verlangen dafür Handarbeit.

## 4. Datenmodell

### 4.1 Neu: `business_hours` (Öffnungszeiten)

```
id, weekday INTEGER (0-6), open_time TEXT, close_time TEXT, closed INTEGER DEFAULT 0
UNIQUE(weekday)
```

Genau eine Zeile pro Wochentag. `closed = 1` heißt geschlossen (`open_time`/`close_time` werden dann ignoriert). `close_time <= open_time` bedeutet — wie überall im Projekt — Überschreitung nach Mitternacht.

### 4.2 Neu: `business_hours_exceptions` (Feiertage, Sonderöffnungszeiten)

```
id, date TEXT, open_time TEXT, close_time TEXT, closed INTEGER, label TEXT
UNIQUE(date)
```

Schlägt für dieses eine Datum die Wochentagsregel.

### 4.3 Neu: `coverage_requirements` (Bedarf auf der Zeitachse)

```
id, weekday INTEGER (0-6), start_time TEXT, end_time TEXT, required_count INTEGER
```

**Semantik: nicht überlappend, absolute Besetzungsstärke.** „08:00–12:00 → 2, 12:00–17:00 → 3, 17:00–22:00 → 2" heißt: zwischen 12 und 17 sollen *insgesamt* drei Leute da sein, nicht 2+3. Überlappende Bänder werden vom Backend abgelehnt (400), Lücken sind erlaubt (= kein Bedarf). Bänder müssen innerhalb der Öffnungszeit liegen.

Diese Tabelle löst `shift_requirements` als Bedarfsquelle ab. `shift_requirements` bleibt bis einschließlich Etappe 3 bestehen und wird erst nach Etappe 4 entfernt — bis dahin ist sie die Rückfallebene, falls der neue Pfad Probleme macht.

**Migration aus dem Alten:** Für jeden Wochentag wird aus den bestehenden Schichtarten eine Bedarfskurve gerechnet (an jedem Zeitpunkt: Summe der `required_count` aller Schichtarten, die diesen Zeitpunkt überdecken). Aufeinanderfolgende Zeitpunkte mit gleicher Summe werden zu einem Band zusammengefasst. Das Ergebnis ist per Konstruktion überlappungsfrei und bildet den bisherigen Bedarf exakt ab.

### 4.4 Neu: `employee_availability` (Arbeitszeitfenster)

```
id, employee_id, weekday INTEGER (0-6), start_time TEXT, end_time TEXT,
valid_from TEXT NULL, valid_until TEXT NULL
```

Mehrere Fenster pro Wochentag sind erlaubt (geteilter Dienst: 08:00–12:00 **und** 16:00–20:00). `valid_from`/`valid_until` erlauben „ab September gilt etwas anderes"; `NULL` heißt unbegrenzt.

### 4.5 Geändert: `employees`

```
+ availability_mode TEXT NOT NULL DEFAULT 'anytime'   -- 'anytime' | 'windows'
```

Ein expliziter Schalter statt einer impliziten Regel:

- **`'anytime'`** (Standard, heutiges Verhalten): keine Uhrzeit-Einschränkung. `unavailable_weekdays` und `unavailable_dates` gelten wie bisher.
- **`'windows'`**: die Person ist **nur** in ihren eingetragenen Fenstern verfügbar. Ein Wochentag ohne Fenster bedeutet: an diesem Tag gar nicht. `unavailable_dates` und `employee_absences` gelten zusätzlich obendrauf.

Warum explizit: Ohne Schalter wäre „hat keine Fenster" mehrdeutig — überall verfügbar oder nirgends? Der Schalter macht das eindeutig und hält alle bestehenden Datensätze unverändert gültig.

`employee_unavailable_weekdays` bleibt bestehen und gilt in beiden Modi. Im `windows`-Modus ist es redundant, aber harmlos; die Oberfläche blendet es dann aus.

### 4.6 Geändert: `shift_assignments`

```
+ start_time TEXT NULL
+ end_time   TEXT NULL
  shift_type_id → wird NULLABLE
```

- `start_time`/`end_time` `NULL` = erbt wie bisher von der Schichtart plus etwaigem `shift_time_overrides`-Eintrag. **Alle bestehenden Zeilen bleiben damit unverändert korrekt.**
- Gefüllt = individuelle Zeiten genau dieser Person auf diesem Platz. Das ist die Schlüsseländerung: Ben steht als 10:00–16:00 im Plan.
- `shift_type_id` wird nullable, damit es freie Blöcke ohne Vorlage geben kann. Diese erscheinen als „Dienst"/„Shift" in neutraler Farbe. Die betroffenen `JOIN shift_types` in `fetch_schedule()` und `constraint_warnings()` werden zu `LEFT JOIN`; ein Block ohne Vorlage **muss** eigene Zeiten tragen (per CHECK bzw. Anwendungsvalidierung).

### 4.7 Indizes und Constraints (Etappe 0)

```sql
CREATE INDEX ix_assignments_date_employee ON shift_assignments(date, employee_id);
CREATE INDEX ix_assignments_schedule      ON shift_assignments(schedule_id);
CREATE INDEX ix_absences_date             ON employee_absences(date);
CREATE UNIQUE INDEX ux_assignment_slot
    ON shift_assignments(schedule_id, date, shift_type_id, slot_index);
```

Der UNIQUE-Index setzt voraus, dass `shift_type_id` nicht NULL ist — für nullable Spalten behandelt Postgres NULLs als verschieden. Deshalb kommt er in Etappe 0 (vor der Nullable-Änderung) und wird in Etappe 2 durch eine passendere Variante ersetzt: `(schedule_id, date, COALESCE(shift_type_id, 0), slot_index)`.

## 5. Der Planer

Der Umbau ist **zweistufig**, damit der bewährte Suchkern erhalten bleibt.

### Stufe 1 — Blockplanung (neu, deterministisch)

Eingabe: Bedarfsbänder eines Tages, Öffnungszeit, die Arbeitszeitfenster aller aktiven Mitarbeiter.
Ausgabe: eine feste Liste von Blöcken mit konkreten Start-/Endzeiten — strukturell genau das, was `build_slots()` heute liefert, nur mit variablen Zeiten.

Ablauf:

1. **Kandidatengrenzen sammeln.** Alle Bandgrenzen, Öffnungszeiten, Vorlagen-Zeiten und Fenstergrenzen aller Mitarbeiter dieses Wochentags bilden die Menge möglicher Blockgrenzen. Das ist der klassische Ereignispunkt-Trick: er hält die Kombinatorik klein, statt ein 15-Minuten-Raster durchzuprobieren.
2. **Mit Vorlagen decken.** Zuerst wird versucht, den Bedarf mit den vorhandenen Schichtvorlagen zu decken, sofern sie in die Öffnungszeit passen. Das ist der Normalfall und ergibt genau das erwartete „2 früh, 3 mittags, 2 spät".
3. **Zuschneiden statt verwerfen.** Wo ein Vorlagenblock von keinem verfügbaren Mitarbeiter ganz abgedeckt werden kann, wird er an Kandidatengrenzen auf den größten Schnitt mit einem Mitarbeiterfenster gekürzt. Der ungedeckte Rest wandert als eigener Block zurück in die Warteschlange.
4. **Mindestblocklänge.** Ein Zuschnitt unter `MIN_BLOCK_MINUTES` (Standard 180, konfigurierbar) wird nicht erzeugt — sonst entstehen 30-Minuten-Schnipsel, die niemand arbeiten will. Bleibt dadurch Bedarf offen, ist das eine reguläre gemeldete Lücke.
5. **Restbedarf** ohne passende Vorlage wird als freier Block (`shift_type_id = NULL`) erzeugt.

Stufe 1 ordnet **keine Personen zu**. Sie beantwortet nur: „welche Blöcke muss dieser Tag haben?"

### Stufe 2 — Besetzung (bestehend, minimal erweitert)

Der vorhandene Backtracking-Suchlauf bleibt unverändert in Struktur, Fairness-Ziel, Branch-and-Bound und Notbremse. Zwei Erweiterungen:

- `structurally_eligible()` prüft zusätzlich: liegt der Block bei `availability_mode = 'windows'` vollständig in einem gültigen Fenster der Person?
- Ruhezeit, Wochenstunden und Monatslimit rechnen mit den **tatsächlichen** Blockzeiten statt mit denen der Schichtart. Das ist größtenteils schon so — `slot['start_time']`/`duration_minutes` existieren bereits, sie werden nur anders befüllt.

### Ergebnis-Meldung

Statt „3 Slots unbesetzt" meldet der Planer künftig zusätzlich **Deckungslücken auf der Zeitachse**: „Di 17.03., 12:00–14:00: 1 Person fehlt". Das ist für HR deutlich handlungsfähiger und fällt bei Stufe 1 ohnehin ab.

## 6. API

Neu:

| Methode | Route | Zweck |
|---|---|---|
| GET/PUT | `/business-hours` | Öffnungszeiten aller sieben Wochentage lesen/setzen |
| GET/POST/DELETE | `/business-hours/exceptions` | Feiertage und Sonderöffnungszeiten |
| GET/PUT | `/coverage-requirements` | Bedarfsbänder pro Wochentag |
| GET/PUT | `/employees/<id>/availability` | Arbeitszeitfenster einer Person |

Geändert:

- `PUT /employees/<id>` nimmt zusätzlich `availability_mode` und `availability` entgegen (gleiche „ersetzt komplett"-Semantik wie die bestehenden Constraint-Listen).
- `PUT /assignments/<id>` nimmt optional `start_time`/`end_time` entgegen.
- `GET /schedules/<year>/<month>` liefert zusätzlich `coverage_gaps: [{date, start_time, end_time, missing}]`.
- Alle Verfügbarkeits-Verstöße erscheinen in `constraint_warnings()` als nicht-blockierende Warnung, in beiden Sprachen.

Alle neuen Schreibrouten sind `@hr_required`. `GET /employees/<id>/availability` folgt der `require_self_or_hr`-Regel, damit ein Mitarbeiter seine eigenen Zeiten einsehen kann.

## 7. Frontend

| Seite | Änderung |
|---|---|
| **Neu: `BusinessHours.jsx`** | Öffnungszeiten pro Wochentag + Ausnahmenliste |
| **Neu: `CoverageEditor.jsx`** | Bedarfsbänder als Balken über den Tag, pro Wochentag; validiert Überlappungen im Browser |
| **`Employees.jsx`** | Umschalter „immer verfügbar / feste Zeiten"; im Fenster-Modus ein Wochenraster mit Von–Bis-Feldern, mehrere Fenster pro Tag, optionale Gültigkeit von/bis |
| **`ShiftCell.jsx`** | Zeigt die tatsächlichen Zeiten der Zuweisung; HR kann sie direkt für diese eine Person ändern |
| **`CalendarView.jsx`** | Blöcke mit ihren echten Zeiten; Deckungslücken als eigene Markierung |
| **`SchedulePage.jsx`** | Lückenliste („12:00–14:00 fehlt 1 Person") statt nur einer Zahl |

Alle neuen Texte kommen in `frontend/src/i18n/translations.js` und `backend/i18n.py` — deutsch und englisch, wie bisher.

## 8. Fehlerbehandlung

- **Validierung** (Etappe 0): ein globaler Flask-Errorhandler gibt für jede unbehandelte Exception JSON zurück statt Flasks HTML-500. Heute erzeugt das im Frontend die irreführende Meldung „unerwartete Antwort".
- **Neue Validierungen:** überlappende Bedarfsbänder, Bedarf außerhalb der Öffnungszeit, Fenster mit `end <= start` ohne Mitternachtsabsicht, Zuweisungszeiten außerhalb der Öffnungszeit → jeweils 400 mit übersetzter Meldung.
- **Planer:** die bestehende Notbremse (300.000 Knoten / 8 s) bleibt. Stufe 1 bekommt eine eigene, deutlich kleinere Schranke, damit sie den Suchlauf nicht auffrisst.
- **Migration:** jede Alembic-Revision braucht ein funktionierendes `downgrade()`.

## 9. Tests

| Ebene | Was |
|---|---|
| **Scheduler** (`test_scheduler.py`, bestehend) | Alle 23 Tests müssen unverändert grün bleiben — sie sind die Rückwärtskompatibilitätsgarantie |
| **Scheduler** (neu) | Fenster-Filter; Zuschnitt bei Teilüberdeckung; Mindestblocklänge greift; freier Block bei fehlender Vorlage; Bedarfskurve über Mitternacht; korrekte Lückenmeldung |
| **Bedarfsmigration** (neu) | `shift_requirements` → `coverage_requirements` erzeugt dieselbe Kurve |
| **API** (neu, fehlt komplett) | pytest + Flask-Testclient: Rollentrennung, Validierungen, Absenz-Flow, neue Routen |
| **Frontend** (neu, fehlt komplett) | Vitest + Testing Library für den Verfügbarkeits-Editor und den Bedarfs-Editor |
| **Benchmark** | Ein Szenario mit Zeitfenstern ergänzen, um zu belegen, dass Zuschnitt Lücken schließt |

Vorgehen: **erst der Test, dann der Code.** Jede Etappe endet grün im CI.

## 10. Etappen

Jede Etappe bekommt ihren **eigenen Umsetzungsplan** und wird abgeschlossen (grün im CI, lauffähig) bevor die nächste beginnt. Dieses Dokument ist die gemeinsame Klammer, nicht ein einziger Arbeitsauftrag.

### Etappe 0 — Fundament

1. Eigenes Git-Repository mit `.gitignore` und erstem Commit
2. Abhängigkeiten pinnen (`flask==…` statt `flask`), Python-Version festlegen
3. CI: GitHub Actions — pytest, eslint, `npm run build` bei jedem Push
4. Alembic einführen, `init_db()` durch Migrationen ablösen
5. `SECRET_KEY` in Produktion erzwingen (Abbruch statt Fallback); Rate-Limit auf `/login` und `/invitations/<token>`; Security-Header
6. Globaler JSON-Errorhandler + strukturiertes Logging
7. Zeitzone `Europe/Berlin` für „aktueller Monat" statt Serverzeit
8. Indizes und UNIQUE-Constraints
9. Warnung vor Datenverlust beim Neugenerieren; Backup-Strategie dokumentieren

### Etappe 1 — Arbeitszeitfenster

`employee_availability`, `availability_mode`, Filter im Planer, Warnung bei Handkorrektur, Editor in `Employees.jsx`. **Nach dieser Etappe funktioniert dein Kernwunsch bereits** — Anna 08:00–14:00 wird respektiert.

### Etappe 2 — Individuelle Zeiten pro Zuweisung

`shift_assignments.start_time/end_time`, `shift_type_id` nullable, Ansichten und Constraint-Rechnung darauf umstellen, HR kann Zeiten pro Person ändern.

### Etappe 3 — Öffnungszeiten und Bedarf auf der Zeitachse

`business_hours`, `business_hours_exceptions`, `coverage_requirements`, Migration aus `shift_requirements`, beide neuen Editoren, Deckungslücken-Anzeige.

### Etappe 4 — Zuschnitt im Planer

Stufe 1 (Blockplanung), automatisches Kürzen, benannte Restlücken, Benchmark-Erweiterung.

### Etappe 5 — Restliche Produktionsreife

Veröffentlichen-Workflow (`status` endlich nutzen), Audit-Log, Exporte (PDF/Excel/iCal), DSGVO-Themen (Auskunft, Löschung, Aufbewahrung), ArbZG-Prüfungen (max. 8/10 h pro Tag, Pausen, max. 6 Tage in Folge).

## 11. Bewusst nicht dabei (YAGNI)

- **Kein CP-SAT / OR-Tools im Produktivpfad.** Der Benchmark zeigt, dass die eigene Suche bei dieser Größe gleichwertige Ergebnisse ~900× schneller liefert. Eine 100-MB-Abhängigkeit für nichts.
- **Keine „bevorzugt"-Stufe** bei der Verfügbarkeit. Papershift ist auch binär; Wünsche sind ein eigenes Thema für später.
- **Keine Zeiterfassung, keine Lohnkosten, keine Abteilungen** in diesem Vorhaben.
- **Kein Umbau auf ein Minutenraster.** Ereignispunkte reichen und bleiben verständlich.
- **Keine Mehrmonatsplanung.** Die Monatsgrenze bleibt die bekannte Einschränkung des Planers.

## 12. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Stufe 1 erzeugt schlechtere Pläne als heute | Etappe 4 kommt zuletzt; der Benchmark vergleicht vorher/nachher; bei Verschlechterung bleibt der alte Pfad als Option erhalten |
| `shift_type_id` nullable bricht bestehende Abfragen | Jede betroffene Stelle wird beim Umbau einzeln geprüft; API-Tests aus Etappe 0 fangen Regressionen |
| Migration der Bedarfsdaten verfälscht Pläne | Eigener Test, der die Kurve vorher/nachher vergleicht; `downgrade()` verpflichtend |
| Etappe 0 fühlt sich wie Stillstand an | Etappe 1 liefert direkt danach den sichtbaren Kernnutzen |
