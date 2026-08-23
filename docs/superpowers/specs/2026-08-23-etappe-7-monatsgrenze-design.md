# Design: Etappe 7 — Über die Monatsgrenze

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Der erste Roadmap-Punkt nach Etappe 6, und bewusst kein neues Merkmal, sondern eine Lücke in dem,
was das Tool bereits zusichert:

> Generation-time weekly-hours/rest-period checks that see across a month boundary (currently only
> the manual-edit warning path does)

**Ein Monat ist ein Abrechnungszeitraum, keine Einheit der Ruhe.** Zwei Regeln laufen quer über die
Grenze und hörten an ihr auf:

| Regel | Was danebenging |
|---|---|
| § 5 Abs. 1 ArbZG, elf Stunden zwischen zwei Schichten | Nachtdienst bis 06:00 am 31., Frühdienst ab 06:00 am 1. — jeder für sich in Ordnung, zusammen null Stunden Ruhe |
| Das Wochenstundenziel | Die Kalenderwoche endet nicht am Monatsletzten. Ein leerer Zähler schenkt jedem am Ersten ein frisches Wochenbudget |

Das Ergebnis ist ein Plan, der in sich jede Regel einhält und an genau einer Stelle im Jahr eine
bricht — der unauffälligste Fehler, den ein Dienstplan haben kann.

## 2. Was schon ging, und warum

**Der Sechs-Tage-Lauf und das Sonntagsbudget sehen die Grenze seit Etappe 5b.**
`scheduling_history()` in `app.py` zählt beide aus der Datenbank über das ganze Jahr und übergibt
sie je Mitarbeiter.

Der Unterschied: diese beiden sind **Zahlen**, und Zahlen lassen sich vorab reichen. Ruhezeit und
Wochenstunden brauchen **Zeiten** — und die lebten ausschließlich im Suchzustand eines Laufs, der
am Ersten leer beginnt.

## 3. Der Zustand beginnt nicht mehr leer

`generate_schedule(..., boundary=...)` nimmt entgegen, was die Nachbarmonate schon halten:
`day_hours` je (Mitarbeiter, Datum) und `week_minutes` je (Mitarbeiter, Wochenbeginn).

`week_minutes` wird direkt als Anfangsstand des vorhandenen Zählers gesetzt — die Prüfung dahinter
bleibt unverändert.

**`day_hours` wird ausdrücklich nicht in die `day_hours` des Suchlaufs verschmolzen**, sondern
liegt daneben und wird nur von `rest_period_ok()` gelesen. Das ist der Punkt, an dem die
naheliegende Lösung falsch gewesen wäre: `worked_dates()` liest die Schlüssel von `day_hours`, und
`sundays_worked_so_far()` zählt daraus die Sonntage. Ein Sonntag am Monatsrand wäre dann **doppelt**
belastet worden — einmal hier und einmal über `sundays_worked_in_year`, das `scheduling_history()`
längst über das ganze Jahr zählt.

`None` — die Vorgabe — stellt das alte Verhalten her. Das ist es, was die 23
Kompatibilitätstests in `test_scheduler.py` und den Benchmark unverändert lässt.

## 4. Was geladen wird

`boundary_context(cursor, year, month)` liest die gespeicherten Pläne **sieben Tage** zu beiden
Seiten:

- Die Ruhezeit braucht nur die zwei **unmittelbar** flankierenden Daten — ein Platz im Monat kann
  an keine anderen grenzen. Den ganzen Vormonat einzubeziehen sperrte den Ersten grundlos, und
  dafür gibt es eine Gegenprobe
- Die straddelnde Woche reicht bis zu sechs Tage in den Nachbarmonat

**Zuweisungen innerhalb des erzeugten Monats sind ausgeschlossen.** Dieselbe Anfrage löscht sie
gleich; sie mitzuzählen bedeutete, jeden für Schichten zu belasten, die gerade ersetzt werden.
Dieselbe Begründung, die `scheduling_history()` seit Etappe 5b notiert.

