# Design: Etappe 4 — Zuschnitt im Planer

**Datum:** 2026-08-22
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §5, §10
**Status:** Entwurf, mit dem Nutzer abgestimmt

---

## 1. Ziel

Der Planer baut seine Plätze bis heute aus `shift_requirements` — „montags braucht die
Frühschicht 3 Leute". Etappe 3 hat daneben ein zweites, feineres Bedarfsmodell aufgebaut
(`coverage_requirements`: Bedarfsbänder über den Tagesverlauf, absolute Besetzungsstärke),
das der Generator bisher nicht kennt.

Etappe 4 stellt den Planer auf dieses Modell um und ergänzt das Alleinstellungsmerkmal des
Vorhabens: **den automatischen Zuschnitt.** Kann ein Block von niemandem ganz abgedeckt
werden, wird er auf das Arbeitszeitfenster eines Mitarbeiters gekürzt, statt die Person zu
verwerfen. Der ungedeckte Rest bleibt als benannte Lücke stehen.

Dazu kommt — auf ausdrücklichen Wunsch des Nutzers und über den ursprünglichen Zuschnitt der
Etappe hinaus — der **geteilte Dienst**: eine Person darf mehrere Blöcke am selben Tag
arbeiten, begrenzt durch eine tägliche Höchstarbeitszeit und die Ruhezeit zum Nachbartag.
Damit rückt ein Teil des Arbeitszeitrechts aus Etappe 5 nach vorn.

## 2. Ausgangslage

### Was steht

- `coverage_requirements` wird über die API gepflegt, ist überlappungsfrei validiert und
  gegen die Öffnungszeiten geprüft (Etappe 3).
- `coverage_model.py` enthält die vollständige Ereignispunkt-Maschinerie: `coverage_curve()`,
  `band_within()`, `trim_band_to_hours()`, `coverage_gaps()` — reine Rechenlogik, ringfest
  über Mitternacht.
- `shift_assignments` trägt seit Etappe 2 eigene `start_time`/`end_time` und ein nullbares
  `shift_type_id`. Der Handkorrektur-Pfad nutzt das bereits.
- `employee_availability` und `availability_mode` existieren seit Etappe 1; der Suchkern
  filtert über `structurally_eligible()` bereits gegen Fenster.
- `min_rest_hours` steht im Bestand standardmäßig auf 11 — das ist § 5 Abs. 1 ArbZG, bisher
  ohne dass es jemand so benannt hätte.

### Was fehlt

- `build_slots()` (`backend/scheduler.py`) liest ausschließlich `shift_type['requirements']`.
  Zeiten kommen starr von der Schichtart.
- Der Generator schreibt **keine** Zeiten in `shift_assignments`; die Spalten aus Etappe 2
  bleiben auf dem Erzeugen-Pfad leer.
- Eine Person kann höchstens einen Block pro Tag bekommen (`day_usage`).
- Es gibt keine tägliche Höchstarbeitszeit.

### Zwei Landminen im Bestand

Beide schlafen heute und gehen hoch, sobald der Generator vorlagenlose Blöcke mit Zeiten
erzeugt:

1. `backend/scheduler.py`, Ergebnisaufbau in `_search()`:
   `assignments.sort(key=lambda a: (a['date'], a['shift_type_id'], a['slot_index']))` wirft
   einen `TypeError`, sobald ein `shift_type_id` `None` ist.
2. `backend/app.py`, `generate_schedule_route()`: der INSERT listet
   `(schedule_id, date, shift_type_id, slot_index, employee_id)` und keine Zeiten.

## 3. Rechtlicher Rahmen

Recherchiert am 22.08.2026 am Gesetzestext, nicht aus dem Gedächtnis.

