# Handoff — Stand und offene Punkte

Kompakte Übergabe, damit eine neue Sitzung ohne Vorwissen weiterarbeiten kann.
Stand: 18.08.2026.

## Das Projekt

Schichtplan-Tool für Personalabteilungen. Flask-Backend (`backend/`), React 19 + Vite
(`frontend/`). SQLite lokal, Postgres in Produktion — über eine **handgeschriebene
Dialektschicht** in `backend/db.py`, kein ORM. Backend auf Render, Frontend auf Vercel.

- Repo: https://github.com/MuhammetSah/scheduling-tool (öffentlich)
- Lokal: `C:\Users\muham\source\repos\scheduling-tool-main`
- API: https://schichtplan-api.onrender.com
- Render-Service `srv-d9r7b4ajobas73cplm1g`, Postgres `dpg-d9r7a7740ujc73arnp6g-a`

Kern ist `backend/scheduler.py`: Backtracking-Suche mit Branch-and-Bound, lexikografisches
Ziel (erst unbesetzte Schichten minimieren, dann Fairness über die Summe quadrierter
Schichtzahlen). Diese Suche wurde in allen drei Etappen **nicht** angefasst — auch Etappe 2
(individuelle Zeiten) betrifft ausschließlich den Handkorrektur-Pfad, nie den Generator.

## Aktueller Stand

