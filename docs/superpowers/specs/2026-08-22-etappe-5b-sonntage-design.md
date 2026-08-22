# Design: Etappe 5b — Sechstageregel und freie Sonntage

**Datum:** 2026-08-22
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §10, Etappe 5
**Geschwister:** [`5a — Ruhepausen`](2026-08-22-etappe-5a-ruhepausen-design.md)
**Status:** Entwurf, mit dem Nutzer abgestimmt

---

## 1. Ziel

Etappe 4 hat drei Regeln des Arbeitszeitgesetzes umgesetzt und drei offengelassen. 5a hat die
Ruhepausen nachgeholt. Diese Etappe holt die Sonn- und Feiertagsruhe nach, soweit sie den
Planer bindet:

| Regel | Norm |
|---|---|
| Höchstens sechs Tage in Folge | [§ 11 Abs. 3](https://www.gesetze-im-internet.de/arbzg/__11.html), über die Implikation unten |
| Mindestens 15 beschäftigungsfreie Sonntage im Kalenderjahr | [§ 11 Abs. 1](https://www.gesetze-im-internet.de/arbzg/__11.html) |

Beide hart im Generator, beide als Warnung auf dem Handkorrektur-Pfad.

## 2. Warum die Sechstageregel den Ersatzruhetag erfüllt

§ 11 Abs. 3 verlangt für jeden gearbeiteten Sonntag einen Ersatzruhetag „innerhalb eines den
Beschäftigungstag einschließenden Zeitraums von zwei Wochen", und für jeden gearbeiteten
Werktags-Feiertag einen innerhalb von acht Wochen.

Das ist eine Bedingung über das **Fehlen** von Zuweisungen. Alle bisherigen harten Bedingungen
im Suchkern sind lokal — passt diese Person auf diesen Block? „Diese Person braucht irgendwann
in einem Zweiwochenfenster einen freien Tag" lässt sich erst beurteilen, wenn der ganze Monat
steht; ein Backtracking-Suchlauf tut sich damit schwer.

**Wer nie mehr als sechs Tage in Folge arbeitet, hat spätestens alle sieben Tage einen freien
Tag.** Damit ist das Zweiwochenfenster der Sonntage erfüllt — und das Achtwochenfenster der
Feiertage erst recht. Die Regel ist lokal, billig und im Suchkern genauso prüfbar wie die
Ruhezeit.

**Der Preis, und er gehört benannt:** die Sechstageregel ist *strenger* als § 11 Abs. 3. Wer
Montag bis Sonntag durcharbeitet und am Montag darauf frei hat, erfüllt die Norm — die
Sechstageregel lehnt ihn trotzdem ab. Das ist eine bewusste Vereinfachung zugunsten einer
Bedingung, die der Planer überhaupt tragen kann, und keine Auslegung des Gesetzes.

## 3. Was diese Etappe nicht tut

- **§ 9 wird nicht durchgesetzt.** Sonn- und Feiertagsarbeit ist grundsätzlich verboten, § 10
  nimmt ganze Branchen aus — Gaststätten, Krankenhäuser, Pflege, Verkehr, Bäckereien und ein
  Dutzend weitere. Ob dieser Betrieb darunterfällt, ist eine Tatsache über den Betrieb und
  keine ableitbare Größe. Entschieden wird das wie bisher über die Öffnungszeiten: ein sonntags
  geschlossener Betrieb hat keinen Sonntagsbedarf und bekommt keine Blöcke. **Ein Schalter
  „Sonntagsarbeit zulässig" wird ausdrücklich nicht gebaut** — er täte nichts, was die
  Öffnungszeiten nicht schon tun.
- **Kein Feiertagskalender.** Er wurde beim Entwurf herausgelöst und wird Etappe 5d. Der Grund
  steht in §4.
- **Der Ersatzruhetag wird nicht eigens gemeldet.** Er folgt aus der Sechstageregel; eine
  zweite Prüfung, die dasselbe noch einmal ausrechnet, wäre Ballast.

## 4. Warum der Feiertagskalender herausgelöst wurde

Der Nutzer hatte zunächst einen eingebauten Kalender mit Bundeslandauswahl gewählt. Beim
Ausarbeiten zeigte sich, dass er im gewählten Zuschnitt **keine Regel durchsetzt**:

- § 11 Abs. 3 für Feiertage ist durch die Sechstageregel abgedeckt (§2);
- § 9 wird nicht durchgesetzt (§3);
- § 11 Abs. 1 betrifft nur Sonntage.

Was bleibt, ist Kennzeichnung und Warnung — echter Nutzen, aber Bewusstsein statt
Regeldurchsetzung. Eine Tabelle mit beweglichen Osterdaten und rund einem Dutzend regionaler
Sonderfälle ist dafür ein eigenes Stück Arbeit und bekommt eine eigene Spec, statt die zwei
Regeln aufzuhalten, die wirklich binden.

## 5. Das strukturell Neue: der Generator bekommt Vorgeschichte

Bisher sieht `generate_schedule()` ausschließlich seinen Monat. Das war eine bewusste Grenze,
an der `max_shifts_per_month` und die Ruhezeitprüfung am Monatsrand enden. Beide Regeln dieser
Etappe reichen darüber hinaus, also muss die Grenze fallen — kontrolliert, an genau einer
Stelle.

`app.py` lädt je aktivem Mitarbeiter zwei Zahlen und gibt sie im Mitarbeiter-Dict mit:

| Feld | Bedeutung |
|---|---|
| `days_worked_before_month` | Wie viele Kalendertage unmittelbar vor dem Monatsersten lückenlos gearbeitet wurden. 0, wenn der Tag davor frei war |
| `sundays_worked_in_year` | Sonntage im Kalenderjahr des geplanten Monats, an denen die Person mindestens einen Block hat — **ohne** den Monat, der gerade erzeugt wird |

Beide sind optional: fehlen sie, gelten sie als 0 und die Prüfungen verhalten sich wie ohne
Vorgeschichte. Dasselbe Muster wie bei `weekly_hours` und `max_daily_hours` — die 23
Bestandstests in `test_scheduler.py` liefern sie nicht und bleiben unverändert grün.

### 5.1 Die Falle: den eigenen Plan nicht gegen sich verwenden

`generate_schedule_route()` löscht die Zuweisungen des Monats **nach** dem Suchlauf. Beim Laden
der Vorgeschichte stehen sie also noch in der Datenbank. Würden sie mitgezählt, bestrafte der
Planer jeden für Schichten, die er ihm im selben Atemzug wegnimmt: wer im August schon vier
Sonntage im Plan hat, bekäme sein Budget um vier gekürzt, obwohl dieser Plan gerade ersetzt
wird.

Abgegrenzt wird deshalb **über den Datumsbereich des Monats**, nicht über `schedule_id`. Der
Datumsbereich ist die Wahrheit; eine Zuweisung mit einem Datum im Zielmonat gehört
dorthin, gleich unter welcher `schedule_id` sie hängt.

### 5.2 Ein Sonntag zählt einmal

„Beschäftigungsfrei" heißt: kein einziger Block an diesem Tag. Ein geteilter Dienst mit zwei
Blöcken macht aus einem Sonntag keine zwei. Gezählt werden also **Daten**, nicht Zuweisungen —
`SELECT DISTINCT date`.

## 6. Im Suchkern

Zwei Prüfungen in `eligible_candidates()`, dazu Buchführung in `backtrack()` nach dem Muster
von `day_minutes` aus Etappe 4.

### 6.1 Sechstageregel

```python
consecutive_days_with(eid, iso_date) -> int
```

Zählt die lückenlose Kette gearbeiteter Kalendertage, die entstünde, wenn `eid` an `iso_date`
arbeitete: vom Datum aus nach links und nach rechts, solange der Nachbartag belegt ist. Links
endet die Kette am Monatsersten und geht dort in `days_worked_before_month` über.

**In beide Richtungen, nicht nur nach links.** Der Suchlauf geht bei `CHRONOLOGICAL` zwar in
Kalenderreihenfolge vor, bei `MOST_CONSTRAINED` aber nicht — und `AUTO` benutzt beide. Nur nach
links zu zählen ließe eine Kette entstehen, die sich von hinten aufbaut. Dieselbe Überlegung
wie bei `rest_period_ok()`, das den Vor- **und** den Folgetag prüft.

Ein Kandidat fällt weg, wenn die Kette 7 erreichen würde.

Gebraucht wird dafür eine Menge der belegten Tage je Person: `day_hours` und `day_untimed` aus
Etappe 4 haben sie bereits als Schlüssel `(employee_id, date)` — eine dritte Struktur wäre
Ballast. Ein Hilfsprädikat `works_on(eid, iso_date)` liest beide.

### 6.2 Freie Sonntage

```python
sunday_budget(emp) = max(0, sundays_in_year - 15 - emp['sundays_worked_in_year'])
```

`sundays_in_year` ist die Zahl der Sonntage im Kalenderjahr des geplanten Monats (52 oder 53) —
ein Monat liegt immer ganz in einem Jahr, die Frage stellt sich also nur einmal je Suchlauf.

Ein Kandidat fällt an einem Sonntag weg, wenn

```
sonntage_in_diesem_lauf(eid, ohne das aktuelle Datum) >= sunday_budget(emp)
```

Gezählt werden dabei **verschiedene Sonntagsdaten**, nicht Blöcke, und das aktuelle Datum ist
ausgenommen: wer an diesem Sonntag schon einen Block hat, verbraucht mit dem zweiten kein
zweites Budget (§5.2). Ohne diese Ausnahme wäre ein geteilter Dienst am Sonntag teurer als
einer unter der Woche, wofür es keinen Grund im Gesetz gibt.

Ist das Budget negativ, weil jemand die Grenze in der Vergangenheit bereits gerissen hat, wird
es als 0 behandelt: der Planer plant ihn an keinem weiteren Sonntag ein, aber er wirft keinen
Fehler über Daten, die er nicht verursacht hat.

## 7. Handkorrektur

Zwei neue Warnungen in `constraint_warnings()`, beide nicht blockierend:

- `warn_seventh_consecutive_day` — DE: „{name} käme damit auf {days} Tage in Folge; nach § 11
  Abs. 3 ArbZG ist spätestens nach sechs ein Ersatzruhetag fällig."
- `warn_sunday_budget_exhausted` — DE: „{name} hätte damit nur noch {free} freie Sonntage in
  {year}; § 11 Abs. 1 ArbZG verlangt mindestens 15."

Der Handkorrektur-Pfad rechnet gegen gespeicherte Daten und sieht deshalb **auch nach vorn**
über den Monatsrand — anders als der Generator (§8). Er ist damit strenger, nicht laxer.

## 8. Was das Tool weiterhin nicht kann

- **Die Sechstageregel über den Monatsrand nach vorn.** Blöcke des Folgemonats existieren beim
  Erzeugen noch nicht; wer am 31. arbeitet, kann durch einen später erzeugten Folgemonat auf
  sieben Tage kommen. Dieselbe Grenze, an der `max_shifts_per_month` und die Ruhezeitprüfung am
  Monatsrand schon enden. `constraint_warnings()` sieht sie, der Generator nicht
- **Der Ersatzruhetag im Wortlaut des Gesetzes** — siehe §2, die Sechstageregel ist strenger
- **§ 9 und § 10** — siehe §3

## 9. Tests

| Ebene | Was |
|---|---|
| `test_scheduler.py` (23 Bestandstests) | Unverändert grün. Sie liefern keine Vorgeschichte, beide Prüfungen greifen damit nicht |
| `test_scheduler_rest_days.py` (neu) | Der siebte Tag in Folge bleibt offen; sechs gehen. Die Kette baut sich auch **von hinten** auf (Gegenprobe zur Nur-nach-links-Zählung). `days_worked_before_month` verlängert die Kette über den Monatsanfang. Das Sonntagsbudget bindet; ein zweiter Block am selben Sonntag verbraucht kein zweites Budget |
| `test_api_schedules.py` (erweitert) | **Die wichtigste Gegenprobe:** ein Monat, der zweimal erzeugt wird, ergibt beide Male denselben Plan. Würde die Vorgeschichte den eigenen Monat mitzählen, wäre der zweite Lauf ärmer als der erste |
| API | Die beiden neuen Warnungen, je mit Gegenprobe |
| Frontend | Keine Änderung — die Warnungen kommen fertig übersetzt aus dem Backend |

## 10. Fallstricke, die hier greifen

- **4** — Tests, die nichts prüfen. Sechs Fälle bisher
- **6** — die 23 Bestandstests bleiben unverändert
- **7** — Kommentarsprache folgt der Datei
- **13** — `WHERE ... = ?` mit `None` trifft keine Zeile

## 11. Bewusst nicht dabei

- Ein Schalter „Sonntagsarbeit zulässig" (§3)
- Der Feiertagskalender (§4, wird 5d)
- Eine eigene Meldung für den Ersatzruhetag (§3)
- Konfigurierbarkeit von „sechs Tage" und „15 Sonntage" — beides steht im Gesetz
- **Kein Schemaeingriff.** Beide Größen werden gerechnet, nicht gespeichert. Die erste Etappe
  seit 0 ohne Migration

## 12. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Vorgeschichte zählt den eigenen Monat mit und bestraft Leute für Schichten, die gerade ersetzt werden | Abgrenzung über den Datumsbereich (§5.1); der Zweimal-Erzeugen-Test in §9 ist genau dafür da |
| Die Kette wird nur nach links gezählt und lässt sich von hinten aufbauen | Eigener Test dafür (§9); die Zählung geht in beide Richtungen (§6.1) |
| Das Sonntagsbudget sperrt jemanden dauerhaft, weil die Vergangenheit die Grenze schon riss | Negatives Budget wird als 0 gelesen, nicht als Fehler (§6.2) |
| Der Planer findet weniger Besetzungen und meldet mehr Lücken | Das ist die Wirkung, nicht der Fehler: die Lücken waren vorher auch da, nur unbenannt. Der Benchmark zeigt die Größenordnung |
