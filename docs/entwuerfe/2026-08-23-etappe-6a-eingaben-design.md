# Design: Etappe 6a — Eingaben, die durchrutschen

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Woher das kommt

Etappe 5 ist abgeschlossen. Was bleibt, sind die **zurückgestellten Befunde** aus neun Reviews —
im Handoff gesammelt, bewusst nicht behoben, weil sie neben der jeweiligen Etappe lagen.

Diese Etappe nimmt daraus die Teilmenge mit einer gemeinsamen Eigenschaft: **eine Eingabe
passiert die Prüfung und tut danach nichts.** Kein Fehler, keine Meldung, keine Spur im Log — die
Zeile steht in der Datenbank, sieht richtig aus und verliert jeden späteren Vergleich.

Das ist die schlechteste Fehlerart, die eine Anwendung haben kann: sie sieht wie Erfolg aus.

**Zuerst wurde geprüft, was von der Liste überhaupt noch stimmt.** Ein Befund
(`handleMonthChange` setzt den Plan nicht zurück) war längst behoben — die Liste ist stellenweise
veraltet, und ungeprüft danach zu arbeiten hieße, Vorhandenes zu „reparieren".

## 2. Der Datumsfehler, sechsmal

Seit Python 3.11 akzeptiert `date.fromisoformat()` auch das Basisformat `'20260901'`. Wer die
Funktion nur zur **Prüfung** aufruft und danach die rohe Zeichenkette speichert, legt eine Zeile
an, die nie zutrifft: das Tool vergleicht Datumsangaben durchgehend als Zeichenketten, und
`'2026-09-15' < '20260901'`, weil `-` vor `0` kommt.

Für `valid_from`/`valid_until` war das in Etappe 1 erkannt und behoben worden. **An sechs weiteren
Stellen nicht:**

| Stelle | Was still danebengeht |
|---|---|
| `unavailable_dates` | Ein gesperrter Tag sperrt nichts |
| `POST /absences` | Eine Krankmeldung macht keine Schicht frei |
| `DELETE /absences/<datum>` | Die Rücknahme findet die Zeile nicht |
| `PUT /shift-times` | Die abweichende Zeit gilt an keinem Tag |
| `POST /business-hours/exceptions` | Der Betrieb bleibt offen an dem Tag, den jemand geschlossen hat |
| `POST /slots` | Der Platz landet auf einem Datum, das der Plan nicht kennt |

**Ein Helfer statt sechs Flicken:** `parse_iso_date()` prüft *und* normalisiert und wirft einen
`ValueError` mit übersetzter Meldung. Die Fenstergrenzen aus Etappe 1 benutzen ihn jetzt auch —
sie hatten dieselbe Rechnung von Hand, mit einem achtzeiligen Kommentar davor.

**Die Gegenprobe gehört dazu:** normalisieren heißt nicht durchwinken. `'2026-02-30'` wird
weiterhin abgelehnt.

## 3. Die Grenze, die § 3 ArbZG zieht

`max_daily_hours` hatte keine Obergrenze. Das Feld nahm 12 an, und der Planer baute trotzdem
keinen Block über zehn Stunden — `MAX_BLOCK_MINUTES = 600` deckelt ihn.

