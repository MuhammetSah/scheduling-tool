# Design: Etappe 5c — der Achtstundenschnitt

**Datum:** 2026-08-22
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Geschwister:** [`5a — Ruhepausen`](2026-08-22-etappe-5a-ruhepausen-design.md), [`5b — Sechstageregel und freie Sonntage`](2026-08-22-etappe-5b-sonntage-design.md)
**Status:** Entwurf

---

## 1. Ziel

Die letzte offene Regel aus Etappe 4. [§ 3](https://www.gesetze-im-internet.de/arbzg/__3.html)
erlaubt zehn Stunden werktäglich **nur**, wenn im Durchschnitt über sechs Kalendermonate oder
24 Wochen acht Stunden nicht überschritten werden. Etappe 4 hat `max_daily_hours` mit dem
Standard 10 eingeführt und dabei ausdrücklich festgehalten: ohne diesen Nachweis ist die Grenze
**rechtlich nicht selbsttragend**. Das holt diese Etappe nach.

**Gemeldet, nicht erzwungen** — so entschieden, und aus einem Grund, der im Code stehen
gehört: ob zehn Stunden heute zulässig sind, entscheidet sich erst in den kommenden Monaten.
Beim Erzeugen darauf zu bestehen hieße entweder falsch zu rechnen oder unnötig zu beschränken.

## 2. Was das Gesetz verlangt, und was daran unbequem ist

**Der Arbeitgeber wählt den Bezugszeitraum** — sechs Kalendermonate *oder* 24 Wochen — und darf
ihn rollierend legen; das Gesetz schreibt keine Kalenderhalbjahre vor.

**Gerechnet wird je Werktag**, nicht je gearbeitetem Tag und nicht je Kalendertag. Werktage sind
Montag bis Samstag; Sonn- und Feiertage zählen nicht. Der Vergleich lautet also:

```
Arbeitszeit im Zeitraum  ≤  8 h × Werktage im Zeitraum
```

Das ist ein großzügiger Nenner. Wer fünf Tage die Woche acht Stunden arbeitet, kommt auf rund
6,2 Stunden je Werktag — die Grenze bindet erst bei vielen langen Tagen. Das ist keine
Nachlässigkeit der Umsetzung, sondern was die Norm sagt.

## 3. Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Bezugszeitraum | **24 Wochen**, rollierend, endend am Monatsletzten | Feste Länge, keine Monatslängen-Varianz. Sechs Kalendermonate wären ebenso zulässig; die Wahl steht dem Arbeitgeber zu, und eine Einstellung dafür wäre Fläche, solange niemand die andere Variante verlangt |
| Wo gemeldet | In `GET /schedules/<year>/<month>`, neben `coverage_gaps` | Dort schaut HR ohnehin hin, und die Größe gehört zu einem Monat wie die Deckungslücken |
| Warnung beim Zuweisen | **Nein** | Eine Aggregation über 24 Wochen bei jeder einzelnen Zuweisung zu melden wäre laut und teuer, und die Zahl ändert sich durch eine Zuweisung kaum. „Gemeldet" heißt hier: einmal je Monatsansicht |
| Arbeitszeit | **Netto**, wie seit 5a | § 2 Abs. 1 lässt keine andere Lesart zu |

## 4. Die Meldung

`GET /schedules/<year>/<month>` liefert zusätzlich:

```
average_hours: [
  {employee_id, employee_name, hours_worked, hours_allowed, average_per_working_day}
]
```

**Nur Überschreitungen**, wie `coverage_gaps` auch nur Lücken meldet. Wer unter der Grenze
liegt, erzeugt keinen Eintrag — sonst stünde bei jedem Monat die ganze Belegschaft in der
Liste.

`average_per_working_day` wird mitgeliefert, weil „38 Stunden zu viel" ohne Bezugsgröße nichts
sagt, „8,4 Stunden im Schnitt statt 8" dagegen sofort.

## 5. Die Rechnung

Für jeden aktiven Mitarbeiter:

1. Fenster: die 24 Wochen (168 Tage), die am Letzten des angezeigten Monats enden.
2. Arbeitszeit: die Summe der **Netto**-Minuten aller Zuweisungen dieser Person im Fenster —
   `assignment_hours()` für die Zeiten, `break_minutes` für die Pause, beides wie in 5a.
3. Werktage: Montag bis Samstag im Fenster. Das sind bei 168 Tagen genau 144.
4. Überschritten, wenn `Minuten > 8 × 60 × Werktage`.

Geladen wird das für alle Mitarbeiter in **einer** Abfrage über das Fenster, nicht je Person —
dieselbe Sorgfalt, mit der `coverage_gaps_for_month()` seine drei Abfragen für den ganzen Monat
macht statt je Tag.

## 6. Was das Tool dabei nicht weiß

- **Feiertage.** Sie sind keine Werktage und müssten den Nenner verkleinern. Ohne den Kalender
  aus 5d ist der Nenner um die Feiertage zu groß — bei rund fünf Feiertagen in 24 Wochen also
  144 statt 139, gut drei Prozent. Die Meldung ist dadurch **zu nachsichtig**, nicht zu streng:
  sie könnte eine Überschreitung übersehen, nie eine erfinden. Das gehört gesagt, weil es die
  unangenehmere Richtung ist. Mit 5d löst es sich auf.
- **Wann jemand angefangen hat.** Wer seit zwei Wochen dabei ist, wird trotzdem gegen 144
  Werktage gerechnet und liegt weit darunter. Das erzeugt keine falsche Meldung, nur eine
  fehlende — und eine fehlende Meldung für jemanden, der zwei Wochen dabei ist, ist richtig.
- **Zeiten außerhalb dieses Tools.** Urlaub, Krankheit und Arbeit bei einem zweiten Arbeitgeber
  (die § 2 Abs. 1 ausdrücklich zusammenrechnet) stehen nirgends.

## 7. Tests

| Ebene | Was |
|---|---|
| `test_working_time.py` (erweitert) | Die reine Rechnung: Werktage im Fenster, Grenze, Überschreitung. Kanten: genau an der Grenze meldet nicht, eine Minute darüber schon |
| API | Ein Monat mit langen Schichten meldet; derselbe Monat mit kurzen nicht. **Gegenprobe:** die Meldung rechnet netto — dieselben Blöcke mit ausdrücklicher Pause 0 überschreiten, mit gesetzlicher Pause nicht |
| API | Ein Mitarbeiter ohne Zuweisungen taucht nicht auf |
| Frontend | Die Liste anzeigen, wo `CoverageGaps` schon steht |

## 8. Bewusst nicht dabei

- **Sechs Kalendermonate als Alternative** und eine Einstellung dafür (§3)
- **Eine Warnung beim Zuweisen** (§3)
- **Durchsetzung im Generator** — der Kern der Entscheidung, siehe §1
- **Feiertage im Nenner** — das ist 5d (§6)
- **Kein Schemaeingriff.** Alles wird gerechnet

## 9. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Meldung ist zu nachsichtig, weil Feiertage fehlen | Ausdrücklich dokumentiert (§6); löst sich mit 5d |
| Die Abfrage über 24 Wochen je Monatsansicht wird teuer | Eine Abfrage für alle Mitarbeiter, nicht je Person (§5). Bei drei Mitarbeitern und 168 Tagen ist das ohnehin unkritisch; der Aufbau hält es auch bei dreißig aus |
| HR liest „8,4 statt 8" als harten Verstoß | Die Formulierung im Frontend sagt, dass zehn Stunden zulässig sind, *wenn* der Schnitt stimmt — nicht dass etwas verboten wurde |