**Die Zeiten kommen über `assignment_hours()`, nicht aus den beiden Spalten.** Das Review zu PR #29
hat gefunden, dass die erste Fassung sie direkt las — eine gespeicherte Zuweisung muss ihre Zeiten
aber nicht selbst tragen: sie kann sie aus einer Tagesausnahme oder aus der Schichtart beziehen.
Eine Nachtschicht, die ihre Zeiten aus der Vorlage nimmt, war damit **unsichtbar**, und der Erste
wurde frei geplant, als gäbe es sie nicht. `assignment_hours()` löst genau diese drei Ebenen auf
und stand die ganze Zeit daneben.

**Die Lehre:** wer eine bestehende Datenstruktur neu ausliest, muss die Ebenen mitlesen, die ihre
vorhandenen Leser schon kennen. Zwei Spalten zu nehmen, wo eine Funktion drei Ebenen auflöst, ist
kein Abkürzen, sondern ein anderes Datenmodell.

Bleibt wirklich nichts übrig — keine Vorlage und keine eigenen Zeiten —, wird der Block
übersprungen: ohne Minutenachse kann er weder eine Ruhezeit begrenzen noch Arbeitszeit beitragen.
Übersprungen statt geraten, mit eigener Gegenprobe.

## 5. Tests

`backend/test_api_monatsgrenze.py`, neun Tests — und die Gegenproben sind hier die eigentliche
Arbeit:

| Test | Wogegen er schützt |
|---|---|
| Ruhezeit über den Wechsel | Der Kern |
| Ohne Nachtdienst wird sie am Ersten eingeplant | Ein Generator, der am Ersten grundsätzlich niemanden einplant, wäre sonst grün |
| Ein Block am 29.08. stört den Ersten nicht | Ein zu weit gefasstes Fenster wäre sonst grün |
| Ohne Ruhezeitvorgabe ändert sich nichts | Aus einem einstellbaren Wert wäre sonst still eine feste Regel geworden |
| Wochenstunden über den Wechsel | Der zweite Kern |
| In der Woche darauf arbeitet sie wieder | Gesperrt ist die Woche, nicht der Mitarbeiter |
| Ohne Wochenziel ändert sich nichts | Wie bei der Ruhezeit |

**Zwei Dinge sind beim Schreiben schiefgegangen und stehen deshalb in den Docstrings:**

1. Die Gegenprobe „ohne Ruhezeitvorgabe" wurde zuerst mit `min_rest_hours: None` geschrieben. Die
   Spalte hat aber **11 als Vorgabe**, und ein gesendetes `null` landet dort — der Test war damit
   eine zweite Ausgabe des Haupttests: grün vor der Behebung, rot danach, und beides aus dem
   falschen Grund. Ausgedrückt wird „keine Ruhezeit" als `0`.
2. Die Wochentests waren **sofort** grün. Das belegt nichts, solange nicht gezeigt ist, dass sie
   ohne die Behebung rot sind — nachgeprüft, indem die Saat des Wochenzählers versuchsweise
   entfernt wurde.

## 6. Bewusst nicht dabei

- **Die Tagesarbeitszeit über die Grenze.** § 3 ArbZG begrenzt den *Werktag*; ein Tag liegt immer
  ganz in einem Monat. Es gibt nichts zu überbrücken
- **Der Achtstundenschnitt über 24 Wochen.** Er wird gemeldet, nicht erzwungen (Etappe 5c), und
  liest ohnehin die gespeicherten Daten über den ganzen Zeitraum
- **Ein erneutes Erzeugen des Nachbarmonats, wenn dieser dadurch ungültig wird.** Das Tool plant
  einen Monat auf einmal; wer August neu erzeugt, nachdem September steht, bekommt einen August,
  der den September respektiert — nicht umgekehrt. Ein Plan, der andere Pläne umschreibt, wäre
  eine deutlich größere Entscheidung
- **Eine Warnung, wenn der Nachbarmonat noch nicht geplant ist.** Dann gibt es nichts zu
  respektieren, und das ist kein Mangel