Der Handoff notierte das als Widerspruch und schlug vor, den Deckel einstellbar zu machen. **Das
ist die falsche Richtung.** [§ 3 ArbZG](https://www.gesetze-im-internet.de/arbzg/__3.html): acht
Stunden werktäglich, auf höchstens zehn verlängerbar. Zehn ist die Grenze, nicht eine Vorgabe des
Planers. Ein Feld, das zwölf annimmt, verspricht etwas Rechtswidriges — und der Planer hat recht,
wenn er es nicht liefert.

Also: `0 < Wert <= 10`, mit einer Meldung, die den Paragraphen nennt.

**Null wird auch abgelehnt.** Es passierte die alte Prüfung („nicht negativ") und war keine
Arbeitszeitgrenze, sondern eine getarnte Deaktivierung: die Person konnte nie eingeplant werden,
und nichts sagte das.

**Nicht abgebildet:** § 7 (Tarifvertrag) und § 14 (Notfälle) erlauben Ausnahmen darüber hinaus.
Das Tool kennt sie nicht, und sie auf Vorrat einzubauen hieße, eine Rechtsgrundlage anzubieten,
die niemand verlangt hat.

## 4. Zwei Werte, die `int()` stillschweigend annimmt

`int(True)` ist `1`, `int(3.9)` ist `3`. An drei Stellen (`availability`, `business_hours`,
`coverage_requirements`) wurde der Wochentag so gelesen. Ein verirrter Wahrheitswert wird zum
Dienstag, ein Rundungsfehler eine Ebene höher zum Donnerstag — beides ergibt eine gültig
aussehende Zeile für einen Tag, den niemand genannt hat.

`parse_weekday()` lehnt beides ab.

**Das Nachprüfen hat gezeigt, dass das zu kurz griff.** Behoben waren die drei Stellen, für
die Tests geschrieben worden waren — nicht die Klasse. Dieselbe Schwäche stand noch in
`parse_int_list()` (`unavailable_weekdays`, `allowed_shift_types`) und in
`parse_optional_hours()`, wo `float(True)` eine Tagesgrenze von einer Stunde ergibt: innerhalb
jeder gültigen Spanne und deshalb stumm.

Die Behebung liegt jetzt in den **Parsern**, nicht an den Aufrufstellen. Eine Gegenprobe über ein
zweites Feld desselben Parsers (`weekly_hours`) hält das fest — und eine dritte, dass eine echte
`1` weiterhin durchgeht.

## 5. Ein 500er für einen Klientenfehler

Beim Schreiben der Tests selbst gestolpert: `PUT /employees/<id>/availability` ruft `.get()` auf
dem geparsten Rumpf auf. Ein JSON-**Array** parst einwandfrei und hat kein `.get` — das ergab
einen `AttributeError` und damit „der Server ist kaputt" für etwas, das der Aufrufer falsch
gemacht hat. Wer eine Integration gegen dieses Tool schreibt, sucht den Fehler dann an der
falschen Stelle.

Jetzt eine 400 mit einer Meldung, die sagt, was erwartet wird.

## 6. Was die Liste falsch anzeigte

Die Fenster-Abzeichen in der Mitarbeiterliste filterten nicht nach `valid_from`/`valid_until`. Ein
abgelaufenes Fenster las sich wie ein aktives — die Liste behauptete eine Verfügbarkeit, die der
Generator korrekt ignoriert.

Abgelaufene und noch nicht begonnene Fenster fallen jetzt weg. **Und sie bekommen einen eigenen
Hinweis:** „Kein Fenster gilt heute" statt „keine Fenster hinterlegt". Der Unterschied entscheidet,
ob jemand ein Fenster *anlegen* oder eine *Grenze ändern* muss — dieselbe Meldung für beides wäre
eine neue Irreführung an der Stelle der alten.

Das Datum wird über `toLocaleDateString('sv-SE')` gebildet, nicht über `toISOString()`: letzteres
liefert UTC und verschiebt für jeden östlich von Greenwich am Abend den Tag.

## 7. Tests

`backend/test_api_eingaben.py` (16) und `frontend/src/pages/Employees.test.jsx` (5).

Jeder Befund hat einen Test, der **vor** der Behebung rot war — dreizehn von sechzehn waren es. Dazu die
Gegenproben: ein unsinniges Datum bleibt abgelehnt, genau zehn Stunden gehen durch, und die beiden
Fenster-Meldungen dürfen nicht dieselbe werden.

**Zwei Bestandstests wurden angepasst.** Sie zeigten die Netto-Rechnung mit 12 und 13 Stunden —
Werte, die die neue Grenze nicht mehr zulässt. Ihre Aussage ist unverändert (Anwesenheit ist nicht
Arbeitszeit), die Zahlen liegen jetzt bei 9 und 10.

## 8. Bewusst nicht dabei

- **Die Leistungsbefunde** (`plan_day()` quadratisch, Fensterprüfung im innersten Schleifenkörper).
  Der Handoff sagt zu beiden „erst angehen, wenn der Benchmark es zeigt", und er zeigt es nicht
- **Überlappungs- und Eindeutigkeitsprüfung auf `employee_availability`.** Dasselbe Fenster
  zweimal ist doppelt gemeldet, aber nicht falsch — eine eigene Etappe wert, keine Zeile hier
- **Die Sperrbefunde am Anmeldeweg** (`is_locked_out`/`record_attempt` ohne Zeilensperre). Sie
  gehören zusammen betrachtet, nicht einzeln
- **Die Testschulden** (fester `10/9/11` in den Drosselungstests, ungepinntes `ortools`,
  Cache-Schlüssel in `ci.yml`, `Project Structure` im README). Eigene Etappe, keine Vermischung
  mit Verhaltensänderungen