| Norm | Inhalt | Folge |
|---|---|---|
| [§ 2 Abs. 1](https://www.gesetze-im-internet.de/arbzg/__2.html) | Arbeitszeit ist die Zeit vom Beginn bis zum Ende der Arbeit **ohne die Ruhepausen** | Bei geteiltem Dienst zählt die Unterbrechung nicht mit. Die Tagesarbeitszeit ist die **Summe der Blockdauern**, nicht die Spanne vom ersten Beginn bis zum letzten Ende |
| [§ 3](https://www.gesetze-im-internet.de/arbzg/__3.html) | max. 8 h werktäglich; auf 10 h verlängerbar **nur**, wenn im Durchschnitt über sechs Kalendermonate oder 24 Wochen 8 h nicht überschritten werden | Die 10 h sind keine freistehende Grenze, sondern an einen Ausgleich gebunden |
| [§ 4](https://www.gesetze-im-internet.de/arbzg/__4.html) | 30 Min Pause bei mehr als 6 bis 9 h, 45 Min bei mehr als 9 h; teilbar in Abschnitte von je mind. 15 Min; nie länger als 6 h am Stück ohne Pause | Das Tool kennt keine Pausen |
| [§ 5 Abs. 1](https://www.gesetze-im-internet.de/arbzg/__5.html) | nach **Beendigung der täglichen Arbeitszeit** ununterbrochen mind. 11 h Ruhezeit. Abs. 2 lässt in Gaststätten, Krankenhäusern und Verkehrsbetrieben 10 h zu, wenn eine andere Ruhezeit binnen Kalendermonat oder vier Wochen auf 12 h verlängert wird | Die Unterbrechung eines geteilten Dienstes ist **keine** Ruhezeit. Maßgeblich ist das Ende des letzten Blocks an Tag D gegen den Beginn des ersten Blocks an Tag D+1 |
| [§ 11](https://www.gesetze-im-internet.de/arbzg/__11.html) | mind. 15 beschäftigungsfreie Sonntage im Jahr, Ersatzruhetag binnen zwei Wochen | Bleibt Etappe 5 |

### Was diese Etappe davon umsetzt

1. **Geteilter Dienst** — mehrere Blöcke am selben Tag, die sich nicht überschneiden dürfen.
2. **Tägliche Höchstarbeitszeit** — über die Summe der Blockdauern, neues Feld
   `employees.max_daily_hours`, Standard 10 (§ 3 Satz 2).
3. **Ruhezeit über die Tagesgrenze** — letzter Block an D gegen ersten Block an D+1, über das
   bestehende `min_rest_hours` (§ 5 Abs. 1).

### Was sie bewusst nicht umsetzt

Nicht als stille Lücke, sondern schriftlich und in der Oberfläche benannt:

- **Der 8-h-Durchschnitt aus § 3 Satz 2.** Der Planer plant monatsweise; ein Fenster von sechs
  Kalendermonaten oder 24 Wochen kann er strukturell nicht prüfen — dieselbe Grenze, an der
  schon `max_shifts_per_month` und die Ruhezeitprüfung am Monatsrand enden. Eine 10-h-Grenze
  ohne Ausgleichsnachweis ist rechtlich **nicht selbsttragend**. Die Oberfläche weist am Feld
  `max_daily_hours` darauf hin; die Verantwortung für den Ausgleich bleibt bei HR.
- **§ 4 Ruhepausen.** Das Tool kennt keine Pausen. Ein durchgehender 8-h-Block verletzt § 4
  Satz 3 (mehr als 6 h am Stück ohne Pause) — das gilt schon heute, Etappe 4 verschlechtert
  nichts. Bemerkenswert in die andere Richtung: eine Unterbrechung von mindestens 30 Minuten
  zwischen zwei Blöcken **erfüllt** § 4 der Form nach. Der geteilte Dienst ist damit
  arbeitszeitrechtlich sauberer als der durchgehende Block, den das Tool heute erzeugt.
- **§ 11 Sonn- und Feiertagsruhe** und die daraus folgende Regel „höchstens sechs Tage in
  Folge". Bleibt Etappe 5, wie in der Roadmap vorgesehen.

## 4. Entschiedene Fragen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Umstieg auf `coverage_requirements` | **Hart**, mit Benchmark-Gegenprobe | `build_slots()` baut nur noch aus Bändern. Der alte Pfad lebt als Vergleichsbasis in `benchmark.py` und in den 23 Bestandstests weiter, nicht in Produktion. Ein Laufzeit-Umschalter hieße doppelte Testmatrix und einen Schalter, den danach niemand entfernt |
| Wann wird zugeschnitten | **Probeweise Tagesbesetzung** | Ein statischer Test („kann irgendwer diesen Block ganz abdecken?") kennt keine Konkurrenz: bei drei Plätzen 06:00–14:00, zwei „immer verfügbaren" Personen und einer mit Fenster 08:00–14:00 sagt er „abdeckbar" und lässt den dritten Platz unbesetzt, obwohl ein Zuschnitt ihn gerettet hätte |
| Alte Bedarfszahlen im Schichtart-Editor | **Aus dem Editor nehmen** | Ein Formular, das Eingaben annimmt und verwirft, ist genau Fallstrick 12 des Handoffs. Tabelle und Spalten bleiben bis Etappe 5 unangetastet, nur der Schreibpfad im Frontend fällt weg |
| Mehrere Blöcke pro Person und Tag | **Erlaubt**, mit Tagesgrenze und Ruhezeit | Siehe §3. Löst das Spec-Beispiel „geteilter Dienst 08:00–12:00 und 16:00–20:00" aus §4.4 der übergeordneten Spec ein, das bisher niemand arbeiten konnte |

## 5. Stufe 1 — Blockplanung

Neues Modul `backend/block_planner.py`. Reine Rechenlogik ohne Datenbank und ohne Flask, nach
dem Vorbild von `coverage_model.py`; die Minutenachse und die Mitternachtsregel werden von
dort und aus `scheduler.py` importiert, nicht zweitgefasst.

Der Name folgt Fallstrick 16: `planner.py` wäre harmlos, aber `block_planner.py` ist
eindeutig und verdeckt kein installiertes Paket.

### 5.1 Eingabe und Ausgabe

**Eingabe je Datum:**

- die Bedarfsbänder des Wochentags, jedes über `trim_band_to_hours()` auf die **effektive**
  Öffnungszeit dieses Datums zugeschnitten (Ausnahme schlägt Wochentag — die Logik steht in
  `app.py` und wird wiederverwendet, nicht kopiert). Ein geschlossener Tag liefert keine Bänder
- die Vorlagen (`shift_types` mit `start_time`/`end_time`). **`requirements` wird nicht mehr
  gelesen**
- je aktivem Mitarbeiter die für dieses Datum gültigen Fenster (Wochentag,
  `valid_from`/`valid_until`), sowie `unavailable_weekdays`, `unavailable_dates`,
  Abwesenheiten und `allowed_shift_types`. Ein Mitarbeiter mit `availability_mode = 'anytime'`
  gilt als ganztägig verfügbar

**Ausgabe:** eine Liste von Blöcken, strukturgleich zu dem, was `build_slots()` heute liefert:

```
{date, weekday, week_start, shift_type_id (int oder None), slot_index,
 is_weekend, start_time, end_time, duration_minutes}
```

Stufe 1 ordnet **keine Personen zu**. Sie beantwortet nur: welche Blöcke muss dieser Tag haben?

### 5.2 Verfahren

**Phase A — mit Vorlagen decken.**
Für jede Vorlage `v`, die in die Öffnungszeit passt, sei `n_v` das Minimum des Restbedarfs
über alle Minuten von `v`. Die Vorlage mit dem größten `n_v × Dauer` wird zuerst gewählt,
`n_v` Blöcke ihrer Form erzeugt und vom Restbedarf abgezogen; wiederholt, bis keine Vorlage
mehr etwas beiträgt. Bei Gleichstand entscheidet die Vorlagen-ID, damit das Ergebnis
deterministisch ist.

*Warum das die Rückwärtskompatibilität beweist:* Migration `0007` hat die Bänder aus genau
diesen Vorlagen abgeleitet. Auf unverändertem Bestand ist `n_v` deshalb identisch mit dem
alten `required_count`, und Phase A erzeugt exakt die Blöcke, die `build_slots()` heute
erzeugt — Phase B und C haben nichts mehr zu tun. Das ist die Messlatte für den Benchmark.

**Phase B — Restbedarf zu Blöcken.**
Was Phase A nicht deckt, wird zu Blöcken: der früheste Zeitpunkt mit Restbedarf, von dort der
maximale zusammenhängende Bereich mit Restbedarf, das ergibt einen Block. Abziehen,
wiederholen. Diese Blöcke tragen `shift_type_id = None`, außer eine Vorlage trifft ihre Zeiten
exakt — dann bekommen sie deren ID und damit Name und Farbe.

**Phase C — probeweise Tagesbesetzung und Zuschnitt.**
Jetzt liegt eine Blockliste vor. Sie wird probeweise besetzt, um zu erkennen, welche Blöcke
niemand arbeiten kann:

1. Je Block die Menge der Mitarbeiter bestimmen, die ihn **ganz** abdecken können (Fenster,
   `unavailable_*`, Abwesenheit, `allowed_shift_types`).
2. Blöcke nach der Größe dieser Menge aufsteigend durchgehen — die klassische
   Minimum-Remaining-Values-Heuristik, die `order_slots()` im Suchkern schon nutzt. Jeweils
   die Person mit den wenigsten verbleibenden Alternativen zuweisen, sofern die Zuweisung
   überschneidungsfrei ist und `max_daily_hours` einhält.
3. Jeder Block, der dabei unbesetzt bleibt, ist Zuschnittkandidat: über alle an diesem Tag
   noch nicht ausgelasteten Mitarbeiter den größten Schnitt aus Block und Fenster bilden, an
   Kandidatengrenzen ausgerichtet. Der größte Schnitt gewinnt; bei Gleichstand die kleinere
   Mitarbeiter-ID.
4. Der Block wird auf diesen Schnitt gekürzt. Der ungedeckte Rest geht als eigener Block
   zurück in die Warteschlange und durchläuft Phase C erneut.

Die gefundene Zuordnung wird anschließend **verworfen**. Sie hat nur die Blockformen bestimmt;
wer die Blöcke tatsächlich arbeitet, entscheidet Stufe 2 monatsweit und fair.

**Phase D — Mindestblocklänge.**
Ein Zuschnitt unter `MIN_BLOCK_MINUTES` wird nicht erzeugt — sonst entstehen
30-Minuten-Schnipsel, die niemand arbeiten will. Bleibt dadurch Bedarf offen, ist das eine
reguläre Deckungslücke, keine Fehlermeldung.

### 5.3 Kandidatengrenzen

Alle Bandgrenzen, Vorlagenzeiten, Öffnungszeiten und Fenstergrenzen der Mitarbeiter dieses
Tages, auf der Minutenachse mit der Mitternachtsregel aus `scheduler._time_range_minutes()`.
Kein 15-Minuten-Raster: das Ereignispunkt-Verfahren hält die Kombinatorik klein und ist im
Projekt bereits an drei Stellen etabliert (`coverage_curve()`, `coverage_gaps()`,
`first_overlapping_pair()`).

### 5.4 Schranken

Phase C ist eine Schleife, die Blöcke erzeugt. Sie braucht eine eigene, deutlich kleinere
Schranke als die Suche, damit sie deren 8-Sekunden-Budget nicht auffrisst: eine
Iterationsobergrenze proportional zur Anzahl der Ausgangsblöcke. Wird sie erreicht, liefert
Stufe 1 die bis dahin erzeugte Blockliste zurück; der Rest erscheint als Deckungslücke. Kein
Abbruch mit Fehler — dasselbe „meldet Lücken, statt zu scheitern"-Verhalten wie überall sonst
im Planer.

### 5.5 `MIN_BLOCK_MINUTES`

Modulkonstante in `block_planner.py`, Standard 180, überschreibbar als Parameter von
`generate_schedule()`. **Keine API- und keine Oberflächenfläche in dieser Etappe** — die
übergeordnete Spec sagt „konfigurierbar", und ein Funktionsparameter ist konfigurierbar. Ein
Request-Feld nach dem Muster von `weekend_weight` ist jederzeit nachrüstbar, sobald jemand es
tatsächlich verstellen will; vorher wäre es Fläche ohne Nutzer (YAGNI).

## 6. Stufe 2 — die Eingriffe in den Suchkern

Der Backtracking-Kern wurde in vier Etappen nicht angefasst. Der geteilte Dienst zwingt uns
erstmals hinein. Drei eng umrissene Stellen, alle in `_search()`:

1. **`day_usage`** ist heute `date → set(employee_id)` und beantwortet „arbeitet schon heute".
   Es wird zu `(employee_id, date) → Liste belegter Zeitintervalle`. Geprüft wird
   **Überschneidung** statt Anwesenheit, über dieselbe Ring-Primitive `_ranges_overlap()`,
   die `coverage_model.py` schon benutzt.
2. **`day_shift`** hält heute genau eine Schicht je `(employee_id, date)`. Es wird eine Liste.
   `rest_period_ok()` vergleicht das **späteste Ende** des Vortags gegen den **frühesten
   Beginn** des aktuellen Tages, und das späteste **Ende** des aktuellen Tages gegen den
   frühesten Beginn des Folgetags — die Ruhezeit nach § 5 misst zwischen Arbeitstagen, nicht
   zwischen Blöcken desselben Tages.
3. **Neu: `day_minutes`** — `(employee_id, date) → zugewiesene Minuten`. Ein Kandidat fällt
   weg, wenn `day_minutes + Blockdauer > max_daily_hours × 60`. Aufgebaut wie die bestehende
   `week_minutes`-Prüfung, damit der Rücknahme-Pfad beim Backtracking dasselbe Muster hat.
   Gelesen wird über `emp.get('max_daily_hours')`: die Spalte ist zwar `NOT NULL`, aber
   Aufrufer, die den Schlüssel gar nicht mitgeben — alle Bestandstests —, bekommen wie bei
   `weekly_hours` keine Prüfung statt eines `KeyError`.

Fairness-Ziel, Branch-and-Bound, lexikografische Ordnung und Notbremse bleiben unverändert.

**Rückwärtskompatibilität:** alle drei Prüfungen hängen an *bekannten* Zeiten, genau wie die
bestehende Ruhezeitprüfung. Die 23 Tests in `test_scheduler.py` liefern keine Zeiten und
greifen deshalb in keine von ihnen — Fallstrick 6 des Handoffs bleibt gewahrt. Sie sind die
Rückwärtskompatibilitätsgarantie; werden sie rot, ist die Änderung falsch.

## 7. Datenmodell

Ein einziger Schemaeingriff.

**Migration `0008_max_daily_hours`:**

```
employees + max_daily_hours REAL NOT NULL DEFAULT 10
```

`NOT NULL` mit Standard, nicht nullbar wie `weekly_hours`. `0001_baseline.py` begründet
dieselbe Entscheidung für `min_rest_hours` ausdrücklich: anders als eine Zielvorgabe zur
Wochenarbeitszeit ist das eine sicherheitsrelevante Einstellung, die nie unbesetzt sein soll.
Für eine Grenze, die aus § 3 ArbZG kommt, gilt das erst recht — „keine Tagesgrenze" darf
nicht die stille Voreinstellung eines vergessenen Feldes sein. Bestandszeilen bekommen 10.

Als **`.py`-Migration mit `table_columns()`-Wächter** vor dem `ALTER`, Muster aus
`0001_baseline.py` — Fallstrick 3 des Handoffs: `ADD COLUMN` kann kein `IF NOT EXISTS`, und
eine Migration muss nach ihrer eigenen Rücknahme wieder vorwärts laufen. Pflicht:
Rundlauftest up → down → up, und zwar so, dass er auch prüft, was `down()` wirklich entfernt
hat — der entsprechende Befund aus Etappe 3 ist noch offen und soll sich hier nicht
wiederholen.

`shift_requirements` bleibt unangetastet in der Datenbank. Entfernt wird sie erst nach dieser
Etappe, wie die übergeordnete Spec es vorsieht.

## 8. API

**Geändert:**

- `POST /employees` und `PUT /employees/<id>` nehmen `max_daily_hours` entgegen, über das
  bestehende `parse_optional_hours()`. Fehlt der Wert, gilt 10.
- `GET /employees` und `GET /employees/<id>` liefern es mit.
- `POST /schedules/generate` schreibt jetzt `start_time`/`end_time` und ein möglicherweise
  `NULL`-es `shift_type_id` in `shift_assignments`.

**Neu (Vorarbeit, siehe §10):**

- `GET/PUT /employees/<id>/availability` mit `require_self_or_hr`.

**Warnungen auf dem Handkorrektur-Pfad.** `constraint_warnings()` muss die drei neuen Regeln
als nicht blockierende Warnung melden: überschneidende Blöcke am selben Tag, überschrittene
Tagesarbeitszeit, verletzte Ruhezeit zum Nachbartag. Es importiert die Prüffunktionen aus
`scheduler.py` und **dupliziert sie nicht** — `swap_assignments()` und
`replacement_suggestions()` bauen ihrerseits auf `constraint_warnings()` auf, alle Pfade
hängen damit an einer Implementierung. „Warnung statt Verbot" bleibt: HR ist der Chef.

Alle neuen Texte in `backend/i18n.py` und `frontend/src/i18n/translations.js`, deutsch und
englisch.

## 9. Frontend

| Seite | Änderung |
|---|---|
| `ShiftTypes.jsx` | Die Wochentags-Bedarfszahlen verschwinden. Die Schichtart bleibt Vorlage: Name, Zeiten, Farbe |
| `Employees.jsx` | Feld `max_daily_hours` mit Hinweis, dass mehr als 8 h nach § 3 ArbZG einen Ausgleich über sechs Monate voraussetzt, den das Tool nicht prüft |
| `ShiftCell.jsx` | Zellenkollision beheben (Vorarbeit, §10) |
| `CalendarView.jsx` | Mehrere Blöcke einer Person am selben Tag als solche darstellen |

Die Deckungslücken-Anzeige und die Darstellung echter Zuweisungszeiten stehen bereits aus
Etappe 2 und 3.

## 10. Vorarbeiten

Zwei zurückgestellte Befunde, die die Grundlage dieser Etappe betreffen und **vor** dem
Zuschnitt erledigt werden:

1. **Route `GET/PUT /employees/<id>/availability`** mit `require_self_or_hr`, wie in §6 der
   übergeordneten Spec vorgesehen. Heute hängen die Fenster an `/employees/<id>` mit
   `@hr_required` — sicherheitsseitig die konservative Richtung, aber ein Mitarbeiter sieht
   seine eigenen Arbeitszeiten nicht. Etappe 4 macht die Fenster zur zentralen Steuergröße
   der Planung; dass die betroffene Person sie nicht einsehen kann, wird damit unhaltbar.
2. **Zellenkollision.** Mehrere vorlagenlose Blöcke am selben Datum landen in derselben Zelle,
   und nur der erste liefert die Zellenzeile. Bisher war das unerreichbar — ab Etappe 4
   erzeugt der Generator solche Blöcke regelmäßig.

## 11. Was gratis abfällt

`coverage_gaps_for_month()` rechnet Deckungslücken bereits aus den Bändern gegen die
tatsächlichen Zuweisungen, und unbesetzte Blöcke tragen `employee_id NULL`, zählen also nicht
als Deckung. Die „benannten Restlücken" aus §5 der übergeordneten Spec entstehen damit von
selbst. **Etappe 4 baut keinen zweiten Lückenmechanismus.**

## 12. Tests

| Ebene | Was |
|---|---|
| `test_scheduler.py` (23 Bestandstests) | Bleiben unverändert und grün. Rückwärtskompatibilitätsgarantie |
| `test_block_planner.py` (neu) | Phase A deckt abgeleitete Bänder deckungsgleich mit dem alten `build_slots()`; Zuschnitt bei Teilüberdeckung; `MIN_BLOCK_MINUTES` greift; vorlagenloser Block bei fehlender Vorlage; Band über Mitternacht; geschlossener Tag liefert nichts; Iterationsschranke liefert Teilergebnis statt Fehler |
| `test_scheduler_split_shifts.py` (neu) | Zwei Blöcke am selben Tag werden zugewiesen; überschneidende Blöcke nicht; `max_daily_hours` bindet über die Summe; Ruhezeit misst letztes Ende gegen ersten Beginn des Folgetags, nicht über die Tagesunterbrechung |
| `test_migrations.py` / `_postgres.py` | Rundlauf `0008` up → down → up, mit Prüfung dessen, was `down()` entfernt hat |
| API | `max_daily_hours` schreiben und lesen; Generator schreibt Zeiten und `NULL`-Vorlagen; die drei neuen Warnungen in `constraint_warnings()`; die neue Verfügbarkeitsroute in beiden Rollen |
| Frontend (Vitest) | Mehrere Blöcke einer Person am selben Tag; vorlagenlose Blöcke kollidieren nicht mehr |
| `benchmark.py` | Gegenprobe alt gegen neu auf unverändertem Bestand (§5.2 Phase A), plus ein Szenario mit Fenstern, das belegt, dass Zuschnitt Lücken schließt |

Vorgehen wie in allen Etappen: erst der Test, dann der Code. Vor jedem Commit die Frage aus
Fallstrick 4 — *würde dieser Test fehlschlagen, wenn ich das Feature lösche?*

## 13. Fallstricke, die hier greifen

Aus dem Handoff, weil sie diese Etappe unmittelbar betreffen:

- **3** — `ADD COLUMN` gehört in eine `.py`-Migration mit Wächter, Rundlauftest Pflicht
- **4** — Tests, die nichts prüfen; vier Fälle bisher
- **6** — die 23 Bestandstests bleiben unverändert
- **7** — Kommentarsprache folgt der Datei. `scheduler.py` ist englisch, `coverage_model.py`
  deutsch; `block_planner.py` folgt `coverage_model.py`, weil es dessen Nachbar ist
- **10** — Postgres-Verhalten nie aus SQLite schließen
- **13** — `WHERE shift_type_id = ?` mit `None` trifft keine Zeile
- **15** — zwei gleichnamige Testfunktionen überschreiben sich still; bei zwei neuen
  Testdateien mit verwandten Themen ist das eine reale Gefahr. `pytest --collect-only` zeigt es
- **16** — kein Modulname, der ein installiertes Paket verdeckt

## 14. Bewusst nicht dabei

- **Kein Laufzeit-Umschalter** zwischen altem und neuem Bedarfspfad
- **Kein Entfernen von `shift_requirements`** — erst nach dieser Etappe
- **Keine Pausenmodellierung** (§ 4 ArbZG) und keine Durchschnittsprüfung (§ 3 Satz 2)
- **Keine Sonntagsregeln** (§ 11 ArbZG), keine „höchstens sechs Tage in Folge"
- **Kein Request-Feld für `MIN_BLOCK_MINUTES`**
- **Kein Minutenraster** — Ereignispunkte reichen
- **Keine Mehrmonatsplanung**

## 15. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Stufe 1 erzeugt schlechtere Pläne als heute | Phase A ist auf unverändertem Bestand nachweislich deckungsgleich mit `build_slots()` (§5.2); der Benchmark vergleicht vorher/nachher; Rückweg wäre ein Revert |
| Der Eingriff in den Suchkern kostet Laufzeit oder Fairness | Drei eng umrissene Stellen, alle nach dem Muster der bestehenden `week_minutes`-Prüfung; die 23 Bestandstests und der Benchmark decken Regressionen auf |
| Phase C terminiert nicht | Iterationsschranke mit Teilergebnis statt Abbruch (§5.4) |
| Geteilter Dienst erzeugt Pläne, die HR nicht will | `max_daily_hours` bindet; Stufe 1 deckt vorrangig mit Vorlagen, damit der Tag nicht in Schnipsel zerfällt; `MIN_BLOCK_MINUTES` verhindert Kleinstblöcke |
| Der Zuschnitt bleibt in Produktion wirkungslos | `employee_availability` ist derzeit leer und alle Mitarbeiter stehen auf `'anytime'` — der Zuschnitt greift erst, wenn jemand Fenster pflegt. Das ist erwartet, kein Fehler: die Umstellung auf Bänder wirkt sofort, der Zuschnitt sobald Fenster existieren |
