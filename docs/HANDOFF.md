# Handoff — Stand und offene Punkte

Kompakte Übergabe, damit eine neue Sitzung ohne Vorwissen weiterarbeiten kann.
Stand: 22.08.2026.

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
Schichtzahlen). Diese Suche wurde in allen vier Etappen **nicht** angefasst — auch Etappe 2
(individuelle Zeiten) betrifft ausschließlich den Handkorrektur-Pfad, nie den Generator, und
Etappe 3 (Öffnungszeiten und Bedarf) pflegt und wertet `coverage_requirements` aus, ohne dass
der Generator sie kennt: `build_slots()` baut weiterhin ausschließlich aus
`shift_requirements`. Die Umstellung ist Etappe 4.

## Erster Schritt einer neuen Sitzung

Es ist nichts halb fertig. Etappen 0 bis 4 sind gemergt, deployt und dokumentiert, es gibt
keine offenen Branches und keine offenen Pull Requests. Die Suite ist grün, ein geprüftes
Backup liegt.

Der nächste inhaltliche Schritt ist **Etappe 5 — restliche Produktionsreife** (siehe Roadmap
am Ende). Anders als die Etappen davor ist sie kein zusammenhängendes Vorhaben, sondern ein
Bündel weitgehend unabhängiger Teile: `shift_requirements` entfernen, Veröffentlichen-Workflow,
Audit-Log, Exporte, DSGVO und die drei ArbZG-Regeln, die Etappe 4 bewusst offengelassen hat.
**Sie gehört vor dem Planen zerlegt**, nicht als ein Umsetzungsplan angefasst — jedes Teil
bekommt seine eigene Spec und seinen eigenen Plan.

**Lies vorher zwei Abschnitte:** Fallstricke dieses Projekts und Zurückgestellte Befunde. Dort
steht, was vier Etappen an Reviews gekostet hat und was bewusst liegen geblieben ist. Die
Liste ist nach Etappe 4 um sechs Punkte gewachsen.

**Was beim Nutzer liegt und nicht bei dir:** der Umgang mit der ablaufenden Datenbank
(07.09.2026), das Datenbankpasswort und die IP-Freigabe. Details unter „Offen — liegt beim
Nutzer“. Zugangsdaten fasst du nicht an, auch nicht auf Aufforderung.

## Aktueller Stand

| | |
|---|---|
| `main` | `088fd7d` — Etappen 0 bis 4 gemergt und deployt. Etappe 4 über PR #16 am 22.08. 17:28, Render-Deploy `dep-da4toioae00c73aslg5g` ist `live` |
| Branch-Situation | Keine offenen Branches, keine offenen Pull Requests. Der Etappe-4-Branch ist nach dem Merge lokal und remote gelöscht |
| Aktueller Branch | keiner — `main` ist der Stand |
| Testsuite | 256 passed / 30 skipped (Postgres-only, lokal übersprungen), warnungsfrei unter `-W error::DeprecationWarning`; dazu 15 Frontend-Tests (Vitest + Testing Library) |
| CI | 4 Jobs: `backend (3.13)`, `backend (3.14)`, `backend-postgres`, `frontend` (letzterer führt seit Etappe 3 zusätzlich `npm test -- --run` aus) — alle grün auf `main` |
| Migrationen | `0001`–`0008`, **alle in Produktion angewandt**. `0008_max_daily_hours` mit dem Deploy von #16; die API antwortet danach mit 200, und da `app.py` die Migrationen beim Modulimport ausführt, wäre ein Fehlschlag mit einem laufenden Dienst nicht vereinbar. Aus den Render-Logs vom 22.08.: `0005_assignment_times` beim Deploy von #13, `0006_coverage, 0007_derive_coverage` beim Deploy von #14, beide Male gefolgt von `Your service is live`. Die Ableitung des Altbestands in Bedarfsbänder lief damit fehlerfrei gegen echte Daten |
| Laufzeitabhängigkeiten (Backend) | unverändert fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata |
| Laufzeitabhängigkeiten (Frontend, neu, nur dev) | vitest, @testing-library/react, @testing-library/jest-dom, jsdom — die erste Frontend-Testinfrastruktur des Projekts, alle als devDependency |

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

