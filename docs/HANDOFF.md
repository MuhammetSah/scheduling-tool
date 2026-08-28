# Handoff — Stand und offene Punkte

Der laufende Arbeitsstand: was fertig ist, was offen liegt, und die Fallstricke, die dieses
Projekt stellt. Gedacht als das, was man nach zwei Wochen Pause zuerst liest.
Stand: 28.08.2026.

> **Zu den Kennungen weiter unten.** Die Einträge zu den einzelnen Etappen nennen
> Commit-Kürzel und Vorgangsnummern aus der vorherigen Ablage des Projekts. Dieses
> Repository beginnt mit dem hier beschriebenen Stand, dort sind sie also nicht
> auflösbar. Sie stehen trotzdem noch da, weil der Wert dieser Einträge in der
> Begründung liegt und nicht im Verweis — und weil eine nachträglich geglättete
> Aufzeichnung eine schlechtere Aufzeichnung wäre.

## Das Projekt

Schichtplan-Tool für Personalabteilungen. Flask-Backend (`backend/`), React 19 + Vite
(`frontend/`). SQLite lokal, Postgres in Produktion — über eine **handgeschriebene
Dialektschicht** in `backend/db.py`, kein ORM. Backend auf Render, Frontend auf Vercel.

- Repo: https://github.com/MuhammetSah/schichtplan-tool
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

## Wo es gerade steht

Es ist nichts halb fertig. **Etappe 5 ist vollständig**, und **Etappe 6 hat die zurückgestellten
Befunde abgearbeitet** — bis auf die zwei Leistungsbefunde, die ihre eigene Notiz „erst angehen,
wenn der Benchmark es zeigt" tragen, und er zeigt es nicht. Alles ist gemergt und deployt; es gibt
keine offenen Branches und keine offenen Pull Requests.

Die Roadmap ist abgearbeitet. Was jetzt noch offen liegt, sind die **restlichen zurückgestellten
Befunde** — siehe den eigenen Abschnitt. Sie sind gruppiert, nicht einzeln abzuarbeiten:

**Damit ist die Liste leer** bis auf zwei Leistungsbefunde: `plan_day()` läuft die probeweise
Tagesbesetzung nach jedem Zuschnitt neu, und die Fensterprüfung rechnet im innersten
Schleifenkörper alle `"HH:MM"`-Zeichenketten neu. Beide tragen seit ihrer Aufnahme die Notiz
„erst angehen, wenn der Benchmark es zeigt". Er zeigt es nicht, und eine Optimierung ohne Messung
wäre geraten.

**Etappe 7 hat davon die Prüfungen über die Monatsgrenze erledigt** — der Punkt mit dem größten
Gewicht, weil es keine fehlende Funktion war, sondern eine Lücke in einer bereits gegebenen
Zusicherung.

**Etappe 16 (28.08.2026) war ein Durchgang als Nutzer, keine neue Funktion** — das Werkzeug einmal
so benutzt, wie eine Personalabteilung und ein Mitarbeiter es benutzen. Ergebnis: ein
Sicherheitsbefund (ein Zurücksetzen, das die Sitzung nicht beendete, die es beenden sollte), ein
Datumsfehler, der in UTC unsichtbar ist, eine Reihe Stellen, an denen das Werkzeug das Richtige tut
und nichts darüber sagt, und drei Stellen, an denen das README nicht mehr stimmte. Alles im eigenen
Abschnitt weiter unten.

**Das Nächste ist der Datenbankzyklus.** Am 23.08.2026 entschieden: die Instanz
ablaufen lassen und **eine neue 30-Tage-Instanz** aufziehen. Damit ist es kein Termin, sondern ein
wiederkehrender Vorgang; der erste Durchlauf fällt auf den 07.09.2026. Das Blatt dafür steht in
[`docs/DATENBANKWECHSEL.md`](DATENBANKWECHSEL.md). **Seit Etappe 16 hängt daran eine zweite
Entscheidung:** `render.yaml` steht auf `region: frankfurt`, und Render legt eine Region beim
Anlegen fest — der Zyklus ist der Moment, an dem das ohne zusätzliche Migration wirkt.

**Die Folge, die man kennen muss:** eine Datenbank, die alle 30 Tage neu anfängt,
hält keine Arbeitszeitnachweise. § 16 Abs. 2 ArbZG verlangt zwei Jahre, und das ganze Werkzeug ist
darauf gebaut — die Aufbewahrungsfrist nimmt Zuweisungen aus, Löschen anonymisiert. **Ein Zyklus
ohne Rückspielen macht das zunichte.** Das ist eine Feststellung, keine Empfehlung: es aufzulösen
heißt entweder jeden Zyklus zu sichern und zurückzuspielen oder einen bezahlten Plan zu nehmen,
und beides ist eine Entscheidung des Betreibers.

Der Sprung vom Bestandsstand `0007` auf `0017` ist geprobt (Etappe 11), die neue Instanz selbst
liegt beim Betrieb.

**Die Roadmap ist abgearbeitet.** Etappe 8 brachte den geführten Schichttausch, Etappe 9 die
letzten beiden ArbZG-Regeln, Etappe 10 die Nachweise. Damit ist jeder Punkt umgesetzt, den das
Entwurfsdokument und das README als offen führten.

**Was jetzt kommt, ist vollständig eine Frage des Betriebs.** Es gibt keine Fortsetzung mehr,
die sich aus dem Vorhandenen ergibt. Was sich beim Bauen aufgedrängt hat und bewusst liegen blieb,
steht in den Specs unter „Bewusst nicht dabei" — jeweils mit dem Grund. Die auffälligsten:

| Naheliegend | Warum es liegen blieb |
|---|---|
| „Mindestens ein Ersthelfer je Schicht" | Eine Anzahl innerhalb einer Anzahl, eigenes Modell |
| Warnung, wenn ein Nachweis demnächst abläuft | Braucht eine Frist, und die legt der Betreiber fest |
| Geteilte Pausen nach § 4 Satz 2 | Eigene Tabelle; ohne sie ist das Tool strenger, nicht laxer |
| Benachrichtigungen beim Tauschantrag | Es gibt keinen Versandweg außer den Einladungsmails |
| Anforderungen am Bedarfsband statt an der Schichtart | Kostete die Einheit, die HR benennt und wiedererkennt |

**Eine Erfahrung aus drei Aufräum-Etappen, die man sich sparen kann:** von den rund
dreißig Einträgen dieser Liste waren **vier bereits erledigt**, ohne dass es jemand notiert hatte.
Erledigtes ist deshalb durchgestrichen statt gelöscht — wer später liest, sieht dann, dass es
geprüft wurde. Und jede der drei Etappen begann mit einer Prüfung, nicht mit einer Behebung.

**Bevor du daraus etwas nimmst: prüfe, ob es noch stimmt.** In Etappe 6a war einer der Befunde
längst behoben, und ungeprüft danach zu arbeiten hieße, Vorhandenes zu „reparieren".

**Lies vorher zwei Abschnitte:** Fallstricke dieses Projekts und Zurückgestellte Befunde.

**Was nicht am Code hängt:** der Umgang mit der ablaufenden Datenbank (07.09.2026), das
Datenbankpasswort und die IP-Freigabe. Details unter „Offen — liegt beim Betrieb“.

## Aktueller Stand

