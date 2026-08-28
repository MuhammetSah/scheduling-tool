# Design: Etappe 9 — Die letzten beiden ArbZG-Regeln

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Das README nannte sie seit Etappe 5 als das, was das Tool der Personalabteilung überlässt:

> the position of a break within a block (§ 4 Satz 3), and whether the business is exempt from
> Sunday rest at all (§ 9, § 10)

Beides sind keine fehlenden Merkmale, sondern eine Prüf- und eine Modelllücke.

## 2. § 4 Satz 3 — die Lage der Pause

> „Länger als sechs Stunden hintereinander dürfen Arbeitnehmer nicht ohne Ruhepause beschäftigt
> werden."

Das Tool kannte nur `break_minutes` — eine **Dauer ohne Uhrzeit**. Eine halbe Stunde Pause ab
Schichtbeginn erfüllt Satz 1 und verstößt gegen Satz 3, und beide Fälle sahen in der Datenbank
gleich aus.

**Das ist auch eine Modelllücke, nicht nur eine Prüflücke.** § 4 Satz 1 verlangt „im voraus
feststehende Ruhepausen". Eine Dauer ohne Lage steht nicht fest. Die neue Spalte `break_start`
schließt beides.

**Warum sie NULL-bar ist und keine Vorgabe bekommt:** für jeden Block, den dieses Tool bauen kann
— höchstens zehn Stunden Spanne, mindestens dreißig Minuten Pause — gibt es *immer* eine
zulässige Lage. Eine fehlende Angabe ist deshalb nie ein *bekannter* Verstoß. Sie zu bemängeln
hieße, bei jedem einzelnen Block zu warnen; sie zu erzwingen hieße, jeden Bestandsplan für
ungültig zu erklären; und eine erfundene Vorgabe wäre eine Behauptung über einen Betriebsablauf,
den das Tool nicht kennt.

Die Prüfung greift also genau dann, wenn jemand eine Lage **angegeben** hat — und dort hat sie
Zähne: eine Pause am Rand lässt bis zu siebeneinhalb Stunden am Stück.

**Genau sechs Stunden bleiben erlaubt.** Der Satz sagt „länger als", und die Grenze selbst hat
einen eigenen Test.

**Über Mitternacht** gilt dieselbe Konvention wie überall: 02:00 in einer Schicht ab 22:00 liegt
*nach* dem Beginn, nicht davor. Mit eigener Gegenprobe, damit die Rechnung nicht nur zufällig
stimmt.

**Zurückgewiesen statt gemeldet** werden zwei Fälle, weil sie gar keine Pause beschreiben: eine
Lage ohne Dauer, und eine Lage außerhalb des Blocks. Beides sind Tippfehler, keine Entscheidungen.

**Eine Lage je Block.** § 4 Satz 2 erlaubt, die Pause in Abschnitte von je mindestens fünfzehn
Minuten zu teilen — das wäre eine eigene Tabelle. Sie nicht abzubilden macht das Tool an dieser
Stelle **strenger, nicht laxer**: wer teilt, trägt die Lage des längsten Abschnitts ein und bekommt
eher eine Meldung als zu wenige. Das gehört gesagt, nicht verschwiegen.

**Der Verstoß blockiert einen Mitarbeitertausch** (`ARBZG_BLOCKERS`), wie die übrigen zwingenden
Regeln — aus demselben Grund wie in Etappe 8.

**Und genau dort habe ich die Lehre der Vorgängeretappe direkt wiederholt.** `perform_swap()`
reichte `break_minutes` weiter, `break_start` aber nicht — die Sperre stand in der Liste und griff
nie. Eine Sperre, die nie greift, ist schlimmer als keine, weil die Liste sie wie eine aussehen
lässt. Beim Nachprüfen gefunden, eine Etappe nachdem dieselbe Sache mit `break_minutes`
passiert war. **Was zum Platz gehört, reist ganz mit — und „ganz" heißt jedes Feld, nicht das
zuletzt hinzugefügte.**

## 3. § 9 / § 10 — fällt der Betrieb unter die Ausnahme

§ 9 Abs. 1 verbietet Sonn- und Feiertagsarbeit; § 10 nimmt ganze Branchen aus. Auf welcher Seite
ein Betrieb steht, ist eine Tatsache über den Betrieb, die nur er selbst nennen kann.

Bisher warnte das Tool bei **Feiertagen immer** und bei **Sonntagen nie** — beides falsch: die
erste Meldung ist für eine Klinik reines Rauschen, und die zweite fehlte ganz, obwohl § 9 Sonntage
genauso erfasst.

Neue Einstellung `sunday_work_permitted`. **Vorgabe: nicht ausgenommen**, weil das ist, was § 9
sagt, und weil ein Werkzeug, das die Ausnahme unterstellt, ausgerechnet bei der Regel schweigt,
die es beobachten soll.

**Was die Ausnahme ausdrücklich NICHT abschaltet** — der Punkt, den man übersieht:

| Bleibt in Kraft | Warum |
|---|---|
| Die fünfzehn freien Sonntage, § 11 Abs. 1 | Sie sind das Gegengewicht *zu* § 10 und gelten gerade dann, wenn er greift |
| Der Ersatzruhetag, § 11 Abs. 3 | Ebenso — er entsteht überhaupt erst durch erlaubte Sonntagsarbeit |

Eine Ausnahme, die beides mit abschaltete, machte aus einer Erlaubnis eine Freistellung. Dafür gibt
es einen eigenen Test: mit gesetzter Ausnahme und achtunddreißig gearbeiteten Sonntagen muss die
Budgetmeldung weiterhin kommen.

## 4. Tests

`backend/test_api_arbzg_rest.py` (17), dazu zwei in `ShiftCell.test.jsx` und der Rundlauf von
`0016_break_position` in SQLite und Postgres.

Die Gegenproben tragen auch hier: eine Umsetzung, die jede Pausenlage bemängelt, eine, die immer
meldet, und eine, die mit der Ausnahme alles abschaltet, wären ohne sie sämtlich grün.

## 5. Bewusst nicht dabei

- **Geteilte Pausen** nach § 4 Satz 2 (§2)
- **Eine automatische Pausenlage im Generator.** Der Blockplaner könnte eine mittige Lage setzen;
  das wäre aber eine Behauptung über den Betriebsablauf, und die Voreinstellung „keine Angabe" ist
  ehrlicher als eine erfundene
- **Die Liste der § 10-Ausnahmetatbestände als Auswahl.** Sie hat rund fünfzehn Nummern mit
  Untergliederungen, und welche greift, ist eine Rechtsfrage. Ein Kreuz und der Verweis auf die
  Norm sagen genau so viel, wie das Tool wissen kann
- **§ 11 Abs. 2** (Sonntagsarbeit in Verbindung mit dem Ruhetag) und **§ 12** (Ausgleich in
  Schichtbetrieben) — beide setzen Tarif- oder Betriebsvereinbarungen voraus, die das Tool nicht
  abbildet