*(Historisch: Migration `0004` war zu diesem Zeitpunkt noch nicht in Produktion. Sie ist
seit dem Deploy vom 22.08.2026 angewandt, zusammen mit `0005`–`0007`.)*

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

**Nächster Schritt einer neuen Sitzung war:** Abschluss-Review für Etappe 2 einholen, dann PR
nach `main`. Stattdessen wurde — mangels Merge von PR #13 — direkt auf einem gestapelten Branch
mit Etappe 3 weitergearbeitet (siehe dortiger Abschnitt und die Branch-Situation oben); die
Gesamtdurchsicht für Etappe 2 steht weiterhin aus.

## Etappe 3 — abgeschlossen

Plan: [`docs/superpowers/plans/2026-08-18-etappe-3-oeffnungszeiten-bedarf.md`](superpowers/plans/2026-08-18-etappe-3-oeffnungszeiten-bedarf.md)
Ledger: `.superpowers/sdd/2026-08-18-etappe-3-oeffnungszeiten-bedarf/progress.md` (gitignoriert)

Ziel erreicht: Öffnungszeiten sind pro Wochentag definierbar (mit datumsgenauen Ausnahmen),
und Bedarf ist als Bänder auf der Zeitachse ausdrückbar — absolute Besetzungsstärke, nicht
additiv, mit halboffener Grenze zwischen benachbarten Bändern. Der Plan meldet Deckungslücken
gegen die tatsächlichen, in Etappe 2 eingeführten Zuweisungszeiten. **Der Planer wurde dabei
bewusst NICHT umgestellt:** `build_slots()` in `backend/scheduler.py` baut weiterhin
ausschließlich aus `shift_types`/`shift_requirements`; `coverage_requirements` wird in dieser
Etappe nur gepflegt und ausgewertet, nie geplant. Beide Modelle laufen nebeneinander her, das
ist gewollt — die Spec sieht die Entfernung von `shift_requirements` erst nach Etappe 4 vor,
und die Umstellung des Generators gehört mit dem Zuschnitt zusammen in genau diese Etappe.

| Task | Stand | Commit |
|---|---|---|
| 1 Schema für Öffnungszeiten und Bedarfsbänder | ✅ Review sauber | `f929d4c` |
| 2 Bedarfskurve aus Schichtarten ableiten (reine Funktion, ohne DB) | ✅ Review sauber | `d9a17df` |
| 3 Bestehenden Schichtbedarf einmalig in Bänder überführen | ✅ Review sauber | `27e218c` |
| 4 Öffnungszeiten und Ausnahmen über die API pflegen | ✅ Review sauber nach einer Fix-Runde (2 Important) | `2ec2ef0` / Fix `484d8d8` |
| 5 Bedarfsbänder über die API pflegen | ✅ Review sauber (0 Critical/Important/Minor) | `028b518` |
| 6 Deckungslücken auf der Zeitachse melden | ✅ Review sauber | `64751e3` |
| 7 Frontend-Editoren für Öffnungszeiten und Bedarf | ✅ Review sauber | `ea88166` |
| 8 Frontend-Testinfrastruktur mit Vitest aufsetzen | ✅ Review sauber (0/0/0) | `29d6da9` |
| 9 Dokumentation | ✅ | dieser Commit |