| | |
|---|---|
| `main` | Etappe 5 bis 14 gemergt und deployt (PR #16–#36); `/health` meldet `database: ok`, Stand `0017` |
| Branch-Situation | Keine offenen Branches, keine offenen Pull Requests |
| Aktueller Branch | keiner — `main` ist der Stand |
| Testsuite | 579 passed / 49 skipped (Postgres-only, lokal übersprungen), warnungsfrei unter `-W error::DeprecationWarning`; dazu 52 Frontend-Tests (Vitest + Testing Library) |
| CI | 4 Jobs: `backend (3.13)`, `backend (3.14)`, `backend-postgres`, `frontend` (letzterer führt seit Etappe 3 zusätzlich `npm test -- --run` aus) — alle grün auf `main` |
| Migrationen | `0001`–`0017`. `0017_qualifications` legt den Nachweiskatalog und zwei Verknüpfungstabellen an |
| Laufzeitabhängigkeiten (Backend) | unverändert fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata — auch nach Exporten und DSGVO |
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

Plan: [`docs/plaene/2026-08-16-etappe-1-arbeitszeitfenster.md`](plaene/2026-08-16-etappe-1-arbeitszeitfenster.md)

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

Plan: [`docs/plaene/2026-08-17-etappe-2-individuelle-zeiten.md`](plaene/2026-08-17-etappe-2-individuelle-zeiten.md)

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

**Nächster Schritt war:** Abschluss-Review für Etappe 2 einholen, dann PR
nach `main`. Stattdessen wurde — mangels Merge von PR #13 — direkt auf einem gestapelten Branch
mit Etappe 3 weitergearbeitet (siehe dortiger Abschnitt und die Branch-Situation oben); die
Gesamtdurchsicht für Etappe 2 steht weiterhin aus.

## Etappe 3 — abgeschlossen

Plan: [`docs/plaene/2026-08-18-etappe-3-oeffnungszeiten-bedarf.md`](plaene/2026-08-18-etappe-3-oeffnungszeiten-bedarf.md)

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
Aufgabe 4/5 und `coverage.py` als verbotener Modulname; beide jetzt in der Liste "Fallstricke
dieses Projekts" unten als Punkte 15 und 16.

**Nächster Schritt:** Eine gemeinsame Abschluss-Review-Runde für Etappe 2
UND Etappe 3 einholen (für Etappe 2 steht sie komplett aus, siehe oben; für Etappe 3 sind nur
die acht Einzel-Task-Reviews gelaufen, keine Gesamtdurchsicht), dann beide PRs (#13 zuerst,
danach #14) nach `main` mergen — in dieser Reihenfolge, weil #14 auf #13 aufbaut. Danach
Etappe 4 (Zuschnitt im Planer) auf einem neuen Branch ab `main` beginnen.

## Etappe 4 — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-22-etappe-4-zuschnitt-design.md`](entwuerfe/2026-08-22-etappe-4-zuschnitt-design.md)
Plan: [`docs/plaene/2026-08-22-etappe-4-zuschnitt.md`](plaene/2026-08-22-etappe-4-zuschnitt.md)
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

## Etappe 5 — kein Vorhaben, sondern ein Bündel

Die Roadmap führt „Etappe 5 — restliche Produktionsreife" als einen Punkt. Das sind sechs
unabhängige Dinge: `shift_requirements` entfernen, Veröffentlichen-Workflow, Audit-Log,
Exporte, DSGVO und das Arbeitszeitrecht. **Jedes gehört einzeln durch Spec → Plan → Umsetzung**,
nicht als ein Umsetzungsplan.

Auch das Arbeitszeitrecht allein zerfällt in drei:

| Teil | Inhalt | Stand |
|---|---|---|
| **5a** | Ruhepausen nach § 4, Arbeitszeit netto statt brutto | ✅ umgesetzt, siehe unten |
| **5b** | Höchstens sechs Tage in Folge, 15 freie Sonntage im Jahr | ✅ umgesetzt, siehe unten |
| **5c** | Achtstundenschnitt nach § 3 Satz 2, rollierend über 24 Wochen, gemeldet statt erzwungen | ✅ umgesetzt, siehe unten |
| **5d** | Feiertagskalender mit Bundeslandauswahl | ✅ umgesetzt, siehe unten |
| **5e** | `shift_requirements` entfernen — das lose Ende aus Etappe 4 | ✅ umgesetzt, siehe unten |

Zwei Entscheidungen dazu sind bereits gefallen und gelten für 5b und 5c:

- **Durchsetzung gemischt.** Die Sonntagsregeln gehören hart in den Generator — sie hängen an
  Vergangenheit und Gegenwart und sind beim Planen entscheidbar. Der Achtstundenschnitt wird
  nur gemeldet: ob zehn Stunden heute zulässig sind, entscheidet sich erst in den nächsten fünf
  Monaten, und ihn beim Erzeugen zu erzwingen hieße entweder falsch zu rechnen oder unnötig zu
  beschränken.
- **Kein Schalter „Sonntagsarbeit zulässig".** § 9 verbietet Sonn- und Feiertagsarbeit,
  § 10 nimmt ganze Branchen aus — ob dieser Betrieb darunterfällt, ist eine Tatsache über den
  Betrieb. Ein Schalter täte aber nichts, was die Öffnungszeiten nicht schon tun: ein sonntags
  geschlossener Betrieb hat keinen Sonntagsbedarf und bekommt keine Blöcke.

**Alle drei Regeln von 5b und 5c sind monatsübergreifend**, der Generator sieht aber nur seinen
einen Monat. `constraint_warnings()` fragt dagegen bewusst ohne `schedule_id`-Filter ab und
sieht über Monatsgrenzen. Für 5b muss die Vorgeschichte je Mitarbeiter in `app.py` geladen und
dem Planer mitgegeben werden — das ist der strukturelle Kern dieser Teilaufgabe.

## Etappe 5a — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-22-etappe-5a-ruhepausen-design.md`](entwuerfe/2026-08-22-etappe-5a-ruhepausen-design.md)
Plan: [`docs/plaene/2026-08-22-etappe-5a-ruhepausen.md`](plaene/2026-08-22-etappe-5a-ruhepausen.md)
PR #17, acht Commits, gemergt am 22.08. 18:29 als `c74032a`, Deploy live

| Task | Stand | Commit |
|---|---|---|
| 1 Die zwei Rechenfunktionen | ✅ | `b2b27a7` |
| 2 Spalte `break_minutes` und der Weg durch die API | ✅ | `70d9981` |
| 3 Netto-Arbeitszeit im Suchkern | ✅ | `bdc66f3` |
| 4 Netto und Pausenwarnung auf dem Handkorrektur-Pfad | ✅ | `8a9f7e8` |
| 5 Frontend | ✅ | `3963d3b` |
| 6 Dokumentation | ✅ | `ec85081` |
| Merge nach `main` | ✅ PR #17 | `c74032a` |

### Die zwei Dinge, die man wissen muss

**Die Mindestpause wird auf die Spanne aufgelöst, und die Kante liegt bei 9:30 h, nicht 9:00.**
§ 4 bemisst die Pause an der Arbeitszeit, die Arbeitszeit ist aber die Spanne minus Pause —
wörtlich gelesen dreht sich die Regel im Kreis. Aufgelöst über die kleinste Pause, die für die
Arbeitszeit ausreicht, die sie selbst erzeugt. Bei 9:30 h Spanne bleiben nach 30 Minuten genau
neun Stunden, und neun Stunden sind nicht „mehr als neun"; erst ab 9:31 h reichen 30 Minuten
nicht mehr.

**Anwesenheit und Arbeitszeit sind seither zwei Größen.** Netto rechnen die Tages- und
Wochengrenze auf beiden Pfaden. Brutto bleiben Deckung, Überschneidung, Ruhezeit und die
Fensterprüfung. Die Gegenprobe dazu steht in `test_api_coverage.py` und ist der wichtigste Test
der Etappe: eine Zuweisung mit Pause deckt weiterhin ihre volle Anwesenheit ab. Wäre die
Deckung mit umgestellt worden, entstünde je Block eine halbe Stunde Lücke, die niemand je
schließen könnte — jede Ersatzperson brächte ihre eigene Pause mit.

### Abweichung vom Plan

Der Plan sah ein Feld `working_minutes` am Slot vor. Beim Umsetzen brachen drei Gegenproben,
weil die Testhelfer ihre Slots von Hand bauen und das Feld nicht kannten — `slot.get()` lieferte
`None`, und die Prüfung **übersprang still**. Eine Grenze, die einfach aufhört zu greifen, ist
die schlechteste Art kaputtzugehen. Die Nettozeit wird deshalb über `slot_working_minutes()`
abgeleitet statt gespeichert; ein Slot mit Zeiten hat damit immer eine Arbeitszeit, und niemand
kann ein Feld vergessen.

### Was das an Bestehendem geändert hat

Die Umstellung auf netto **lockert** die Grenzen aus Etappe 1 und 4, ohne dass jemand etwas
angefasst hat: fünf Achtstundentage sind 40 Stunden Anwesenheit, aber 37,5 Stunden Arbeitszeit.
Zwei Bestandstests mussten ihre Erwartungen nachziehen (10,0 → 9,5 und 11,0 → 10,5 Std.).

Dazu ein wiederkehrender Fehler, der jetzt allgemein gelöst ist: der Rundlauftest von `0008`
nahm an, `0008` sei die letzte Migration — derselbe Fehler, den `0007` in Etappe 4 hatte. Statt
ihn ein drittes Mal zu machen, rollen alle drei über den gemeinsamen Helfer `zurueck_bis()`
zurück, bis ihre eigene Version an der Reihe war.

### Zum Merge

Alle vier CI-Jobs grün, einschließlich `backend-postgres` — der einzige Ort, an dem der
Rundlauf von `0009` gegen Postgres läuft.

**Kein Browser-Durchlauf gefahren.** Die Oberfläche ist nur über die 18 Vitest-Tests belegt.

## Etappe 5b — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-22-etappe-5b-sonntage-design.md`](entwuerfe/2026-08-22-etappe-5b-sonntage-design.md)
Plan: [`docs/plaene/2026-08-22-etappe-5b-sonntage.md`](plaene/2026-08-22-etappe-5b-sonntage.md)
PR #18, acht Commits, gemergt am 22.08. 21:22 als `a6e06e2`, Deploy live

| Task | Stand | Commit |
|---|---|---|
| 1 Sechstageregel im Suchkern | ✅ | `2dc430e` |
| 2 Sonntagsbudget im Suchkern | ✅ | `af2d4ee` |
| 3 Vorgeschichte über den Monatsrand | ✅ | `6e4d2e0` |
| 4 Warnungen auf dem Handkorrektur-Pfad | ✅ | `29029a1` |
| 5 Dokumentation | ✅ | `370d68f`, `63376be` |
| Merge nach `main` | ✅ PR #18 | `a6e06e2` |

**Kein Schemaeingriff** — die erste Etappe seit 0 ohne Migration. Beide Größen werden gerechnet.

### Die drei Dinge, die man wissen muss

**Die Sechstageregel ist strenger als § 11 Abs. 3.** Wer Montag bis Sonntag durcharbeitet und
am Montag darauf frei hat, erfüllt die Norm — die Regel lehnt ihn trotzdem ab. Bewusst so: der
Ersatzruhetag ist eine Bedingung über das *Fehlen* von Zuweisungen und lässt sich erst
beurteilen, wenn der ganze Monat steht. Sechs Tage in Folge sind lokal prüfbar und decken
sowohl das Zweiwochenfenster der Sonntage als auch das Achtwochenfenster der Feiertage ab.

**Der Generator liest erstmals außerhalb seines Monats.** `scheduling_history()` in `app.py`
lädt zwei Zahlen je Mitarbeiter. Die Falle dabei: `generate_schedule_route()` löscht die
Zuweisungen des Monats erst *nach* dem Suchlauf, sie stehen beim Laden also noch in der
Datenbank. Abgegrenzt wird deshalb über den **Datumsbereich**, nie über `schedule_id`.

**Beide Regeln hängen daran, dass der Aufrufer die Felder mitgibt** (`max_consecutive_days`,
`sundays_worked_in_year`) — genau wie `min_rest_hours`. Der erste Anlauf prüfte bedingungslos
und riss sieben der 23 Bestandstests; die Regel des Projekts ist da eindeutig. Nebenbei war die
bedingungslose Fassung auch teuer: die Suite lief 100 statt 42 Sekunden.

### Herausgelöst: Etappe 5d — Feiertagskalender

Zunächst war ein eingebauter Kalender mit Bundeslandauswahl für 5b vorgesehen. Beim
Ausarbeiten zeigte sich, dass er **keine Regel durchsetzt**: § 11 Abs. 3 für Feiertage ist
durch die Sechstageregel abgedeckt, § 9 wird über die Öffnungszeiten entschieden, und § 11
Abs. 1 betrifft nur Sonntage. Was bleibt, ist Kennzeichnung und Warnung — echter Nutzen, aber
Bewusstsein statt Regeldurchsetzung.

**Für 5d gilt damit als entschieden:** eingebauter Kalender mit Bundeslandauswahl, bewegliche
Feiertage über die Osterrechnung, regionale Sonderfälle unterhalb der Bundeslandebene
(Fronleichnam in Teilen von Sachsen und Thüringen, Mariä Himmelfahrt in katholischen
bayerischen Gemeinden, das Augsburger Friedensfest) ausdrücklich nicht abgedeckt. Feiertage
werden **nicht** automatisch geschlossen — das entscheiden weiterhin die Öffnungszeiten.

### Zum Merge

Alle vier CI-Jobs grün. **Kein Browser-Durchlauf gefahren** — diese Etappe hat allerdings
keine Oberfläche berührt, die Warnungen kommen fertig übersetzt aus dem Backend.

## Etappe 5e — die alte Bedarfsquelle entfernt

Spec: [`docs/entwuerfe/2026-08-22-etappe-5e-bedarfsquelle-design.md`](entwuerfe/2026-08-22-etappe-5e-bedarfsquelle-design.md)

Aufräumen, kein Nutzenversprechen an HR. `shift_requirements` wurde seit Etappe 4 geschrieben
und gespeichert, aber von nichts mehr gelesen, was den Plan beeinflusst; die übergeordnete Spec
sah die Entfernung ausdrücklich „erst nach Etappe 4" vor.

Weg sind: die Tabelle (Migration `0010`), `replace_shift_requirements()`, die drei
`requirements_*`-i18n-Schlüssel, das Feld in beiden Serialisierungen und im Frontend-Payload.

**`build_slots()` bleibt** — sie liest die Tabelle gar nicht, sondern erwartet die Zahlen im
übergebenen Dict. Zwei Aufrufer bleiben: der Benchmark als Vergleichsbasis der Etappe-4-
Umstellung, und die 23 Bestandstests. Dass sie damit auf keinem Produktionspfad mehr steht,
steht jetzt in ihrem Docstring.

**`requirements` im Rumpf wird ignoriert, nicht abgelehnt.** Ein `400` wäre die strengere
Lesart, bräche aber jeden Aufrufer, der noch die alte Form schickt, ohne dass er etwas falsch
macht.

Drei Dinge, die beim Umsetzen auffielen:

- **`0007` bleibt unangetastet.** Sie liest `shift_requirements` und ist Geschichte. Auf einer
  frischen Datenbank läuft die Kette `0001` → `0007` → `0010` durch: anlegen, nichts vorfinden,
  entfernen.
- **Ein Rundlauftest musste umgedreht werden.** `test_ableitung_laesst_bestehende_baender_
  unangetastet` legte seine Testdaten an, nachdem alle Migrationen gelaufen waren — nach `0010`
  gibt es die Tabelle dort nicht mehr. Es rollt jetzt erst bis `0007` zurück und legt die Daten
  dann an, was ohnehin die wahrheitsgetreuere Anordnung ist.
- **Kein eigenes `table_exists()`.** `table_columns()` liefert für eine fehlende Tabelle eine
  leere Menge, und eine Tabelle ohne Spalten gibt es nicht. Ein zweiter Helfer wäre dieselbe
  Frage in einer zweiten Fassung, samt der Postgres-Eigenheit mit `current_schema()`, die dort
  schon gelöst ist.

## Etappe 5c — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-22-etappe-5c-durchschnitt-design.md`](entwuerfe/2026-08-22-etappe-5c-durchschnitt-design.md)

Die letzte offene Regel aus Etappe 4. `GET /schedules/<year>/<month>` liefert neben
`coverage_gaps` jetzt `average_hours` — die Mitarbeiter, deren Arbeitszeit über 24 Wochen den
Achtstundenschnitt aus § 3 Satz 2 reißt. **Gemeldet, nicht erzwungen**: ob zehn Stunden heute
zulässig sind, entscheidet sich erst in den kommenden Monaten.

Zwei Dinge aus der Recherche, die man leicht falsch macht:

- **Der Arbeitgeber wählt den Bezugszeitraum** — sechs Kalendermonate *oder* 24 Wochen — und
  darf ihn rollierend legen. Gebaut sind 24 Wochen, endend am Letzten des angezeigten Monats.
- **Gerechnet wird je Werktag**, nicht je gearbeitetem Tag und nicht je Kalendertag. Montag bis
  Samstag, also 144 in 24 Wochen. Ein großzügiger Nenner: fünf Achtstundentage die Woche
  ergeben rund 6,2 Stunden je Werktag. Das ist die Norm, keine Nachlässigkeit.

**Die bekannte Lücke, und sie zeigt in die unangenehme Richtung:** Feiertage zählen mangels
Kalender als Werktage und blähen den Nenner um rund drei Prozent. Die Meldung ist dadurch zu
nachsichtig — sie kann eine Überschreitung übersehen, nie eine erfinden. Löst sich mit 5d.

Kein Schemaeingriff.

## Etappe 5d — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-22-etappe-5d-feiertage-design.md`](entwuerfe/2026-08-22-etappe-5d-feiertage-design.md)

`backend/holidays.py`: neun bundesweite und zehn regionale Feiertage, Ostern über den anonymen
gregorianischen Algorithmus, Buß- und Bettag als Mittwoch vor dem 23.11. Keine Bibliothek —
zwölf Zeilen Arithmetik plus eine Tabelle.

Das Bundesland ist eine Einstellung (`holiday_region` in der neuen `settings`-Tabelle,
Migration `0011`). **Ohne Auswahl kennt das Tool keine Feiertage** und verhält sich wie zuvor;
es gibt bewusst keinen Standard.

**Feiertage werden nicht automatisch geschlossen** — das entscheiden die Öffnungszeiten, weil
das Tool nicht wissen kann, ob der Betrieb unter § 10 fällt. Der Kalender kennzeichnet und
warnt.

**Die eine Stelle, an der er eine Rechnung schärft:** der Achtstundenschnitt aus 5c zählte
Feiertage als Werktage und war dadurch zu nachsichtig. Mit gewähltem Bundesland fallen sie aus
dem Nenner. Der Test dazu ist der aufwendigste der Etappe, weil die Stundenzahl zwischen beiden
Grenzen liegen muss: das Fenster 16.04.–30.09.2026 enthält vier bayerische Feiertage auf
Werktagen, 144 Werktage werden zu 140, die erlaubten 1152 Stunden zu 1120 — 87 Schichten von
13 Stunden sind 1131 und liegen dazwischen.

**Unterhalb der Bundeslandebene kennt der Kalender nichts** — Fronleichnam in katholischen
Gemeinden Sachsens und Thüringens, Mariä Himmelfahrt in Bayern, das Augsburger Friedensfest.
Er ist damit in der nachsichtigen Richtung unvollständig: einen Feiertag zu wenig, nie einen zu
viel. Betroffene tragen den Tag als Öffnungszeit-Ausnahme ein.

**Was einen roten CI-Lauf gekostet hat:** `0011_settings` hatte zuerst `name` als natürlichen
Primärschlüssel und keine `id`-Spalte. Die Dialektschicht hängt an jedes `INSERT` ein
`RETURNING id` an — auf SQLite unbemerkt, auf Postgres ein `UndefinedColumn`. Steht jetzt als
Fallstrick 16 und hat einen eigenen Schreibtest gegen Postgres bekommen.

Die regionalen Feiertage sind **paarweise** getestet — je ein Land mit und eines ohne. „Gilt in
Bayern" allein wäre auch grün, wenn der Feiertag überall stünde.

## Etappe 5f — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-5f-veroeffentlichen-design.md`](entwuerfe/2026-08-23-etappe-5f-veroeffentlichen-design.md)

`schedules.status` gab es seit dem ersten Commit und wurde von nichts gelesen — jeder Plan war
sichtbar, sobald er erzeugt war. Jetzt ist er `draft` oder `published`, dazu `published_at`
(Migration `0012`).

**Die Migration setzt alle Bestandspläne auf `published`.** Das ist die Richtung, auf die es
ankommt: eine Migration darf nicht ändern, was Leute gestern sehen konnten. Ein eigener Test
hält es fest.

Zwei Übergänge sind bewusst asymmetrisch und stehen so im README:

- **Neuerzeugen** setzt einen veröffentlichten Plan zurück auf Entwurf — er verwirft ohnehin
  jede Handkorrektur, und den Mitarbeitern stillschweigend einen anderen Plan unterzuschieben
  wäre schlechter als ein sichtbares Zurücksetzen.
- **Eine Handkorrektur** tut das nicht. Sonst wäre das Veröffentlichen unbenutzbar.

Für Mitarbeiter ist ein Entwurf ein `404` — aber mit eigener Meldung. Dafür musste
`fetchSchedule()` im Frontend umgebaut werden: es lieferte bisher nur `null` und verschluckte
die Servermeldung. Es gibt jetzt `{data, message}` zurück, und die beiden Stellen, die den Plan
auf `null` setzen, leeren die Meldung mit — sonst stünde nach dem Löschen noch „noch nicht
veröffentlicht" für einen Plan, den es nicht mehr gibt.

**Kein Frontend-Test für die Schaltfläche.** `SchedulePage.jsx` hat auch bisher keinen — die
Komponente hängt an einem guten Dutzend API-Aufrufen, und der Aufwand für einen sinnvollen Test
gehört in eine eigene Aufgabe. Die Logik ist backendseitig durch zehn Tests gedeckt.

## Etappe 5g — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-5g-audit-log-design.md`](entwuerfe/2026-08-23-etappe-5g-audit-log-design.md)

Ein `after_request`-Haken protokolliert jede verändernde Anfrage: Zeitpunkt, Benutzer, Methode,
Pfad, Status. Eine Stelle, lückenlos per Konstruktion — und **ohne Anfrageinhalte**, weil die
Krankmeldungen enthalten und das Art.-9-Daten sind. Der Preis steht im README: das Log sagt,
*dass* etwas geändert wurde und von wem, nicht worauf.

Kein Fremdschlüssel auf `users`, Benutzername als Kopie: Konten werden gelöscht, und ein
Protokoll, dessen Einträge mit dem Konto verschwinden, ist keines.

**Drei Dinge, die beim Bauen schiefgingen und deshalb Kommentare tragen:**

1. **Der Haken committete die halbfertige Arbeit fehlgeschlagener Anfragen.** Er benutzte die
   Verbindung der Anfrage, und `commit()` nahm mit, was die gescheiterte Route offen gelassen
   hatte. Gefangen von einem Bestandstest — ein ungültig angelegter Mitarbeiter blieb plötzlich
   stehen. Jetzt `rollback()` vor dem Schreiben.
2. **Die naheliegende Lösung war zu teuer.** Eine eigene Verbindung je Anfrage ist entkoppelter,
   verdoppelte aber die Testlaufzeit (68 → 134 s) und wäre in Produktion eine zusätzliche
   Postgres-Verbindung pro Schreibzugriff auf einer Instanz mit begrenztem Vorrat.
3. **Das `try/except` verschluckte einen `NameError` und schrieb still gar nichts.** Genau die
   Fehlerart, die ein solcher Haken erzeugt. Der erste Test der Datei prüft deshalb
   ausdrücklich, dass ein Eintrag *entsteht*.

**Die Aufbewahrungsfrist kam in 5i nach** — das Log ist selbst personenbezogen und fällt jetzt
mit der Sechsmonatsfrist weg. Eine Route zum Leeren gibt es weiterhin nicht: was sich auf
Knopfdruck leert, ist kein Protokoll.

## Etappe 5h — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-5h-exporte-design.md`](entwuerfe/2026-08-23-etappe-5h-exporte-design.md)

**Die Abhängigkeitsfrage aus dem Handoff hat sich aufgelöst, nicht gestellt.** iCal ist ein
Textformat und braucht rund vierzig Zeilen, CSV steht in der Standardbibliothek. PDF und Excel
warten, bis jemand sie tatsächlich verlangt — dann ist es eine Entscheidung mit Anlass statt
einer auf Vorrat. Die Laufzeitabhängigkeiten bleiben bei fünf.

iCal je Mitarbeiter und Monat, `require_self_or_hr`, **nur veröffentlichte Pläne, auch für HR**
— der Zweck der Datei ist, das Haus zu verlassen. Die CSV ist HR-only und liefert auch
Entwürfe; der Unterschied ist der Empfänger.

**Drei Details, an denen solche Exporte scheitern, und alle drei haben Tests:**

1. **iCal verlangt CRLF.** Manche Kalender lehnen die Datei sonst wortlos ab — ohne Fehler,
   einfach ohne Termine.
2. **Die CSV braucht Semikolon und BOM**, sonst geht sie in Excel im deutschsprachigen Raum
   nicht auf.
3. **Der Download geht über ein authentifiziertes `fetch`, nicht über einen `<a href>`.**
   Frontend und Backend liegen auf verschiedenen Domains; ein Klick trüge weder Token noch (unter
   Safaris ITP) Cookie, und die Datei käme als 401 zurück — oder schlimmer als HTML-Fehlerseite
   unter einem `.ics`-Namen.

**Keine Zeitzone im iCal.** Das Tool rechnet in Ortszeit und speichert keine Zone; eine
erfundene wäre eine Behauptung, die die Daten nicht tragen. Ein Kalender in anderer Zone
verschiebt die Termine — steht im README.

## Etappe 5i — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-5i-dsgvo-design.md`](entwuerfe/2026-08-23-etappe-5i-dsgvo-design.md)

Zwei Festlegungen kamen vom Nutzer: **sechs Monate** Aufbewahrung, und beim Löschen wird
**anonymisiert**. Beide prägen alles Weitere.

**Der Konflikt, der zuerst zu klären war — und der beim nächsten Mal sofort auffällt, wenn
sie ihn nicht kennt:** sechs Monate lassen sich *nicht* auf den Dienstplan anwenden.
[§ 16 Abs. 2 ArbZG](https://www.gesetze-im-internet.de/arbzg/__16.html) verlangt, Nachweise über
die acht Stunden hinausgehende Arbeitszeit **mindestens zwei Jahre** aufzubewahren. Einen Plan
mit Zehnstundentagen nach sechs Monaten zu löschen wäre der Verstoß gegen eine Norm zur
Erfüllung einer anderen. Die Frist gilt deshalb nur für das, was *über* die
Arbeitszeitaufzeichnung hinausgeht: Krank- und Urlaubsmeldungen und das Änderungsprotokoll.

**Der Abwesenheitsgrund steht doppelt.** Er liegt in `employee_absences` **und** denormalisiert
in der Zuweisung, die er freigemacht hat (`absence_type`, `absent_employee_id`). Nur die eine
Tabelle zu räumen ließe die Gesundheitsangabe im Dienstplan stehen — genau der Punkt, den man
übersieht. Beide Orte werden geräumt, mit eigenem Test.

**Und beim Löschen genauso** — das hat erst das CodeRabbit-Review in PR #25 gefunden. Die
Anonymisierung leerte `employee_absences` und ließ den Grund in der Zuweisung stehen, samt
`absent_employee_id`. Die Gesundheitsangabe hätte die gelöschte Person um Monate überlebt, bis
die Aufbewahrungsfrist sie eingeholt hätte. **Die Lehre:** ein doppelter Speicherort ist an
*jedem* Löschweg doppelt, nicht nur an dem, an dem man ihn bemerkt hat.

**Löschen heißt anonymisieren.** Vorher setzte `ON DELETE SET NULL` die Schichten der gelöschten
Person auf „unbesetzt": die Vergangenheit sah rückwirkend unterbesetzt aus, Deckungslücken
erschienen aus dem Nichts, und die Arbeitszeitaufzeichnung verlor genau die Zuordnung, die sie
ausmacht. Jetzt wird die Zeile zum Grabstein — Name ersetzt, E-Mail weg, `active` auf 0,
`anonymized_at` gesetzt, alles Persönliche daneben gelöscht —, und die Zuweisungen zeigen weiter
auf sie. Art. 17 Abs. 3 lit. b nimmt Verarbeitung aus, die einer rechtlichen Verpflichtung
dient; § 16 Abs. 2 ArbZG ist eine.

`DELETE /employees/<id>` behält seinen Namen und ändert seine Bedeutung. Die Antwort sagt es
ausdrücklich, und die Rückfrage in der Oberfläche auch.

**Kein Zeitplandienst, und das ist gesagt statt vorgetäuscht.** Der genutzte Render-Plan bietet
keinen. Geräumt wird beim Start der Anwendung — in der Praxis bei jedem Deploy — und auf
Knopfdruck über `POST /retention/purge`. Der Knopf meldet Zahlen je Tabelle; ein Aufräumen, das
schweigt, lässt niemanden wissen, ob es lief. Läuft die Instanz monatelang ohne Neustart durch,
räumt sie ohne den Knopf nicht.

**Die Auskunft nach Art. 15** (`GET /employees/<id>/data-export`, self-or-HR) liefert JSON, nie
den Passwort-Hash — das eine Feld, dessen Preisgabe die Auskunft selbst zum Sicherheitsproblem
machte. Ein Test hält das fest. JSON und nicht PDF, weil Art. 15 Abs. 3 ein gängiges
elektronisches Format verlangt und die Alternative eine Abhängigkeit für Papieroptik wäre.

**Bewusst nicht dabei:** Einwilligungsverwaltung (die Verarbeitung stützt sich auf das
Arbeitsverhältnis und § 16 ArbZG, nicht auf Einwilligung — eine Einwilligungsoberfläche
täuschte eine Rechtsgrundlage vor), ein Verarbeitungsverzeichnis nach Art. 30 (ein Dokument,
kein Programmteil), und ein Löschen der Arbeitszeitaufzeichnung nach zwei Jahren (§ 16 nennt ein
Minimum, kein Maximum — wann darüber hinaus gelöscht wird, ist wieder eine Festlegung des
Betreibers).

## Etappe 6a — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-6a-eingaben-design.md`](entwuerfe/2026-08-23-etappe-6a-eingaben-design.md)

Die erste Etappe aus den zurückgestellten Befunden. Genommen wurde die Teilmenge mit einer
gemeinsamen Eigenschaft: **eine Eingabe passiert die Prüfung und tut danach nichts.** Kein
Fehler, keine Meldung — die Zeile steht da, sieht richtig aus und verliert jeden späteren
Vergleich. Die schlechteste Fehlerart, die eine Anwendung haben kann, weil sie wie Erfolg
aussieht.

**Der Datumsfehler stand an sechs Stellen.** `date.fromisoformat()` akzeptiert seit Python 3.11
auch `'20260901'`; wer damit nur *prüft* und die rohe Zeichenkette speichert, legt eine Zeile an,
die nie zutrifft — das Tool vergleicht Daten durchgehend als Zeichenketten, und `-` kommt vor
`0`. Ein gesperrter Tag sperrte nichts, eine Krankmeldung machte keine Schicht frei, ein
Schließtag ließ den Betrieb offen. `parse_iso_date()` prüft **und** normalisiert; die
Fenstergrenzen aus Etappe 1 benutzen ihn jetzt auch.

**`max_daily_hours` hatte keine Obergrenze.** Der Handoff notierte den Widerspruch zu
`MAX_BLOCK_MINUTES = 600` und schlug vor, den Deckel einstellbar zu machen. Das war die falsche
Richtung: § 3 ArbZG erlaubt höchstens zehn Stunden, der Planer hat also recht. Jetzt `0 < Wert
<= 10`. Null war keine Arbeitszeitgrenze, sondern eine getarnte Deaktivierung.

**Die Lehre dieser Etappe steht im Review, nicht im Plan.** Ich hatte `int(True) == 1` an drei
Stellen behoben — genau den drei, für die ich Tests geschrieben hatte. CodeRabbit fand zwei
weitere: `parse_int_list()` (`unavailable_weekdays`, `allowed_shift_types`) und
`parse_optional_hours()`, wo `float(True)` eine Tagesgrenze von einer Stunde ergibt, also
innerhalb jeder gültigen Spanne und deshalb stumm. **Wer eine Fehlerklasse findet, behebt sie im
Parser, nicht an den Aufrufstellen, die ihm gerade eingefallen sind.**

## Etappe 6b — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-6b-anmeldeweg-design.md`](entwuerfe/2026-08-23-etappe-6b-anmeldeweg-design.md)

Beide Befunde am Anmeldeweg beschrieben denselben Mangel aus verschiedenen Richtungen: **die
Grenze von zehn Versuchen je Viertelstunde ließ sich umgehen.**

**Der Zweig für eingeladene Konten kehrte zurück, bevor irgendetwas gezählt wurde.** Seine
Meldung verrät — anders als die einheitliche Meldung überall sonst —, dass es diesen
Benutzernamen gibt. Das ist eine bewusste Abwägung zugunsten des eingeladenen Menschen und bleibt
so; unbegrenzt und ungezählt war sie aber eine Namensliste zum Nulltarif. Der Versuch wird jetzt
gezählt wie jeder andere.

**Prüfen und Zählen waren zwei Schritte.** N gleichzeitige Anfragen lasen alle denselben Stand
unterhalb der Grenze und kamen alle durch — aus zehn Versuchen wurden so viele, wie ein Angreifer
Verbindungen aufmacht. `security.attempt_guard()` serialisiert beides je Benutzername über einen
Postgres-Advisory-Lock, nach dem Vorbild von `_migration_lock()`.

**Je Benutzername und nicht global**, mit eigener Gegenprobe: ein globaler Lock stellt jede
Anmeldung im Haus hinter jede andere, und wäre im Haupttest ebenfalls grün. Die Zwei-Zahlen-Form
(`pg_advisory_lock(class, key)`) schließt eine Kollision mit dem Migrations-Lock aus, statt sie
nur unwahrscheinlich zu machen. Sitzungsgebunden statt transaktionsgebunden, weil der Sperrpfad
mit 429 antwortet, ohne zu committen.

**Auf SQLite bewusst kein Lock** — dieselbe Abwägung, die der Migrations-Runner notiert.

**Das Wichtigste dazu:** die beiden Race-Tests laufen **nur** im
`backend-postgres`-Job. Ein grüner Job allein beweist nichts; er könnte übersprungen haben.
Beim Merge von PR #27 wurde im Joblog nachgesehen, dass beide wirklich `PASSED` meldeten
(474 passed, 0 skipped). Wer die Drosselung anfasst, macht das wieder.

## Etappe 6c — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-6c-reste-design.md`](entwuerfe/2026-08-23-etappe-6c-reste-design.md)

Die letzten beiden Bündel: Eindeutigkeit auf `employee_availability` und die Testschulden.

**`PUT /shift-times` pflegte eine zweite Zeitprüfung neben `parse_assignment_times()`, und sie war
bereits auseinandergelaufen.** Gleicher Beginn und gleiches Ende wurden angenommen und von
`shift_duration_minutes()` als Lauf über Mitternacht gelesen — aus `10:00`–`10:00` wurde ein
Vierundzwanzigstundendienst. Für die Zuweisung war genau das in Etappe 2 behoben worden. Die
Route benutzt jetzt denselben Parser.

**Nur exakte Duplikate der Arbeitszeitfenster werden abgelehnt.** Zwei Fenster an einem Wochentag
sind der geteilte Dienst; Überlappungen zusammenzufassen hieße, eine Eingabe stillschweigend
umzuschreiben. Die Gültigkeitsgrenzen gehören in den Vergleich — gleiche Zeiten mit verschiedenen
Grenzen sind zwei Aussagen, nicht eine.

**Die Lehre steckt wieder im Review.** Der Umbau auf den gemeinsamen Parser führte einen neuen
Fehler ein: das Formular schickt geleerte Felder als `""`, der Parser macht `None` daraus — aber
die Rücksetz-Prüfung stand *davor*, also fiel `""` in ein `INSERT` mit NULL-Zeiten auf eine
`NOT NULL`-Spalte. Ein 500er, wo vorher eine verständliche 400 stand. **Wer eine Prüfung durch
eine andere ersetzt, verschiebt damit auch, wann Werte normalisiert werden — die Reihenfolge der
Zweige dahinter gehört zum Umbau, nicht zur Umgebung.**

## Etappe 7 — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-7-monatsgrenze-design.md`](entwuerfe/2026-08-23-etappe-7-monatsgrenze-design.md)

**Ein Monat ist ein Abrechnungszeitraum, keine Einheit der Ruhe.** Die elf Stunden aus § 5 Abs. 1
ArbZG und das Wochenstundenziel liefen quer über die Monatsgrenze und hörten an ihr auf: beide
leben nur im Suchzustand eines Laufs, und der begann am Ersten leer. Ein Nachtdienst bis 06:00 am
31. und ein Frühdienst ab 06:00 am 1. waren jeder für sich in Ordnung und ließen null Stunden Ruhe.

Der Sechs-Tage-Lauf und das Sonntagsbudget sahen die Grenze schon seit 5b — **weil das Zahlen
sind, und Zahlen lassen sich vorab reichen.** Ruhezeit und Wochenstunden brauchen Zeiten.

**Die Stelle, an der die naheliegende Lösung falsch gewesen wäre:** die flankierenden Tage liegen
*neben* `day_hours`, nicht darin. Sie zu verschmelzen wäre der offensichtliche Schritt —
`worked_dates()` liest genau diese Schlüssel, und ein Sonntag am Monatsrand wäre dann doppelt
belastet worden, einmal dort und einmal über `sundays_worked_in_year`.

**Und die Stelle, an der ich falsch abgekürzt habe.** Die erste Fassung las `start_time`/`end_time`
direkt aus der Zeile. Eine gespeicherte Zuweisung muss ihre Zeiten aber nicht selbst tragen — sie
kann sie aus einer Tagesausnahme oder aus der Schichtart beziehen, und `assignment_hours()` löst
genau diese drei Ebenen auf. Eine Nachtschicht aus der Vorlage war damit unsichtbar. Gefunden im
Review, nicht von mir.

**`boundary=None` stellt das alte Verhalten her.** Das ist es, was die 23 Kompatibilitätstests und
den Benchmark unverändert lässt.

## Etappe 8 — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-8-schichttausch-design.md`](entwuerfe/2026-08-23-etappe-8-schichttausch-design.md)

**Die tragende Entscheidung, und die einzige, die man wirklich kennen muss:** ein von
Mitarbeitern beantragter Tausch wird **abgelehnt**, wenn er zwingendes Arbeitszeitrecht bräche
(Ruhezeit, Tagesarbeitszeit, Pause, siebter Tag, Sonntagsbudget). Der Direkttausch der
Personalabteilung **warnt weiterhin nur**.

Der Grund ist nicht Vorsicht, sondern die Adressierung des Gesetzes: § 22 Abs. 1 ArbZG macht einen
Verstoß zur Ordnungswidrigkeit **des Arbeitgebers**, und §§ 3 und 5 lassen sich nicht durch
Einzelabrede abbedingen. Die Personalabteilung darf überstimmen, weil sie haftet und etwas wissen
kann, das das Tool nicht weiß (§ 14 Notfall, § 7 Tarifvertrag). Zwei Kolleginnen dürfen es nicht.

**Der Feiertag blockiert nicht.** § 9 verbietet, § 10 nimmt Branchen aus, und auf welcher Seite
dieser Betrieb steht, ist eine Tatsache über den Betrieb. Zu blockieren hieße, sie zu behaupten.
`ARBZG_BLOCKERS` in `app.py` führt die Grenze samt Begründung je Eintrag.

**Der Fehler, den ich fast ausgeliefert hätte:** der erste Entwurf ließ den Antragsteller beide
Schichten benennen. Ein Mitarbeiter sieht aber nur seine eigenen (5f) — das Merkmal wäre für seine
Hauptnutzer unbenutzbar gewesen. Aufgefallen erst beim Anschließen der Oberfläche. Jetzt nennt der
Antrag eine **Person**, und der Partner wählt selbst, was er dagegen gibt; `GET /colleagues` gibt
dafür Namen und nichts über Zeiten.

**`perform_swap()` tauscht und liest danach**; wer nur gefragt hat, rollt zurück. Vorher zu
urteilen beurteilte den falschen Zustand — zwei Schichten an benachbarten Tagen meldeten eine
Ruhezeitverletzung, die der Tausch gerade auflöst. Der Test dazu wird rot, wenn man die Reihenfolge
umdreht.

**Aus dem Review:** „dazwischen liegen Tage" reicht weiter als die Rechtslage. Setzt die
Personalabteilung eine der Schichten zwischendurch um, tauschte die Genehmigung sonst, *wer gerade
dort steht*. Und `break_minutes` gehört zum Platz wie die Zeiten — was mitreist, reist ganz mit.

## Etappe 9 — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-9-arbzg-rest-design.md`](entwuerfe/2026-08-23-etappe-9-arbzg-rest-design.md)

**§ 4 Satz 3 war nicht prüfbar, weil das Modell fehlte.** Das Tool kannte nur `break_minutes` —
eine Dauer ohne Uhrzeit. Eine halbe Stunde Pause ab Schichtbeginn erfüllt Satz 1, verstößt gegen
Satz 3 und sah in der Datenbank genauso aus wie eine mittige. § 4 Satz 1 verlangt ohnehin „im
voraus feststehende Ruhepausen"; eine Dauer ohne Lage steht nicht fest.

**Die Spalte bleibt NULL-bar und ohne Vorgabe**, und das ist die Entscheidung, die man hinterfragen
wird: für jeden Block, den dieses Tool bauen kann, gibt es *immer* eine zulässige Lage. Eine
fehlende Angabe ist deshalb nie ein bekannter Verstoß — sie zu bemängeln hieße, bei jedem Block zu
warnen, sie zu erzwingen, jeden Bestandsplan für ungültig zu erklären.

**Die § 10-Ausnahme schaltet § 11 nicht mit ab.** Die fünfzehn freien Sonntage und der
Ersatzruhetag sind das Gegengewicht *zu* § 10 und gelten gerade dann, wenn er greift. Eine
Ausnahme, die beides abschaltete, machte aus einer Erlaubnis eine Freistellung. Eigener Test.

**Die Lehre, und sie ist eine Wiederholung:** `perform_swap()` reichte `break_minutes` weiter,
`break_start` aber nicht — die Sperre stand in `ARBZG_BLOCKERS` und griff nie. Genau dasselbe war
eine Etappe zuvor mit `break_minutes` passiert. Fallstrick 24 sagt „was zum Platz gehört, reist
ganz mit"; **„ganz" heißt jedes Feld, nicht das zuletzt hinzugefügte.**

## Etappe 10 — abgeschlossen, gemergt, deployt

Spec: [`docs/entwuerfe/2026-08-23-etappe-10-qualifikationen-design.md`](entwuerfe/2026-08-23-etappe-10-qualifikationen-design.md)

Der letzte Punkt der Roadmap. **Die interessante Hälfte ist nicht die Zuordnung, sondern
`valid_until`**: ein Ersthelferschein läuft nach zwei Jahren ab (DGUV Vorschrift 1 § 26), und ein
Nachweis ohne Ablaufdatum ist einer, den der Dienstplan noch Jahre nach seinem Ende beachtet.

**Hart im Generator, Warnung bei der Handkorrektur, keine Sperre beim Tausch.** Die letzte
Entscheidung ist die, die man hinterfragen wird: ob ein Nachweis rechtlich verlangt ist oder eine
Hausregel, kann das Tool nicht wissen — dieselbe Zurückhaltung wie beim Feiertag in Etappe 9.

**Der Preis, und er steht im README:** die Anforderung hängt an der Schichtart, also erbt ein Block
ohne Vorlage nichts. Seit Etappe 4 schneidet der Planer genau solche Blöcke zu.

**Zwei Fehler, die das Review gefunden hat, und beide sind Wiederholungen:**

1. **Fallstrick 16 wieder.** Die beiden Verknüpfungstabellen bekamen einen zusammengesetzten
   Primärschlüssel statt einer `id` — sauber modelliert, auf SQLite grün, auf Postgres ein 500er in
   jeder schreibenden Route. Der lokale Lauf war grün, `backend-postgres` rot: genau die
   Konstellation aus Fallstrick 21. Der Postgres-Schreibtest hat getan, wofür er da ist.
2. **Die Anonymisierung übersah die Nachweise.** `delete_employee()` räumt seit 5i eine feste Liste
   personenbezogener Tabellen; die neue stand nicht darauf.

## Etappe 11 — abgeschlossen, gemergt, deployt

Keine Spec: das hier ist kein Vorhaben, sondern eine Probe vor einem Termin.

**Der Bestandsweg war ungeprüft.** Das Backup vom 22.08. steht auf `schema_migrations` mit sieben
Zeilen — Stand `0007`. Wer es zurückspielt, lässt zehn Migrationen über gefüllte Tabellen laufen.
`backend/test_migrations_bestand.py` baut genau das nach (0001–0006 anwenden, Daten einspielen,
dann 0007, dann der Rest) und prüft danach, dass nichts verloren geht, dass die abgeleiteten
Bänder das `DROP` in `0010` überleben, dass `0012` jeden Plan auf `published` hebt — **und dass
die heutige Anwendung den gehobenen Bestand liest.**

**Nachgebaute Daten, nicht der echte Dump.** Er enthält drei Namen und zweiundsechzig Schichten im
Klartext und gehört weder ins Repository noch in einen CI-Lauf.

**Der erste Tag hat eine Lücke gehabt:** mit einer Schichtart, aber ohne Bedarfsband antwortete
„Plan erzeugen" mit 201, null Blöcken, null gemeldeten Lücken und keinem Wort. Jetzt sagt es,
warum der Plan leer bleibt.

**Und die Testsuite hat meinen ersten Entwurf korrigiert.** Der lehnte mit 400 ab; 87
Bestandstests fielen um und zeigten damit, dass *einen leeren Plan anlegen und von Hand füllen*
ein gängiger Weg ist. **Die Beschwerde war das Schweigen, nicht die Erlaubnis** — gesagt statt
verboten.

**Zwei Annahmen vorher nachgerechnet statt CI raten lassen:** `coverage_curve()` verschmilzt Früh-
und Spätschicht zu einem Band (fünf statt vierzehn), und `GET /employees` blendet Grabsteine aus,
nicht Inaktive.

**Aus dem Review:** `.flash-warning` gab es im Stylesheet nie — seit Etappe 8 setzen mehrere
Seiten `type: 'warning'`, und der Kasten blieb unformatiert. Rückwirkend hat also auch die
Tauschseite ihre Hinweise unsichtbar angezeigt.

## Etappe 12 — abgeschlossen, gemergt, deployt

Keine Spec, wie 11: eine Lücke schließen, keine Etappe planen.

Etappe 11 hat behoben, dass „Plan erzeugen" auf einer leeren Datenbank schweigend nichts tut —
aber erst *nachdem* jemand gedrückt hat. `GET /setup-status` nennt es vorher, und die Planseite
zeigt es **nur, solange etwas fehlt.**

**Die Entscheidung, die man hinterfragen wird: nur drei Dinge stehen drin.** Kein aktiver
Mitarbeiter, keine Schichtart, kein Bedarfsband — mehr verhindert keinen Plan. Eine Liste, die
auch alles Wählbare aufzählt, ist eine Aufgabenliste, die nie leer wird, und eine Liste, die nie
leer wird, wird ignoriert.

**Daneben `notes`** für das, was wissenswert ist und nichts verhindert (fehlendes Bundesland).
`ready` bleibt `true`, auch wenn Hinweise offen sind — mit eigenem Test.

**In keiner der beiden Listen: die § 10-Frage.** „Nicht ausgenommen" ist keine fehlende Angabe,
sondern genau das, was § 9 Abs. 1 sagt. Sie als Mangel zu führen hieße, den Regelfall zum
Versäumnis zu erklären.

Im Browser durchgespielt statt behauptet: leere Datenbank → drei benannte Lücken mit Link →
gesetzt → Kasten verschwindet → 21 Schichten, vollständig besetzt.

## Etappe 13 — abgeschlossen, gemergt, deployt

**Die beiden Leistungsbefunde sind erledigt, und zwar durch Messen.** Sie trugen seit ihrer
Aufnahme die Notiz „erst angehen, wenn der Benchmark es zeigt"; gelaufen ist er dafür nie.

`benchmark.py` endet jetzt mit einer Skalierungsprobe auf dem Produktionspfad, halbe Belegschaft
im Fenster-Modus — genau dort sitzen beide Befunde.

**Der Zuschnitt ist nicht der Engpass:** 1,36 Sekunden bei 2480 Blöcken. Die Notiz zu `plan_day()`
ist damit eingelöst, mit Nein.

**Die Wand ist eine andere, und sie war unbekannt.** `backtrack()` rekursiert einmal je Platz —
die Blockzahl eines Monats *ist* die Stapeltiefe. Bei Pythons Standardgrenze laufen 930 Blöcke
durch und 992 nicht mehr, also rund dreißig Blöcke am Tag: eine große Station, kein Gedankenspiel.
Gescheitert ist es mit einem `RecursionError` an beliebiger Stelle tiefer (bei der Messung in
`locale.getlocale()`), über die API als 500er.

Jetzt eine benannte Ausnahme mit beiden Zahlen. **Die Grenze ist abgeleitet, nicht
festgeschrieben** — aus `sys.getrecursionlimit()` und der aktuellen Stapeltiefe; unter Gunicorn
ist sie eine andere als in einem Test.

**Was bewusst offen bleibt, mit Kosten:** die Rekursion in eine Schleife umzuschreiben ist ein
Eingriff in das heikelste Stück des Projekts (Branch-and-Bound samt Rücknahme von sechs
Zustandsstrukturen, und die 23 Bestandstests decken nur Schichtzahlen ab). Die Rekursionsgrenze
hochzusetzen verschiebt die Wand und tauscht eine saubere Ausnahme gegen einen möglichen harten
Absturz. **Eine Grenze zu benennen ist nicht dasselbe wie sie aufzuheben** — aber es ist die
Entscheidung, die man ohne Auftrag treffen darf.

**Nebenbefund:** Stufe 2 liegt bei jeder Größe über 100 % des Acht-Sekunden-Budgets. Kein
Überziehen, sondern die dokumentierte Strategie — bleiben Lücken, fährt AUTO einen zweiten Lauf.
Zwei volle Budgets sind das Maximum, sechzehn Sekunden also der dokumentierte schlechteste Fall.

## Etappe 14 — abgeschlossen, gemergt, deployt

**`GET /` meldete seit jeher `status: ok` und fasste die Datenbank nie an** — und `render.yaml`
verdrahtete `healthCheckPath` auf genau diese Route. Stirbt die Datenbank, hält Render den Dienst
also für gesund und schickt ihm weiter Anfragen, die samt und sonders mit 500 enden. **Am 07.09.
ist das der wahrscheinlichste Fehler**: `DATABASE_URL` zeigt auf nichts, die Anwendung startet,
alles sieht gut aus.

`/health` liest wirklich, und zwar aus `schema_migrations` — das beantwortet in einem Zug beide
Fragen des Umstellungsblattes: kommt die Datenbank an, und welcher Stand liegt dort. **503 statt
200 mit einem Feld darin**, weil eine Überwachung den Status liest und nicht den Rumpf.

**Der Preis steht dabei:** eine kurz stolpernde Datenbank lässt Render den Dienst als ungesund
führen, und das kann einen Neustart auslösen. Bei einer Datenbank, die nicht antwortet, ist ein
Neustart aber ohnehin nicht das Problem.

Die Wurzel bleibt die Begrüßung der API und behauptet keine Gesundheit mehr. Schritt 4 des
Umstellungsblattes hat damit **eine** Abfrage statt zweier indirekter.

Am lebenden Dienst nachgesehen: `{"database":"ok","migrations":{"applied":17,"latest":
"0017_qualifications"},"status":"ok"}`.

## Etappe 16 — der Durchgang als Nutzer

Keine neue Funktion, sondern ein anderer Blick: das Werkzeug einmal so durchgehen, wie eine
Personalabteilung und wie ein Mitarbeiter es benutzen — nicht wie jemand, der es geschrieben hat.
Ein voller September mit vier Leuten, ein Mitarbeiterkonto von der Einladung bis zum eigenen
Kalender, und an jeder Stelle die Frage: was steht hier, und was müsste stehen?

**Der eine Sicherheitsbefund.** „Passwort zurücksetzen" leerte `users.hash` — und das Bearer-Token,
das mit dem alten Passwort erzeugt worden war, galt weiter, bis zu dreißig Tage. Der Griff, den man
tut, wenn ein Telefon abhanden gekommen ist, tat nachweislich nichts: die alte Sitzung las weiter
den Dienstplan. Am laufenden Dienst nachgestellt, bevor irgendetwas geändert wurde.
`users.token_epoch` (Migration `0018`) schließt es ohne Sitzungstabelle: der Zähler wandert ins
signierte Token, wird bei jeder Anfrage gegen die Spalte verglichen, und ein Zurücksetzen erhöht
ihn. Dasselbe für das Cookie — eine Regel, die nur einen von zwei Anmeldewegen deckt, ist die
Lücke, um die es geht. Ein Token ohne die Angabe zählt als 0, damit das Aufspielen niemanden
abmeldet; erst das nächste Zurücksetzen wirkt.

**Der eine echte Fehler.** Die Grenzen des Datumsfeldes in der Selbstmeldung wurden mit
`toISOString()` auf lokaler Mitternacht gebaut. In Berlin heißt das: `min` steht auf dem letzten
Tag des Vormonats, den der Server ablehnt, und `max` auf dem vorletzten des laufenden — **eine
Krankmeldung für den letzten Tag des Monats war über das Formular nicht möglich.** In UTC
unsichtbar, deshalb setzt der Regressionstest `TZ=Europe/Berlin` selbst, statt dem Runner zu
trauen. `pages/Employees.jsx` hatte das richtige Muster samt Begründung längst danebenstehen.

**Der Rest ist eine Sorte:** das Werkzeug tut das Richtige und sagt nichts darüber.

- Inaktiv gesetzt und trotzdem im Plan — jetzt eine Warnung mit der Anzahl offener Schichten.
- Die gesetzliche Pause wird berechnet, erzwungen, abgezogen — und war nirgends zu sehen. Jetzt im
  Kalender, in der Tabelle, in der CSV und im iCal.
- Die CSV-Kopfzeile war deutsch, während die Wochentage daneben übersetzt waren.
- Der iCal-Kalender hieß „Dienst" statt nach seinem Monat.
- Die Aufbewahrungsfrist lief nur beim Start oder auf Knopfdruck — und der Keepalive-Auftrag hält
  den Dienst wochenlang wach. Jetzt einmal täglich, ausgelöst von der ersten Anfrage.
- Ohne Wochenstunden gilt keine Wochengrenze; im Probelauf kamen 46,5-Stunden-Wochen heraus. Jetzt
  ein Hinweis im Einrichtungsstand.
- Ein Komponentenfehler nahm die ganze Seite (weiße Seite, keine Meldung) — jetzt eine Fehlergrenze
  um die Routen.
- Fehlermeldungen verschwanden nach vier Sekunden, ohne Schließen-Schaltfläche und ohne dass ein
  Screenreader sie je vorgelesen hätte.
- `/qualifications` war für jedes angemeldete Konto lesbar, obwohl keine Mitarbeiteransicht danach
  fragt.

**Und drei Stellen, an denen die Dokumentation nicht mehr stimmte:** das README beschrieb
Kopfzahlen je Wochentag auf der Schichtart (seit `0010` weg), einen Gunicorn-Aufruf mit zwei
Workern (`render.yaml` startet einen) und ein Repository, in dem dieses Projekt neben einem
Ticket-System liegt (tut es nicht).

**Betrieb.** `render.yaml` setzt jetzt `region: frankfurt` für Dienst und Datenbank und deklariert
die `SMTP_*`-Variablen mit `sync: false`, damit Render beim Deploy danach fragt; die App warnt
zusätzlich beim Start, wenn sie in Produktion ohne `SMTP_HOST` läuft. Die Region wirkt nur auf neu
angelegte Ressourcen — **der nächste Datenbankzyklus ist der Moment**, und im Umstellungsblatt
steht das jetzt bei Schritt 1. `health-check.yml` fragt stündlich `/health` ab und **lässt den
Auftrag fehlschlagen**, wenn der Dienst sich nicht gesund meldet; ein fehlgeschlagener Actions-Lauf
schickt GitHub von sich aus als Mail. Der Keepalive-Auftrag pingt weiter alle vierzehn Minuten und
schluckt Fehler weiter — aber `/health` statt der Wurzel.

## Arbeitsweise

Eine Etappe pro Zweig, und jede Etappe in derselben Reihenfolge: erst ein Entwurf unter
`docs/entwuerfe/`, der die Entscheidungen samt Begründung festhält, dann ein Umsetzungsplan
unter `docs/plaene/` mit Aufgaben in Checkbox-Form, dann die Umsetzung Aufgabe für Aufgabe.

**Nach der Umsetzung ein eigener Durchgang mit Abstand.** Nicht die eigene Zusammenfassung
prüfen, sondern den Diff — und dabei ausdrücklich nicht glauben, was der Umsetzungsschritt über
sich selbst behauptet. Die Befunde dieser Durchgänge stehen unten bei den Etappen; die
nützlichsten sind durchweg die, bei denen die Umsetzung „fertig" gemeldet hatte.

**Vor dem Merge selbst prüfen.** Alle vier CI-Jobs grün, besonders `backend-postgres`, der die
lokal übersprungenen Tests fährt. Dann in einem Zug durch: pushen, PR, CI abwarten, mergen,
Branch löschen, Deploy prüfen, Handoff nachziehen. Ein Merge löst einen Deploy aus, der
ausstehende Migrationen auf die Produktionsdatenbank anwendet — das gehört auf die Liste, nicht
in die Hoffnung.

Was hier nicht entschieden wird, steht unter „Offen — liegt beim Betrieb": Zugangsdaten,
Passwortrotation, Entscheidungen über die Datenbankinstanz.

## Fallstricke dieses Projekts — das Wichtigste in Kürze

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
    Etappe 3 legten zwei Aufgaben (4 und 5) denselben Testnamen an; aufgefallen ist es erst bei
    der zweiten, beide sind seitdem eindeutig benannt. `pytest --collect-only` zeigt es.
16. **Jede Tabelle, in die eingefügt wird, braucht eine `id`-Spalte.** `_PostgresCursor.execute()`
    hängt an jedes `INSERT` ohne eigenes `RETURNING` ein `RETURNING id` an, damit `lastrowid`
    auch dort funktioniert. Eine Tabelle ohne `id` ist auf Postgres nicht beschreibbar — auf
    SQLite dagegen schon, weshalb es lokal nicht auffällt. Die erste Fassung von
    `0011_settings` hatte `name` als natürlichen Primärschlüssel und keine `id`; gekostet hat
    das einen roten `backend-postgres`-Job. Ein Schreibtest in `test_migrations_postgres.py`
    hält es jetzt fest.
17. **Ein Modulname im Backend darf kein installiertes Paket verdecken.** `backend/coverage.py`
    hätte das PyPI-Paket `coverage` (Abhängigkeit von `pytest-cov`) verdeckt, sobald jemand das
    ergänzt — auch wenn `coverage` zum Entscheidungszeitpunkt nicht installiert war. Deshalb
    heißt die Datei `coverage_model.py`.

18. **Eine gelöschte Person ist noch da — als Grabstein.** Seit 5i löscht
    `DELETE /employees/<id>` die Zeile nicht, sondern anonymisiert sie (`anonymized_at` gesetzt,
    `active` auf 0). Jede neue Abfrage, die Mitarbeiter *auflistet* oder *zählt*, muss
    `anonymized_at IS NULL` mitführen — sonst tauchen Grabsteine als Personal auf, im
    Auswahlfeld, in Statistiken, im Generator. Wer über `shift_assignments` joint, will das
    Gegenteil: dort gehört der Grabstein dazu, sonst sieht die Vergangenheit unbesetzt aus.

19. **Ein Datum wird geprüft *und* normalisiert, nie nur geprüft.** `date.fromisoformat()`
    akzeptiert seit Python 3.11 auch `'20260901'`. Wer damit nur prüft und die Eingabe roh
    speichert, legt eine Zeile an, die jeden Vergleich verliert — das Tool vergleicht Daten
    durchgehend als Zeichenketten, und `'2026-09-15' < '20260901'`. Dafür gibt es
    `parse_iso_date()`; jede neue Route, die ein Datum entgegennimmt, benutzt ihn.

20. **`int()` und `float()` nehmen Wahrheitswerte an.** `int(True)` ist `1`, `float(True)` ist
    `1.0`, `int(3.9)` ist `3`. Alle drei ergeben eine gültig aussehende Zeile für etwas, das
    niemand genannt hat, und keine Prüfung dahinter schlägt an. `parse_weekday()`,
    `parse_int_list()` und `parse_optional_hours()` lehnen das ab — **neue Eingabefelder gehen
    durch einen dieser Parser, nicht durch ein nacktes `int()`.**

21. **Ein grüner `backend-postgres`-Job beweist nicht, dass die Postgres-Tests gelaufen sind.**
    Sie überspringen sich selbst, wenn `TEST_DATABASE_URL` fehlt, und ein Lauf aus lauter
    übersprungenen Tests meldet Erfolg. Wer etwas anfasst, dessen Nachweis dort liegt — die
    Dialektschicht, die Migrationen, die beiden Advisory-Locks —, sieht im Joblog nach, dass die
    betreffenden Tests wirklich `PASSED` melden. Bei PR #27 waren es 474 passed, 0 skipped.

22. **Wer eine bestehende Datenstruktur neu ausliest, muss die Ebenen mitlesen, die ihre
    vorhandenen Leser schon kennen.** Die Zeiten einer Zuweisung stehen an drei Stellen — in der
    Zeile selbst, in `shift_time_overrides`, in der Schichtart —, und `assignment_hours()` löst
    das auf. Zwei Spalten zu nehmen, wo eine Funktion drei Ebenen auflöst, ist kein Abkürzen,
    sondern ein anderes Datenmodell. Dasselbe gilt für die Pause
    (`effective_break_minutes`/`legal_break_minutes`).

23. **Was ein Mitarbeiter sieht, entscheidet, was er bedienen kann.** Seit 5f liefert
    `GET /schedules/<j>/<m>` einem Mitarbeiterkonto ausschließlich dessen eigene Schichten. Jedes
    neue Merkmal, das einen Mitarbeiter etwas *auswählen* lässt, muss daran zuerst gemessen
    werden — in Etappe 8 war der ganze Entwurf einmal fertig, bevor auffiel, dass sein Hauptnutzer
    die zweite Hälfte der Auswahl gar nicht sehen kann. Die Antwort ist nicht, ihm mehr zu zeigen.

24. **Was zum Platz gehört, reist ganz mit — und „ganz" heißt jedes Feld.** Eine Zuweisung trägt
    Zeiten, `break_minutes` *und* `break_start`; alle drei gehören dem Platz, nicht der Person.
    Wer sie weiterreicht und eines auslässt, rechnet stillschweigend falsch: ohne die Dauer mit
    der gesetzlichen Mindestpause statt der vereinbarten, ohne die Lage gar nicht nach § 4 Satz 3.
    **Das ist zweimal hintereinander passiert** (Etappe 8 und 9, beide Male im Review gefunden),
    einmal je Feld. Wer `constraint_findings()` aus einem neuen Pfad aufruft, geht die
    Parameterliste durch, statt sich zu erinnern.

25. **Die Löschliste in `delete_employee()` ist der Ort, an dem das Vergessen steht.** Wer eine
    Tabelle anlegt, die etwas über eine Person sagt, trägt sie dort ein — sonst überlebt die Angabe
    die Anonymisierung. In Etappe 10 sind es die Nachweise gewesen, gefunden im Review; die Liste
    wächst nicht von selbst mit.

26. **Eine neue Tabelle folgt dem Muster der bestehenden, auch wo es unnötig aussieht.** Jede
    Verknüpfungstabelle in diesem Schema trägt eine eigene `id` und sagt die Eindeutigkeit mit
    `UNIQUE` — nicht aus Gewohnheit, sondern weil die Dialektschicht jedem `INSERT` ein
    `RETURNING id` anhängt (Fallstrick 16). Ein zusammengesetzter Primärschlüssel ist die sauberere
    Modellierung und auf Postgres ein Laufzeitfehler.

27. **Ein Riegel, den 87 Tests umwerfen, ist der falsche Riegel.** Wenn eine neue Prüfung breit
    Bestand bricht, sagt die Suite meistens nicht „die Tests sind veraltet", sondern „das verbotene
    Verhalten wird gebraucht". In Etappe 11 war es das Anlegen eines leeren Plans zum
    Von-Hand-Füllen. Erst fragen, was die Tests *benutzen*, dann entscheiden, ob es ein Hinweis
    oder ein Verbot wird.

28. **Ein „erst wenn der Benchmark es zeigt" ist eine Aufgabe, keine Ablage.** Zwei
    Leistungsbefunde standen zwölf Etappen lang mit dieser Notiz da, ohne dass jemand gemessen
    hätte. Das Messen hat sie an einem Nachmittag erledigt — und dabei eine Grenze gefunden, die
    niemand gesucht hat. **Wer eine Frage vertagt, notiert auch, wie man sie beantwortet.**

29. **Eine Zusage, die nichts prüft, ist schlimmer als keine.** `GET /` sagte `status: ok`, ohne
    die Datenbank anzufassen — und die Überwachung hing daran. Wer ein Feld `status` einführt,
    schuldet die Prüfung dahinter; wer sie nicht leisten will, nennt das Feld anders. Dasselbe
    Muster wie beim leeren Plan in Etappe 11: Erfolg melden und nichts tun.

## Offen — liegt beim Betrieb

**Erledigt am 22.08.2026:** Etappe 2 und 3 gemergt und deployt (PR #13, #14), alle Migrationen
`0001`–`0007` in Produktion angewandt, der Nachtschicht-Fehler in `window_contains_shift()`
behoben und gemergt (PR #15), und ein vollständiges Backup gezogen und geprüft. Was hier steht,
ist der verbliebene Rest.

### Der Datenbankzyklus — alle 30 Tage, erster Durchlauf 07.09.2026

**Am 23.08.2026 entschieden: die Instanz ablaufen lassen und eine neue
30-Tage-Instanz aufziehen.** Kein bezahlter Plan. Damit ist es kein Termin, sondern ein
wiederkehrender Vorgang.

**Das Blatt dafür ist [`DATENBANKWECHSEL.md`](DATENBANKWECHSEL.md)** — dort steht der Durchlauf,
nicht hier. Was man wissen muss:

- **Die Reihenfolge trägt.** Neue Instanz anlegen, *solange die alte läuft*; Schreiben beenden,
  dann sichern; **zurückspielen, bevor** `DATABASE_URL` umgebogen wird. Wer erst deployt und
  danach zurückspielt, läuft eine Weile gegen eine leere Datenbank — und `pg_restore --clean`
  wischt weg, was in der Zwischenzeit dort angelegt wurde.
- **§ 16 Abs. 2 ArbZG steht dem Zyklus entgegen**, wenn nicht jeder Durchlauf gesichert und
  zurückgespielt wird. Siehe oben unter „Wo es gerade steht".
- **`pg_dump`/`pg_restore` sind nicht im PATH** — das stand weiter unten schon, und trotzdem
  riefen `DATENBANKWECHSEL.md` und das README sie bloß beim Namen auf. Eine Tatsache zu
  notieren und sie in derselben Anleitung zu missachten ist das eigentliche Versäumnis; der
  volle Pfad steht jetzt an beiden Stellen.
- Auf einer leeren neuen Datenbank laufen alle Migrationen beim Modulimport von selbst durch.
  `0007_derive_coverage` findet dort nichts zum Ableiten und tut nichts — der Wächter in der
  Migration, kein Fehler.
- **Die Region wird hier entschieden und nur hier.** `render.yaml` steht seit Etappe 16 auf
  `region: frankfurt` für Dienst und Datenbank, aber Render legt die Region beim Anlegen fest und
  ändert sie nicht nachträglich. Läuft die bisherige Instanz in einer US-Region, ist dieser
  Durchlauf die Gelegenheit. Verarbeitet werden Namen, Arbeitszeiten und Krankmeldungen; letztere
  sind Gesundheitsdaten nach Art. 9 DSGVO, und eine US-Region macht daraus eine
  Drittlandübermittlung nach Kapitel V. Der Auftragsverarbeitungsvertrag nach Art. 28 mit Render
  wird davon unabhängig gebraucht.

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

- **Datenbankpasswort wurde in einem Chatverlauf offengelegt.** Mit der Entscheidung, die
  Instanz ablaufen zu lassen, erledigt sich das für diese Datenbank von selbst: das Passwort
  verschwindet am 07.09. mit ihr. Zwei Dinge bleiben und liegen beim Nutzer: die **neue**
  Datenbank bekommt ein neues Passwort, nicht dasselbe wieder — und falls dasselbe Passwort
  noch anderswo benutzt wird, gilt es dort weiter als offengelegt. Das lässt sich nur vor Ort
  prüfen.
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

- ~~`ci.yml` Cache-Schlüssel deckt nur `requirements-dev.txt` ab~~ — **erledigt in 6c**
- ~~`ortools` in `requirements-dev.txt` ungepinnt~~ — **erledigt in 6c**
- ~~`password_not_set_yet`-Zweig in `login()` zählt keine Versuche~~ — **erledigt in 6b**
- ~~Drosselungstests verdrahten `10/9/11` fest~~ — **erledigt in 6b**
- ~~`is_locked_out`/`record_attempt` sind check-then-act ohne Zeilensperre~~ — **erledigt in 6b**, über einen Advisory-Lock je Benutzername statt einer Zeilensperre
- `HTTPException`-Fallback liefert für andere Codes als 404/405 einen unübersetzten Literal (aktuell unerreichbar)
- ~~`handleMonthChange` setzt den geladenen Plan nicht zurück~~ — **war bereits behoben**, in Etappe 6a nachgeprüft
- `fetchSchedule()` schluckt jeden GET-Fehler zu `null`
- `MIGRATIONS_DIR.iterdir()` wirft, wenn das Verzeichnis fehlt
- ~~Zwei Validierungstests in `test_api_availability.py` prüfen nur den Status~~ — **erledigt in 6c**
- ~~Frontend hat keinerlei Testinfrastruktur~~ — **erledigt in Etappe 3** (Aufgabe 8, Vitest +
  Testing Library, siehe dort)

Neu aus dem Abschluss-Review von Etappe 1:

- ~~`unavailable_dates` hat denselben Normalisierungsfehler wie `valid_from`/`valid_until`~~ —
  **erledigt in Etappe 6a**, und der Befund war breiter als hier notiert: dieselbe Stelle stand
  sechsmal im Code, nicht einmal
- keine CHECK-Constraints auf `employee_availability` (`weekday`, `start_time`, `end_time`);
  konsistent mit den anderen Tabellen, die API ist der einzige Schreiber. Wieder aufgreifen,
  sobald ein zweiter Schreibpfad entsteht (Import/Seed in Etappe 5)
- ~~keine Eindeutigkeit auf `employee_availability`~~ — **erledigt in 6c**, aber nur für exakte
  Duplikate. Überlappungen bleiben absichtlich erlaubt: sie zusammenzufassen hieße, eine Eingabe
  stillschweigend umzuschreiben, und zwei Fenster an einem Tag sind der geteilte Dienst
- ~~die Fenster-Abzeichen in der Mitarbeiterliste filtern nicht nach `valid_from`/`valid_until`~~
  — **erledigt in Etappe 6a**. Abgelaufene Fenster bekommen einen eigenen Hinweis statt der
  Meldung für „gar keine Fenster": der Unterschied entscheidet, ob jemand ein Fenster anlegen
  oder eine Grenze ändern muss
- ~~die Fensterprüfung rechnet im innersten Schleifenkörper von `eligible_candidates()` alle
  `"HH:MM"`-Strings neu~~ — **gemessen in Etappe 13 mit halber Belegschaft im Fenster-Modus:
  zeigt sich nicht.** Der Engpass ist die Rekursionstiefe, nicht die Rechnung
- ~~der `Project Structure`-Block im README ist im Rückstand~~ — **erledigt in 6b**. `security.py`
  und `timeutil.py` standen entgegen der Notiz längst drin; nachgetragen wurden die neuen
  Testdateien und die Migrationsspanne
- ~~Spec §6 sah eine eigene Route `GET/PUT /employees/<id>/availability` vor~~ — **erledigt in
  Etappe 4** (Vorarbeit 1). Lesen darf man sich selbst, schreiben bleibt HR

Neu aus den Reviews von Etappe 2:

- ~~ungenutzte Konstante `ASSIGNMENT_TIMES_PY_PATH`~~ — **war bereits benutzt**, in 6c nachgeprüft
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
- ~~die `end_time`-Hälfte der Zeitformat-Prüfung ist ungetestet~~ — **war bereits getestet**, in 6c nachgeprüft
- die Validierungsreihenfolge in `add_slot()` prüft Zeiten vor dem Datum
- die Regel „Block ohne Vorlage braucht Zeiten" steht an zwei Stellen (`add_slot()` und
  `update_assignment()`)
- ~~`set_shift_times()` hat dieselbe Gleichheitslücke wie `parse_assignment_times()`~~ —
  **erledigt in 6c**, indem die Route denselben Parser benutzt statt einer zweiten Prüfung
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

- ~~der Rundlauftest von `0006_coverage.py` prüft nur `business_hours`~~ — **erledigt in 6c**;
  alle drei Tabellen werden nach dem Rollback geprüft
- ein Docstring in `test_migrations_postgres.py` spricht von Einzelindex-Zugriff, der Test
  vergleicht aber ganze Tupel
- für `0007_derive_coverage.py` gibt es nur einen Postgres-Test (die Ableitung selbst), keine
  Postgres-Gegenprobe für den Leer-Bestand-Wächter oder den Rundlauf
- ~~`int(entry.get('weekday'))` schluckt `True`/`False` als `1`/`0` und kürzt `3.9` zu `3`~~ —
  **erledigt in Etappe 6a**, an fünf Stellen statt der hier genannten zwei
- die Datumsprüfung beim Anlegen einer `business_hours_exceptions`-Zeile
  (`create_business_hours_exception()`) ist check-then-act ohne Sperre
- kein eigener HTTP-Test für den Abwesenheitsfall bei den Deckungslücken (code-seitig korrekt,
  über denselben `employee_id IS NULL`-Filter wie ein unbesetzter Platz)
- ~~der Entfernen-Button im Bedarfseditor hat nur `title`, kein `aria-label`~~ — **erledigt in
  6c**; der Test findet ihn jetzt über `getByRole`, denselben Weg wie jemand, der ihn nicht sieht
- die Datumsformatierung steht jetzt in dritter Kopie im Frontend — folgt aber bereits
  etablierter Projektkonvention, keine neu eingeführte Dublette

Neu aus Etappe 4:

- ~~`plan_day()` läuft die probeweise Tagesbesetzung nach jedem Zuschnitt neu~~ — **gemessen in
  Etappe 13: zeigt sich nicht.** 1,36 Sekunden bei 2480 Blöcken, und dort greift längst die
  Rekursionsgrenze
- der Zuschnitt greift nur bei Mitarbeitern im `windows`-Modus. Jemand mit
  `availability_mode = 'anytime'`, dem nur die Tagesgrenze im Weg steht, bekommt kein gekürztes
  Stück angeboten — denkbar, aber nicht das, was die Spec unter Zuschnitt versteht
- `day_envelope()` gibt es zweimal: einmal in `scheduler._search()` über den Suchzustand,
  einmal als `app.day_envelope_from_hours()` über gespeicherte Zeilen. Die gemeinsame Rechnung
  steckt in `shift_datetimes()` und wird importiert, die Hülle ist doppelt
- ~~`MAX_BLOCK_MINUTES` ist als 600 fest verdrahtet, obwohl `max_daily_hours` einstellbar ist~~
  — **erledigt in Etappe 6a, in der anderen Richtung**: § 3 ArbZG erlaubt höchstens zehn
  Stunden, also wurde das Feld gedeckelt statt der Block gelockert
- ~~die Bedarfszahlen der Schichtart werden vom Frontend weiterhin mitgeschickt~~ —
  **erledigt in Etappe 5e** mit dem Entfernen von `shift_requirements`
- für `0008_max_daily_hours` gibt es zwei Postgres-Tests, die lokal übersprungen werden; sie
  sind bislang nur im CI gelaufen — **beim Abschluss-Review prüfen, dass `backend-postgres`
  wirklich grün war**

## Roadmap

Design: [`docs/entwuerfe/2026-08-16-zeitachsen-dienstplan-design.md`](entwuerfe/2026-08-16-zeitachsen-dienstplan-design.md)

- ~~**Etappe 4** — Zuschnitt im Planer~~ — **umgesetzt**, siehe oben. Der Planer baut aus
  `coverage_requirements`, schneidet auf die Arbeitszeitfenster zu und kann den geteilten
  Dienst. `shift_requirements` wird nicht mehr gelesen und in Etappe 5 entfernt. Damit geht das
  Tool über Papershift und Deputy hinaus — dort wird nicht automatisch zugeschnitten.
- **Etappe 5** — vollständig. Kein Vorhaben, sondern ein Bündel aus neun unabhängigen Teilen,
  jeder mit eigener Spec: das Arbeitszeitrecht (5a Ruhezeiten und Pausen, 5b Sonn- und
  Feiertage, 5c Achtstundenschnitt, 5d Feiertagskalender), `shift_requirements` entfernen (5e),
  Veröffentlichen-Workflow (5f), Änderungsprotokoll (5g), Exporte (5h), DSGVO (5i)