| | |
|---|---|
| `main` | `8116e63` — Etappe 0 (PR #9, #10) und Etappe 1 (PR #11, #12) gemergt |
| Arbeitsbranch | `etappe-2-individuelle-zeiten`, ab `b65db6e` verzweigt. Etappe 2 lokal abgeschlossen (dieser Commit), Abschluss-Review und Merge nach `main` stehen noch aus |
| Testsuite | 141 passed / 22 skipped (Postgres-only, lokal übersprungen), warnungsfrei unter `-W error::DeprecationWarning` |
| CI | 4 Jobs: `backend (3.13)`, `backend (3.14)`, `backend-postgres`, `frontend` — alle grün auf `251d8c7` (Stand vor diesem Dokumentations-Commit; der Lauf für diesen Commit selbst steht noch aus) |
| Migrationen | `0001`–`0005` lokal angewandt und rundlauffest (up → down → up geprüft); in Produktion bislang nur `0001`–`0003`, `0004` und `0005` sind beim nächsten Deploy fällig |
| Laufzeitabhängigkeiten | unverändert fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata |

## Etappe 0 — abgeschlossen, gemergt, deployt

Produktionsreife-Fundament. 17 Commits, Suite von 23 auf 66 Tests.

- CI-Pipeline (vorher liefen die Tests nie automatisch)
- Versionierte Migrationen mit Rücknahme und Transaktion pro Migration; `init_db()`-Flickwerk abgelöst
- Abhängigkeiten exakt gepinnt
- `SECRET_KEY` in Produktion erzwungen (fiel vorher still auf einen im Quelltext veröffentlichten Wert zurück)
- Login-Drosselung, überlebt Neustart und mehrere Worker
- Fehlerantworten immer JSON, mit nachverfolgbarer `request_id`
- „Aktueller Monat" in der Betriebszeitzone statt UTC; `datetime.utcnow()` entfernt
- Rückfrage vor dem Überschreiben von Handkorrekturen
- Indizes und Eindeutigkeit auf `shift_assignments`
- Postgres in der CI; Advisory Lock gegen das Migrations-Rennen
- Betriebsrunbook im README

## Etappe 1 — abgeschlossen und gemergt

Plan: [`docs/superpowers/plans/2026-08-16-etappe-1-arbeitszeitfenster.md`](superpowers/plans/2026-08-16-etappe-1-arbeitszeitfenster.md)
Ledger: `.superpowers/sdd/2026-08-16-etappe-1-arbeitszeitfenster/progress.md` (gitignoriert)

Ziel erreicht: „Anna arbeitet Mo–Fr 08:00–14:00" ist ausdrückbar, wird vom Planer als harte
Bedingung respektiert und ist über das Mitarbeiterformular pflegbar.

| Task | Stand | Commit |
|---|---|---|
| 1 Migration und Schema | ✅ Review sauber | `415caca` |
| 2 Fensterprüfung im Planer | ✅ Review sauber | `4c857d3` |
| 3 API — lesen und schreiben | ✅ Review sauber | `d5e1d14` |
| 4 Warnung bei Handkorrektur | ✅ Review sauber | `1f3e161` |
| 5 Frontend-Editor | ✅ Review sauber | `4aa2bb0` |
| 6 Dokumentation | ✅ Review sauber nach einer Fix-Runde | `e3963c3` |
| Abschluss-Review + Fix-Welle | ✅ Re-Review sauber | `7524e83` |
| Merge nach `main` | ✅ PR #11 | `b65db6e` |

**Erster Schritt einer neuen Sitzung:** Etappe 2 planen und auf einem neuen Branch ab `main`
beginnen. Aus Etappe 1 ist nichts offen.

**Beim nächsten Deploy:** Migration `0004` ist noch nicht in Produktion angewandt — sie läuft
beim ersten Start nach dem Deploy. Danach `python migrations.py status` gegenprüfen.

### Was das Abschluss-Review gefunden hat — die Lehre daraus

Ein **Critical**, und er lag im Plan, nicht in der Umsetzung: Migration `0004` endete mit
einem ungeschützten `ALTER TABLE employees ADD COLUMN availability_mode`, und die vom Plan
wörtlich vorgegebene `.down.sql` entfernte die Spalte bewusst nicht. Der Rundlauf
up → down → up scheiterte damit an `duplicate column name`. Weil `app.py` die Migrationen beim
Modulimport ausführt und jeder Gunicorn-Worker die App nach dem Fork selbst importiert, hätte
ein einziges `python migrations.py down` in Produktion jeden Worker beim Boot getötet — also
genau in der Situation, für die das Down-Skript existiert.

Behoben durch Umstellung von `0004` auf eine `.py`-Migration mit `table_columns()`-Wächter vor
dem `ALTER`, Muster aus `0001_baseline.py`. Die Spalte bleibt beim Rollback weiterhin stehen;
die ursprüngliche Begründung dafür war richtig, nur unvollständig zu Ende gedacht.

Zwei **Important** im Frontend, beide aus derselben Wurzel: was im Fenster-Modus ausgeblendet
wird, wirkt trotzdem weiter. Ein leeres, neu hinzugefügtes Fenster wurde beim Zurückschalten
auf „Immer verfügbar" mitgesendet und erzeugte einen 400 über ein unsichtbares Feld; und
`unavailable_weekdays` blieb eine harte, vor der Fensterlogik geprüfte Bedingung, war aber
weder sichtbar noch korrigierbar. Der Picker steht jetzt in beiden Modi, mit Hinweistext.

### Die Semantik, einmal präzise

`employees.availability_mode` ist `'anytime'` (Standard, wie bisher) oder `'windows'`.
Im Fenster-Modus gilt: nur innerhalb der eingetragenen Fenster; ein Wochentag ohne Fenster
heißt „an dem Tag gar nicht". `unavailable_weekdays`, `unavailable_dates` und Abwesenheiten
gelten in **beiden** Modi zusätzlich und werden **vor** dem Fenster-Check geprüft — sie können
nie etwas erlauben, nur verbieten.

Eine Schicht ist erlaubt, wenn sie **vollständig in ein einzelnes** Fenster passt — nicht in
die Vereinigung mehrerer. Gerechnet in Minuten ab Mitternacht des Starttags; ein Ende ≤ Start
bekommt 1440 aufgeschlagen, für Fenster **und** Schicht. Der Wochentag ist der des
Schichtbeginns, auch bei Nachtschichten. Gültigkeitsgrenzen sind einschließlich.

Funktionen in `backend/scheduler.py`: `time_to_minutes()`, `window_contains_shift()`,
`window_is_valid_on()`. **Nicht duplizieren** — `constraint_warnings()` in `app.py` importiert
sie, und weil `swap_assignments()` und `replacement_suggestions()` ihrerseits
`constraint_warnings()` wiederverwenden, hängen alle Pfade an derselben Implementierung.

## Etappe 2 — abgeschlossen

Plan: [`docs/superpowers/plans/2026-08-17-etappe-2-individuelle-zeiten.md`](superpowers/plans/2026-08-17-etappe-2-individuelle-zeiten.md)
Ledger: `.superpowers/sdd/2026-08-17-etappe-2-individuelle-zeiten/progress.md` (gitignoriert)

Ziel erreicht: eine Zuweisung kann eigene Start-/Endzeiten tragen, die vor dem Datums-Override
der Schichtart und vor deren üblicher Zeit gelten (drei Stufen, siehe unten), und ein
Zuweisungsplatz kann auch ganz ohne Schichtart existieren, wenn er eigene Zeiten mitbringt.
Der Fenster-Block in `constraint_warnings()`, für den das Etappe-1-Handoff eine Umstellung
vormerkte (siehe oben, jetzt entfernt), rechnet damit korrekt statt in einen 500 zu laufen.

| Task | Stand | Commit |
|---|---|---|
| 1 Migration und Schema für individuelle Zeiten | ✅ Review sauber nach einer Fix-Runde | `592dd39` |
| 2 Zeitauflösung einer Zuweisung an einer Stelle bündeln | ✅ Review sauber nach einer Fix-Runde | `bca00ad` |
| 3 Plan liefert die tatsächlichen Zeiten und Blöcke ohne Vorlage | ✅ Review sauber nach einer Fix-Runde | `b445903` |
| 4 Warnungen und Platzvergabe kommen ohne Schichtart aus | ✅ Review sauber (0 Findings) | `c71d1cf` |
| 5 Individuelle Zeiten über die API setzen | ✅ Review sauber nach einer Fix-Runde | `99701b6` |
| 6 Individuelle Zeiten pro Person in der Planansicht (Frontend) | ✅ Review sauber nach einer Fix-Runde | `251d8c7` |
| 7 Dokumentation | ✅ | dieser Commit |

**Die Vorrangregel**, einmal präzise: eine Zuweisung läuft an einem Datum zu genau einem
Zeitpaar, in dieser Reihenfolge — `shift_assignments.start_time`/`end_time`, wenn gefüllt
(genau diese Person, genau dieser Platz); sonst ein Eintrag in `shift_time_overrides` für
`(schedule_id, date, shift_type_id)` (gilt für alle auf der Schicht an diesem Tag); sonst
`shift_types.start_time`/`end_time`. Gebündelt in `assignment_hours()` (`backend/app.py`) und
von allen zeitabhängigen Prüfungen genutzt — Wochenstunden, Ruhezeit, Verfügbarkeitsfenster.
Betrifft ausschließlich den Handkorrektur-Pfad; der Generator setzt nie eigene Zeiten oder
einen Datums-Override, eine frisch erzeugte Zuweisung läuft immer auf der dritten Stufe.

Beide neuen Spalten sind entweder beide gefüllt oder beide `NULL`; ein halb gefülltes Paar
oder ein Paar mit gleicher Start-/Endzeit wird mit 400 abgelehnt (Letzteres wegen der
projektweiten Mitternachtskonvention `end <= start`, die sonst still eine 24-Stunden-Schicht
daraus machen würde).

`shift_assignments.shift_type_id` ist jetzt nullable. Ein Block ohne Schichtart muss eigene
Zeiten tragen — er hat keine Stufe 2 und keine Stufe 3, von der er erben könnte, und die API
erzwingt das. In dieser Etappe erzeugt niemand einen solchen Block: der Generator weist immer
eine echte Schichtart zu, und es gibt bewusst keine Schaltfläche im Frontend dafür. Das
Datenmodell geht dem Planer damit absichtlich voraus — Etappe 4 baut darauf auf, ohne Schema
und Algorithmus gleichzeitig ändern zu müssen.

**Nächster Schritt einer neuen Sitzung:** Abschluss-Review für Etappe 2 einholen (die sechs
Task-Reviews oben sind einzeln sauber, aber es gab noch keine Gesamtdurchsicht wie am Ende von
Etappe 1), dann PR nach `main`. Danach Etappe 3 (Öffnungszeiten und Bedarf auf der Zeitachse)
auf einem neuen Branch beginnen.

## Arbeitsweise

Subagent-driven development (`superpowers:subagent-driven-development`): pro Aufgabe ein
frischer Implementer, danach ein unabhängiger Reviewer, der dem Bericht des Implementers
ausdrücklich **nicht** glauben darf. Bei Befunden Fix-Runden mit eng gefasstem Re-Review.
Fortschritt im Ledger, nicht nur im Kopf — er überlebt eine Kontextverdichtung.

Skripte: `scripts/sdd-workspace`, `scripts/task-brief`, `scripts/review-package` unter
`C:\Users\muham\.claude\plugins\cache\claude-plugins-official\superpowers\6.2.0\skills\subagent-driven-development\`

Modellwahl: Sonnet für Implementierung und Review, Opus für besonders riskante Reviews
(Migrations-Runner, Auth-Pfad, Gesamt-Review).

## Fallstricke dieses Projekts — das Wichtigste für eine neue Sitzung

1. **Kein literales `?` in SQL, auch nicht in Kommentaren.** `_PostgresCursor` ersetzt es
   bedingungslos durch `%s`. Ein `?` in einem Migrations-Kommentar hätte beinahe die
   Produktion lahmgelegt; gefunden nur, weil die Postgres-CI existierte.
2. **Semikolons in SQL-Kommentaren** zerteilen die Datei am naiven Splitter.
3. **Eine Migration muss nach ihrer eigenen Rücknahme wieder vorwärts laufen.** Rückwärts
   allein reicht nicht. Alles, was nicht `IF NOT EXISTS` kann — vor allem `ADD COLUMN` —
   gehört in eine `.py`-Migration mit `table_columns()`-Wächter. Jede solche Migration
   braucht einen Rundlauftest up → down → up. Das war der Critical aus dem Abschluss-Review
   von Etappe 1 und hätte in Produktion jeden Worker beim Boot getötet.
4. **Tests, die nichts prüfen — vier Fälle bisher.** Vor jedem Commit fragen: *Würde dieser
   Test fehlschlagen, wenn ich das Feature lösche?* Typische Muster: Operationen in falscher
   Reihenfolge gestaffelt; zwei Eingaben gleichzeitig variiert, sodass ein Filter vorher
   kurzschließt; eine Soll-Liste aus derselben Datei abgeleitet, die sie absichern soll.
5. **Die Tabellenliste in `test_migrations.py` ist absichtlich fest verdrahtet.** Nicht wieder
   in eine Ableitung zurückverwandeln.
6. **Die 23 Tests in `backend/test_scheduler.py` bleiben unverändert.** Sie sind die
   Rückwärtskompatibilitätsgarantie. Werden sie rot, ist die Änderung falsch, nicht der Test.
7. **Kommentarsprache folgt der Datei.** `app.py`, `db.py`, `scheduler.py`,
   `test_scheduler.py` sind englisch; `security.py`, `timeutil.py`, `migrations.py` und die
   neueren Testdateien deutsch. Zwei Sprachen in *einer* Datei sind der eigentliche Fehler.
   Commit-Nachrichten durchgehend deutsch, README englisch.
8. **`render.yaml` ist nicht, was läuft.** Der Render-Dashboard-Startbefehl überschreibt die
   Datei vollständig. Vor jeder Änderung dort prüfen, ob der Dienst der Datei überhaupt folgt.
9. **`--preload` nicht als Ballast entfernen.** Ohne es führt jeder Worker beim Start die
   Migrationen aus; stirbt einer beim Booten, fährt Gunicorn den *gesamten* Dienst herunter.
10. **Postgres-Verhalten nie aus SQLite schließen.** Lokal läuft nur SQLite. Der
    `backend-postgres`-Job ist die einzige echte Probe.
11. **Die Render-MCP-Abfrage funktioniert nicht** (kein SSL). Für Datenbankabfragen ein
    Python-Skript mit `psycopg2` und `sslmode='require'` nutzen.
12. **Was die Oberfläche ausblendet, wirkt trotzdem weiter.** Ein ausgeblendetes Formularfeld
    schickt seinen Wert weiter mit, und eine ausgeblendete Einschränkung wird weiter geprüft.
    Beide Important-Befunde des Abschluss-Reviews von Etappe 1 waren genau das.
13. **`WHERE shift_type_id = ?` mit `None` trifft in SQL keine Zeile**, auch nicht die mit
    NULL. Deshalb der `IS NULL`-Zweig in `add_slot()` und `COALESCE(shift_type_id, 0)` im
    UNIQUE-Index — ohne den würde Postgres NULLs als voneinander verschieden behandeln und
    der Index nichts mehr garantieren.
14. **`PUT /assignments/<id>` schreibt die Zeiten bei jedem Aufruf mit.** Fehlen sie im Body,
    werden sie auf NULL gesetzt. Wer nur den Mitarbeiter tauschen will, muss die Zeiten
    mitschicken. Das Frontend tut das; ein künftiger Aufrufer muss es auch.

## Offen — liegt beim Nutzer

- **Postgres läuft am 07.09.2026 ab.** Kostenloser Plan. Entscheidung nötig: bezahlter Plan,
  Umzug, oder bewusster Datenverlust. Datenbestand ist klein (3 Mitarbeiter, 62 Zuweisungen),
  also kein Notfall, aber ein Termin.
- **IP-Freigabe an der Datenbank entfernen.** Wurde für eine einmalige Prüfung gesetzt.
- **Datenbankpasswort wurde in einem Chatverlauf offengelegt** und sollte getauscht werden.
  Entschärft dadurch, dass externer Zugriff nur von einer IP erlaubt ist und die Instanz
  ohnehin am 07.09. verschwindet.
- **Render-Startbefehl angleichen** (optional): Dashboard → Settings → Start Command auf
  `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --threads 4 --timeout 60`
- **`pg_dump` fehlt**: `winget install --id PostgreSQL.PostgreSQL.18` (Version 18, passend zum Server)

## Zurückgestellte Befunde

Aus den Reviews, bewusst nicht behoben, für ein späteres Aufräumen:

- `ci.yml` Cache-Schlüssel deckt nur `requirements-dev.txt` ab
- `ortools` in `requirements-dev.txt` ungepinnt
- `password_not_set_yet`-Zweig in `login()` zählt keine Versuche
- Drosselungstests verdrahten `10/9/11` fest statt `security.MAX_FAILED_ATTEMPTS`
- `is_locked_out`/`record_attempt` sind check-then-act ohne Zeilensperre
- `HTTPException`-Fallback liefert für andere Codes als 404/405 einen unübersetzten Literal (aktuell unerreichbar)
- `handleMonthChange` setzt den geladenen Plan nicht zurück; Erzeugen-Knopf nicht gesperrt während des Ladens
- `fetchSchedule()` schluckt jeden GET-Fehler zu `null`
- `MIGRATIONS_DIR.iterdir()` wirft, wenn das Verzeichnis fehlt
- Zwei Validierungstests in `test_api_availability.py` prüfen nur den Status, nicht die Meldung
- **Frontend hat keinerlei Testinfrastruktur.** Bewusste Entscheidung; sollte spätestens mit
  dem Zeitachsen-Editor aus Etappe 3 nachgerüstet werden (Vitest + Testing Library)

Neu aus dem Abschluss-Review von Etappe 1:

- `unavailable_dates` hat denselben Normalisierungsfehler, der für `valid_from`/`valid_until`
  behoben wurde: `date.fromisoformat()` akzeptiert ab Python 3.11 auch `'20260901'`, und der
  Wert wird wörtlich gespeichert, obwohl später als Zeichenkette verglichen wird. Kleiner
  Folge-Commit, gleiche Zeile Logik
- keine CHECK-Constraints auf `employee_availability` (`weekday`, `start_time`, `end_time`);
  konsistent mit den anderen Tabellen, die API ist der einzige Schreiber. Wieder aufgreifen,
  sobald ein zweiter Schreibpfad entsteht (Import/Seed in Etappe 5)
- keine Eindeutigkeit und keine Überlappungsprüfung auf `employee_availability` — dasselbe
  Fenster zweimal gesendet steht zweimal in der Warnung
- die Fenster-Abzeichen in der Mitarbeiterliste filtern nicht nach `valid_from`/`valid_until`;
  ein abgelaufenes Fenster liest sich wie ein aktives. `constraint_warnings()` filtert korrekt
- die Fensterprüfung rechnet im innersten Schleifenkörper von `eligible_candidates()` alle
  `"HH:MM"`-Strings pro Kandidat und Knoten neu. Datenbankseitig ist alles vorgeladen, nur
  rechnerisch. Erst angehen, wenn der Benchmark es zeigt
- der `Project Structure`-Block im README listet weiterhin weder `migrations/` noch
  `security.py`, `timeutil.py` oder die seit Etappe 0 hinzugekommenen Testdateien
- Spec §6 sah eine eigene Route `GET/PUT /employees/<id>/availability` mit `require_self_or_hr`
  vor; gebaut wurde sie nicht, die Fenster hängen an `/employees/<id>` (`@hr_required`).
  Sicherheitsseitig die konservative Richtung, aber ein Mitarbeiter sieht seine eigenen
  Arbeitszeiten nicht. **Etappe 2 und 3 dürfen die Route nicht als vorhanden annehmen**

Neu aus den Reviews von Etappe 2:

- ungenutzte Konstante `ASSIGNMENT_TIMES_PY_PATH` in `test_migrations_postgres.py`
- der Bestandstest zum Tabellenneubau prüft nur 6 von 9 kopierten Spalten
- `ux_assignment_slot_v2` ist ein Ausdrucksindex und damit als Zugriffspfad schwächer als sein
  Vorgänger — nutzbarer Präfix nur `(schedule_id, date)`
- der SQLite-Tabellenneubau läuft mit eingeschalteten Fremdschlüsseln; eine verwaiste
  Bestandszeile ließe die Kopie scheitern (laut und vollständig zurückgerollt, nur lokal
  möglich)
- halb gefüllte Zeitpaare fallen in `assignment_hours()` still auf Stufe 2/3 durch, statt
  einen Fehler zu erzeugen
- in der Wochenschleife von `constraint_warnings()` laufen jetzt zwei Abfragen pro Zeile statt
  einer, multipliziert in `replacement_suggestions()`
- die `end_time`-Hälfte der Zeitformat-Prüfung ist ungetestet
- die Validierungsreihenfolge in `add_slot()` prüft Zeiten vor dem Datum
- die Regel „Block ohne Vorlage braucht Zeiten" steht an zwei Stellen (`add_slot()` und
  `update_assignment()`)
- `set_shift_times()` hat dieselbe Gleichheitslücke, die in `parse_assignment_times()`
  behoben wurde (vorbestehend)
- der i18n-Schlüssel `availability_time_invalid` wird jetzt auch für Zuweisungen benutzt,
  obwohl sein Name nach Etappe 1 klingt
- ein unübersetztes `OK`-Literal in `ShiftCell.jsx` (aus dem Bestandsmuster übernommen)
- mehrere vorlagenlose Blöcke am selben Datum landen in derselben Zelle und nur der erste
  liefert die Zellenzeile — erst ab Etappe 4 erzeugbar

## Roadmap

Design: [`docs/superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md`](superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md)

- **Etappe 3** — Öffnungszeiten und Bedarf auf der Zeitachse: `business_hours`,
  `business_hours_exceptions`, `coverage_requirements` (nicht überlappend, absolute
  Besetzungsstärke), Migration aus `shift_requirements`, Deckungslücken-Anzeige
- **Etappe 4** — Zuschnitt im Planer: Blockplanung aus Bedarf und Fenstern, automatisches
  Kürzen auf das Mitarbeiterfenster, benannte Restlücken. Das ist der Punkt, an dem das Tool
  über Papershift und Deputy hinausgeht — dort wird nicht automatisch zugeschnitten.
- **Etappe 5** — restliche Produktionsreife: Veröffentlichen-Workflow (`schedules.status` wird
  bis heute nicht genutzt), Audit-Log, Exporte, DSGVO (Krankmeldungen sind Art.-9-Daten),
  ArbZG-Prüfungen (max. 8/10 h, Pausen, max. 6 Tage in Folge)