**Die Semantik, einmal präzise:** `business_hours` trägt genau eine Zeile je Wochentag
(`UNIQUE(weekday)`), Standard nach der Migration `00:00`/`00:00` mit `closed = 0` — nach der
Mitternachtskonvention `end <= start` heißt das "der ganze Tag" und ist der einzige Standard,
der kein bestehendes Verhalten ändert, weil es vor dieser Etappe überhaupt keine
Öffnungszeiten gab. `business_hours_exceptions` schlägt für ein einzelnes Datum die
Wochentagsregel. **Öffnungszeiten sind in dieser Etappe eine Validierungsgrenze, keine
Planerbedingung** — sie beschränken, welche Bänder gespeichert werden dürfen, verbieten aber
keine bestehende Zuweisung und lösen keine Warnung aus. `coverage_requirements` trägt Bänder
pro Wochentag mit **absoluter, nicht additiver** Besetzungsstärke; Bänder desselben Wochentags
dürfen sich nicht überlappen (400) und müssen innerhalb der Öffnungszeit liegen (400) — die
Grenze zwischen benachbarten Bändern ist halboffen, `08:00–12:00` und `12:00–16:00` berühren
sich nur und sind beide erlaubt. Die Bänder wurden **einmalig** bei der Migration
(`0007_derive_coverage.py`) aus dem bestehenden `shift_requirements`-Bedarf abgeleitet
(`coverage_curve()` in `backend/coverage_model.py`); danach gibt es **keine** automatische
Neuberechnung, wenn sich `shift_requirements` später ändert — sonst hätte man zwei Quellen,
die sich gegenseitig überschreiben. `GET /schedules/<jahr>/<monat>` liefert zusätzlich
`coverage_gaps`, gerechnet gegen die tatsächlichen Zeiten der Zuweisungen (Etappe 2); ein
unbesetzter Platz und ein durch Abwesenheit freigewordener decken nichts ab.

**Bekannte, dokumentierte Grenze:** Überlappung über die Wochentagsgrenze hinweg wird nicht
geprüft — ein Band Montag 22:00–06:00 und eines Dienstag 00:00–08:00 werden beide akzeptiert
(über die API nachgeprüft, nicht angenommen: `test_nachtband_wird_unter_ganztaegiger_oeffnung_akzeptiert`).
Bei konsequent start-verankerter Lesart beschreiben sie auch nicht dieselbe Zeit; ein realer
Konflikt entstünde erst über die Wochenwiederholung hinweg, und das zu erkennen hieße, die
Woche als 10080-Minuten-Ring zu behandeln — bewusst nicht gebaut, siehe README.

Diese Etappe hat zwei neue Fallstricke hervorgebracht — die gleichnamigen Testfunktionen bei
Task 4/5 und `coverage.py` als verbotener Modulname; beide jetzt in der Liste "Fallstricke
dieses Projekts" unten als Punkte 15 und 16.

**Nächster Schritt einer neuen Sitzung:** Eine gemeinsame Abschluss-Review-Runde für Etappe 2
UND Etappe 3 einholen (für Etappe 2 steht sie komplett aus, siehe oben; für Etappe 3 sind nur
die acht Einzel-Task-Reviews gelaufen, keine Gesamtdurchsicht), dann beide PRs (#13 zuerst,
danach #14) nach `main` mergen — in dieser Reihenfolge, weil #14 auf #13 aufbaut. Danach
Etappe 4 (Zuschnitt im Planer) auf einem neuen Branch ab `main` beginnen.

## Etappe 4 — abgeschlossen, gemergt, deployt

Spec: [`docs/superpowers/specs/2026-08-22-etappe-4-zuschnitt-design.md`](superpowers/specs/2026-08-22-etappe-4-zuschnitt-design.md)
Plan: [`docs/superpowers/plans/2026-08-22-etappe-4-zuschnitt.md`](superpowers/plans/2026-08-22-etappe-4-zuschnitt.md)
PR #16, vierzehn Commits, gemergt am 22.08. 17:28 als `088fd7d`, Deploy live

Ziel erreicht: der Planer baut aus `coverage_requirements` statt aus `shift_requirements`,
schneidet Blöcke auf die Arbeitszeitfenster zu, und der geteilte Dienst ist innerhalb der
Grenzen des Arbeitszeitgesetzes plan bar.

| Task | Stand | Commit |
|---|---|---|
| 1 Route für eigene Arbeitszeitfenster (Vorarbeit) | ✅ | `bb74f35` |
| 2 Zellenkollision bei gleichzeitigen Blöcken (Vorarbeit) | ✅ | `a758d63` |
| 3 Tägliche Höchstarbeitszeit, Migration `0008` | ✅ | `537e287` |
| 4 Stufe 1: Bedarf mit Vorlagen decken | ✅ | `19a290c` |
| 5 Stufe 1: Zuschnitt auf Arbeitszeitfenster | ✅ | `4ea6ed2` |
| 6 Anschluss an den Generator | ✅ | `4ef8a22` |
| 7 Geteilter Dienst im Suchkern | ✅ | `53f185f` |
| 8 Warnungen auf dem Handkorrektur-Pfad | ✅ | `135cb0b` |
| 9 Bedarfszahlen aus dem Schichtart-Editor | ✅ | `171e4e1` |
| 10 Benchmark-Gegenprobe | ✅ | `a330c27` |
| 11 Dokumentation | ✅ | `0bead66` |
| Fund aus der Durchsicht vor dem Merge | ✅ | `6a2a38f` |
| Merge nach `main` | ✅ PR #16 | `088fd7d` |

### Was der Benchmark sagt

Die beiden Zahlen, die diese Etappe rechtfertigen — `python benchmark.py`, letzter Abschnitt:

| Szenario | Pfad | Blöcke | unbesetzt |
|---|---|---|---|
| unveränderter Bestand | alt | 166 | 0 |
| | Stufe 1 | 166 | 0 — **identische Blöcke** |
| Arbeitszeitfenster | alt | 93 | 31 |
| | Stufe 1 | 93 | **0** |

Oben: die Umstellung ändert auf unverändertem Bestand nichts. Unten: der Zuschnitt schließt
jede Lücke, die die Fenster sonst offen ließen — eine pro Tag.

### Die Architektur in drei Sätzen

`block_planner.py` ist Stufe 1: aus Bedarfsbändern, Vorlagen und Fenstern wird die Blockliste
eines Monats, reine Rechenlogik ohne Datenbank. `scheduler.py` ist Stufe 2 und bekommt die
Blöcke über den neuen Parameter `slots=` fertig übergeben — Fairness, Branch-and-Bound und
Notbremse sind unverändert. Der Monatsaufbau liegt in `block_planner`, **nicht** in
`scheduler`, weil `block_planner` aus `scheduler` importiert und der umgekehrte Import ein
Zirkel wäre.

### Was beim Umsetzen anders entschieden wurde als im Plan

- **`MIN_BLOCK_MINUTES` gilt nur für den Zuschnitt**, nicht für bedarfsgetriebene Blöcke. Ein
  bewusst gepflegtes Zwei-Stunden-Band still zu verwerfen wäre genau das Muster „Eingabe
  annehmen und wegwerfen". Neu dazu kam `MAX_BLOCK_MINUTES` (600): ein selbst gebildeter Block
  über zehn Stunden wäre nach § 3 ArbZG von niemandem zu besetzen.
- **Das Auswahlverfahren in Stufe 1 wurde ersetzt.** Der Plan sah „Vorlage mit dem größten
  Produkt aus Anzahl und Dauer" vor. Das deckt die Spitze zuerst und hängt die Schulter ab:
  bei Bedarf 06:00–08:00 für zwei und 08:00–14:00 für drei ergab es fünf Blöcke statt drei,
  darunter zwei unarbeitbare Zwei-Stunden-Reste. Gebaut ist jetzt „von links": am frühesten
  offenen Punkt ansetzen. Aufgefallen ist es beim Nachrechnen von Hand — der Determinismustest
  war grün, weil beide Reihenfolgen dasselbe schlechte Ergebnis lieferten.
- **Die Zellenkollision war breiter als notiert.** Nicht nur vorlagenlose Blöcke kollidieren,
  sondern auch zugeschnittene Blöcke derselben Vorlage: gleiche `shift_type_id`, andere
  Zeiten. Gruppiert wird jetzt nach (Vorlage, Start, Ende).

### Was dabei gefunden wurde

- **Eine zweite Landmine**, die im Plan fehlte: nicht nur die Ergebnissortierung in `_search()`
  vergleicht `shift_type_id` und fällt bei `None` über `TypeError`, sondern auch
  `order_slots()`. Gefunden von einem Bestandstest, der die zweite Suchrunde auslöst.
- **Ein Test, der bestand, obwohl das Feature fehlte.** `requirements` ist eine Liste von
  sieben Werten; ein übergebenes Dict mit den Schlüsseln `'0'`–`'6'` wurde zu `[0,1,2,3,4,5,6]`
  statt zu lauter Nullen. Fünfter Fall dieser Art im Projekt — die Frage aus Fallstrick 4 vor
  jedem Commit zu stellen lohnt sich weiterhin.
- **Vier Bestandstests mussten nachziehen**, drei davon, weil sie ihren Plan allein über
  `shift_requirements` aufbauten und nun keinen mehr bekamen.

### Arbeitszeitrecht: was das Tool prüft und was nicht

Geprüft: Überschneidungsverbot, tägliche Höchstarbeitszeit als **Summe der Blockdauern**
(§ 2 Abs. 1, § 3), Ruhezeit gemessen vom letzten Block eines Tages zum ersten des nächsten
(§ 5 Abs. 1). Beides sowohl im Generator als auch — warnend — auf dem Handkorrektur-Pfad.

**Nicht geprüft, bewusst und schriftlich:** der Achtstundendurchschnitt aus § 3 Satz 2 (der
Planer arbeitet monatsweise und kann ein 24-Wochen-Fenster strukturell nicht sehen — eine
`max_daily_hours` über 8 ist damit rechtlich nicht selbsttragend, der Hinweis steht am Feld),
die Ruhepausen aus § 4, und die Sonntagsregeln aus § 11. Alles drei ist Etappe 5.

### Zum Merge

Alle vier CI-Jobs grün, **einschließlich `backend-postgres`** — der ist der einzige Ort, an dem
die beiden Postgres-Tests für `0008` laufen, lokal werden sie übersprungen.

Bei der Durchsicht vor dem Merge fiel noch ein Punkt auf, der nicht von einem Test kam:
`generate_schedule()` sagt in seiner eigenen Beschreibung `"HH:MM" or None` für die Zeiten
einer Schichtart zu, und `cover_demand()` wäre daran abgestürzt. Über die Anwendung
unerreichbar (die Spalten sind `NOT NULL`), aber Vertrag und Code sagten Verschiedenes —
behoben in `6a2a38f`.

**Kein Browser-Durchlauf gefahren.** Die Oberfläche ist nur über die Vitest-Tests belegt.

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
15. **Zwei gleichnamige Testfunktionen im selben Modul überschreiben sich in Python still.**
    Der erste verschwindet lautlos aus der Suite, ohne dass irgendetwas fehlschlägt. In
    Etappe 3 gaben zwei Task-Briefs (4 und 5) denselben Testnamen vor; der Implementer von
    Task 5 hat es bemerkt und beide eindeutig umbenannt. `pytest --collect-only` zeigt es.
16. **Ein Modulname im Backend darf kein installiertes Paket verdecken.** `backend/coverage.py`
    hätte das PyPI-Paket `coverage` (Abhängigkeit von `pytest-cov`) verdeckt, sobald jemand das
    ergänzt — auch wenn `coverage` zum Entscheidungszeitpunkt nicht installiert war. Deshalb
    heißt die Datei `coverage_model.py`.

## Offen — liegt beim Nutzer

**Erledigt am 22.08.2026:** Etappe 2 und 3 gemergt und deployt (PR #13, #14), alle Migrationen
`0001`–`0007` in Produktion angewandt, der Nachtschicht-Fehler in `window_contains_shift()`
behoben und gemergt (PR #15), und ein vollständiges Backup gezogen und geprüft. Was hier steht,
ist der verbliebene Rest.

### Der Termin

- **Die Postgres-Instanz läuft am 07.09.2026 ab** (`expiresAt`, per Render-API bestätigt).
  Kostenloser Plan, Region Frankfurt, Version 18. Entscheidung nötig: bezahlter Plan, Umzug zu
  einem anderen Anbieter, oder bewusster Datenverlust. **Ein geprüftes Backup existiert**
  (siehe unten), der Verlust wäre also nicht endgültig — aber die laufende Anwendung verliert
  ihre Datenbank und braucht dann eine neue.

### Das Backup — vorhanden und geprüft

`C:\Users\muham\schichtplan-2026-08-22.dump`, 59,9 KB, Format `custom`, gezogen am 22.08.2026
um 15:02 mit `pg_dump 18.6` gegen den Server 18.

Am selben Tag per `pg_restore --list` und Auszählung der COPY-Blöcke verifiziert — 18 Tabellen,
alle mit Daten wie erwartet:

| Tabelle | Zeilen |
|---|---|
| `employees` | 3 |
| `shift_assignments` | 62 |
| `shift_types` | 2 |
| `coverage_requirements` | 21 (aus `0007` abgeleitet) |
| `business_hours` | 7 (genau eine je Wochentag) |
| `business_hours_exceptions` | 0 |
| `employee_availability` | 0 |
| `schema_migrations` | 7 |

Nebenbefund, der für Etappe 4 zählt: **`employee_availability` ist leer** — niemand nutzt
bisher den Fenster-Modus. Der am 22.08. behobene Nachtschicht-Fehler hatte im Betrieb also noch
keine Auswirkung.

**Die Datei enthält Betriebsdaten im Klartext.** Sie liegt bewusst in `$HOME` und nicht im
Repo-Verzeichnis — beachte, dass `C:\Users\muham` selbst ein Git-Repository ist und ein
unbedachtes `git add -A` sie einsammeln würde.

Zurückspielen in eine neue Postgres-18-Datenbank:

```
pg_restore --clean --no-owner --dbname="$NEUE_DBURL" schichtplan-2026-08-22.dump
```

Danach findet die Anwendung `0001`–`0007` bereits als angewandt vor — `schema_migrations` ist
Teil des Dumps.

### Zugangsdaten und Zugriff

- **Datenbankpasswort wurde in einem Chatverlauf offengelegt** und sollte getauscht werden.
  Entschärft dadurch, dass externer Zugriff nur von freigegebenen IPs erlaubt ist und die
  Instanz ohnehin am 07.09. verschwindet. **Bei einem Umzug oder einem bezahlten Plan gehört es
  rotiert.**
- **IP-Freigabe an der Datenbank aufräumen.** Am 22.08. wurde eine aktuelle IP ergänzt, damit
  der Dump laufen konnte — der alte Eintrag `88.130.158.137/32` vom 08.08. war durch die
  Zwangstrennung des Anschlusses veraltet. Erst entfernen, wenn kein Dump mehr nötig ist.
  **Merkposten für künftige Fehlersuche:** der Fehler `SSL-Verbindung wurde unerwartet
  geschlossen` bedeutet bei Render fast immer eine nicht freigegebene IP, kein TLS-Problem. Die
  Anwendung selbst ist davon nie betroffen, sie verbindet sich über die interne URL.

### Betrieb

- **Render-Startbefehl angleichen** (optional): die Logs vom 22.08. zeigen, was tatsächlich
  läuft — `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT`, ohne `--preload`, ohne
  `--threads`. Render setzt zusätzlich `WEB_CONCURRENCY=1`. Der Dienst läuft also mit **einem**
  Worker; das ist der Grund, warum das Migrations-Rennen bisher nie auftrat, und zugleich der
  Grund, warum `--preload` derzeit nichts schützt. Solange es bei einem Worker bleibt, ist das
  harmlos. Wird je auf mehrere erhöht, **muss** `--preload` in den Dashboard-Befehl, sonst
  greift genau die Race, gegen die `render.yaml` es vorsieht:
  `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --preload --threads 4 --timeout 60`
- `pg_dump`/`pg_restore` 18.6 sind installiert unter `C:\Program Files\PostgreSQL\18\bin`, aber
  **nicht im `PATH`**. Entweder mit vollem Pfad aufrufen oder dauerhaft ergänzen. Die
  PowerShell dieses Rechners ist 5.1 — dort gibt es kein `&&`, und Bash-Syntax wie `read -p`
  oder `export` funktioniert nicht.

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
- ~~Frontend hat keinerlei Testinfrastruktur~~ — **erledigt in Etappe 3** (Task 8, Vitest +
  Testing Library, siehe dort)

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
- der `Project Structure`-Block im README listet seit Etappe 3 zwar `migrations/` und
  `coverage_model.py`, weiterhin aber nicht `security.py`, `timeutil.py` oder die seit
  Etappe 0 hinzugekommenen Testdateien
- ~~Spec §6 sah eine eigene Route `GET/PUT /employees/<id>/availability` vor~~ — **erledigt in
  Etappe 4** (Vorarbeit 1). Lesen darf man sich selbst, schreiben bleibt HR

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
- ~~ein unübersetztes `OK`-Literal in `ShiftCell.jsx`~~ — **erledigt in Etappe 4**, es lag in
  derselben Zeile wie die Zellenkollision
- ~~mehrere vorlagenlose Blöcke am selben Datum landen in derselben Zelle~~ — **erledigt in
  Etappe 4** (Vorarbeit 2). Der Befund war breiter als hier notiert: auch zugeschnittene
  Blöcke derselben Vorlage kollidierten. Gruppiert wird jetzt nach (Vorlage, Start, Ende)

Aus dem Abschluss-Review von Etappe 3 behoben (eine Fix-Runde, ein Commit):

- `/business-hours` und `/coverage-requirements` prüfen einander in beide Richtungen; eine
  Öffnungszeit, die ein gespeichertes Band ungültig machen würde, wird mit Nennung von
  Wochentag und Band abgelehnt (`reject_hours_conflicting_with_bands()`)
- `coverage_gaps_for_month()` schneidet jedes Band auf das **effektive** Öffnungsfenster des
  Datums zu — Ausnahme schlägt Wochentag, und die Zeiten einer offenen Ausnahme wirken jetzt
  wirklich, statt nur ihr `closed`-Flag
- `band_within()` prüft die Enthaltung über die Schließzeit statt über eine gerade Achse; ein
  Nachtband 22:00–06:00 passt damit in die ganztägige Standard-Öffnungszeit, ohne dass
  07:00–12:00 bei 08:00–18:00 durchginge
- `business_hours_for()` ist eine reine Funktion auf vorgeladenen Dicts und hat wieder echte
  Aufrufer (`_closed_on()` und der Zuschnitt); `fetch_schedule()` macht unverändert acht
  Abfragen

Weiterhin offen aus den Reviews von Etappe 3:

- der Rundlauftest von `0006_coverage.py` prüft nach `down()`+`up()` nur `business_hours`,
  nicht ob die beiden Nebentabellen (`business_hours_exceptions`, `coverage_requirements`)
  wirklich weg waren — ein vergessenes `DROP TABLE` bliebe wegen `CREATE TABLE IF NOT EXISTS`
  unbemerkt
- ein Docstring in `test_migrations_postgres.py` spricht von Einzelindex-Zugriff, der Test
  vergleicht aber ganze Tupel
- für `0007_derive_coverage.py` gibt es nur einen Postgres-Test (die Ableitung selbst), keine
  Postgres-Gegenprobe für den Leer-Bestand-Wächter oder den Rundlauf
- `int(entry.get('weekday'))` in `replace_business_hours()`/`parse_coverage_requirements()`
  (`backend/app.py`) schluckt `True`/`False` als `1`/`0` und kürzt `3.9` zu `3`
- die Datumsprüfung beim Anlegen einer `business_hours_exceptions`-Zeile
  (`create_business_hours_exception()`) ist check-then-act ohne Sperre
- kein eigener HTTP-Test für den Abwesenheitsfall bei den Deckungslücken (code-seitig korrekt,
  über denselben `employee_id IS NULL`-Filter wie ein unbesetzter Platz)
- der Entfernen-Button im Bedarfseditor (`frontend/src/pages/CoverageEditor.jsx`) hat nur
  `title`, kein `aria-label`
- die Datumsformatierung steht jetzt in dritter Kopie im Frontend — folgt aber bereits
  etablierter Projektkonvention, keine neu eingeführte Dublette

Neu aus Etappe 4:

- `plan_day()` läuft die probeweise Tagesbesetzung nach jedem einzelnen Zuschnitt komplett neu,
  statt sie fortzuschreiben. Bei wenigen Blöcken pro Tag ist das billig, bei vielen quadratisch.
  Erst angehen, wenn der Benchmark es zeigt
- der Zuschnitt greift nur bei Mitarbeitern im `windows`-Modus. Jemand mit
  `availability_mode = 'anytime'`, dem nur die Tagesgrenze im Weg steht, bekommt kein gekürztes
  Stück angeboten — denkbar, aber nicht das, was die Spec unter Zuschnitt versteht
- `day_envelope()` gibt es zweimal: einmal in `scheduler._search()` über den Suchzustand,
  einmal als `app.day_envelope_from_hours()` über gespeicherte Zeilen. Die gemeinsame Rechnung
  steckt in `shift_datetimes()` und wird importiert, die Hülle ist doppelt
- `MAX_BLOCK_MINUTES` ist als 600 fest verdrahtet, obwohl `max_daily_hours` je Mitarbeiter
  einstellbar ist. Wer die Tagesgrenze auf 12 setzt, bekommt trotzdem keinen Block über zehn
  Stunden
- die Bedarfszahlen der Schichtart werden vom Frontend weiterhin mitgeschickt, damit der
  Bestand nicht still auf 0 fällt. Mit dem Entfernen von `shift_requirements` in Etappe 5 fällt
  das weg
- für `0008_max_daily_hours` gibt es zwei Postgres-Tests, die lokal übersprungen werden; sie
  sind bislang nur im CI gelaufen — **beim Abschluss-Review prüfen, dass `backend-postgres`
  wirklich grün war**

## Roadmap

Design: [`docs/superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md`](superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md)

- ~~**Etappe 4** — Zuschnitt im Planer~~ — **umgesetzt**, siehe oben. Der Planer baut aus
  `coverage_requirements`, schneidet auf die Arbeitszeitfenster zu und kann den geteilten
  Dienst. `shift_requirements` wird nicht mehr gelesen und in Etappe 5 entfernt. Damit geht das
  Tool über Papershift und Deputy hinaus — dort wird nicht automatisch zugeschnitten.
- **Etappe 5** — restliche Produktionsreife: `shift_requirements` entfernen,
  Veröffentlichen-Workflow (`schedules.status` wird bis heute nicht genutzt), Audit-Log,
  Exporte, DSGVO (Krankmeldungen sind Art.-9-Daten) und die ArbZG-Regeln, die Etappe 4 bewusst
  offengelassen hat: der Achtstundendurchschnitt aus § 3 Satz 2, die Ruhepausen aus § 4 und die
  Sonntagsregeln aus § 11 samt der Folge „höchstens sechs Tage in Folge"
