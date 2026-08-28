# Design: Etappe 6c — Der Rest der zurückgestellten Befunde

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Die letzten beiden Bündel: die Eindeutigkeit auf `employee_availability` und die Testschulden.
Danach ist die Liste bis auf die zwei Leistungsbefunde leer, die ihre eigene Notiz „erst angehen,
wenn der Benchmark es zeigt" tragen — und er zeigt es nicht.

**Wieder zuerst geprüft, was noch stimmt.** Von den Einträgen dieses Bündels waren **drei bereits
erledigt**, ohne dass es jemand notiert hätte:

| Notiert als offen | Tatsächlich |
|---|---|
| Die `end_time`-Hälfte der Zeitformat-Prüfung ist ungetestet | Getestet, in derselben Schleife wie `start_time` |
| Ungenutzte Konstante `ASSIGNMENT_TIMES_PY_PATH` | Wird benutzt |
| `Project Structure` listet `security.py`/`timeutil.py` nicht | Standen längst drin (in 6b nachgesehen) |

Drei von rund zwölf. Das ist der Grund, warum jede dieser Etappen mit einer Prüfung anfängt.

## 2. Dieselbe Eingabe, zwei Antworten

`PUT /assignments/<id>` und `PUT /schedules/<jahr>/<monat>/shift-times` nehmen beide ein
Zeitpaar. Die eine Route benutzt `parse_assignment_times()`, die andere hatte eine eigene, zweite
Prüfung — und die war bereits auseinandergelaufen:

- **Gleicher Beginn und gleiches Ende wurden angenommen.** `shift_duration_minutes()` liest
  `end <= start` als „läuft über Mitternacht"; aus `10:00`–`10:00` wird stillschweigend ein
  Vierundzwanzigstundendienst. Für die Zuweisung war genau das in Etappe 2 behoben worden
- **Eine halbe Zeitangabe hieß „Format falsch".** Die Zeit stimmte, es fehlte die andere Hälfte.
  Eine Meldung, die auf die falsche Stelle zeigt, kostet mehr Zeit als gar keine

Die Route benutzt jetzt denselben Parser. Eine zweite Prüfung derselben Sache zu pflegen ist die
Ursache, nicht der Fehler.

**Gegenprobe:** `end < start` bleibt erlaubt — das ist die Nachtschicht, nicht der Fehler.

**Das Review zu PR #28 hat einen Fehler gefunden, den genau dieser Umbau eingeführt hat.** Das
Formular schickt geleerte Felder als `""`, nicht als `null`. Vorher fielen sie auf die
Formatprüfung und ergaben eine verständliche 400; danach machte der Parser `None` daraus — aber
die Rücksetz-Prüfung stand *davor*, also fiel `""` in ein `INSERT` mit NULL-Zeiten, und die Spalte
ist `NOT NULL`. Ein 500er, wo vorher eine 400 stand.

**Die Lehre:** wer eine Prüfung durch eine andere ersetzt, verschiebt damit auch, *wann* Werte
normalisiert werden. Die Reihenfolge der Zweige dahinter ist Teil des Umbaus, nicht Umgebung.
Geparst wird jetzt vor der Rücksetz-Prüfung, mit Test und Gegenprobe für beide Schreibweisen.

## 3. Dasselbe Fenster zweimal

Zwei identische Arbeitszeitfenster wurden gespeichert und danach überall doppelt angezeigt. Der
Generator kommt damit zurecht (ein Platz passt, wenn er in *irgendein* Fenster passt), aber
niemand kann sehen, ob das Absicht war.

**Nur exakte Duplikate.** Zwei Fenster an einem Wochentag sind der geteilte Dienst und bleiben
erlaubt; **Überlappungen bleiben ebenfalls erlaubt**, weil sie zusammenzufassen hieße, eine
Eingabe stillschweigend umzuschreiben. Abgelehnt wird nur gleicher Wochentag *und* gleiche Zeiten
*und* gleiche Gültigkeitsgrenzen — eine Aussage, zweimal gemacht.

Die Gültigkeitsgrenzen gehören in den Vergleich: gleiche Zeiten mit verschiedenen Grenzen sind
zwei verschiedene Aussagen („bis März so, ab April wieder"). Eigene Gegenprobe.

**Nicht dabei: CHECK-Constraints auf der Tabelle.** Der Befund selbst sagt „wieder aufgreifen,
sobald ein zweiter Schreibpfad entsteht". Es gibt keinen; die API ist weiterhin der einzige.

## 4. Testschulden

| Was | Warum es zählt |
|---|---|
| `ortools` war ungepinnt | Alles andere ist exakt gepinnt, mit einem Kommentar, der genau erklärt warum. Dass es nur den Benchmark betrifft, ändert nichts: ein roter Lauf hält genauso auf, und die Ursache wäre eine Bibliothek, die niemand angefasst hat |
| Der CI-Cache-Schlüssel deckte nur `requirements-dev.txt` ab | Die Datei holt `requirements.txt` über `-r` herein. Nach einem Versionssprung dort bliebe der Cache stehen, und der Lauf benutzte die alte Bibliothek — grün, aber nicht das, was deployt wird |
| Der `0006`-Rundlauf prüfte nur `business_hours` | `up()` legt mit `CREATE TABLE IF NOT EXISTS` an, also verschwiege ein vergessenes `DROP TABLE` in `down()` keinen Fehler. Jetzt werden alle drei Tabellen geprüft |
| Zwei Validierungstests prüften nur den Status | Eine 400 aus einer ganz anderen Prüfung wäre ebenfalls grün gewesen |
| Der Entfernen-Knopf im Bedarfseditor hatte nur `title` | Er trägt ein bloßes „×"; ohne `aria-label` liest ein Screenreader genau das vor. Der Test findet ihn jetzt über `getByRole` — denselben Weg wie jemand, der ihn nicht sehen kann |

## 5. Bewusst nicht dabei

- **Die beiden Leistungsbefunde** (`plan_day()` quadratisch, die Fensterprüfung im innersten
  Schleifenkörper). Beide tragen die Notiz „erst angehen, wenn der Benchmark es zeigt"
- **`assignment_hours()` bei halb gefüllten Zeitpaaren.** Der Befund nennt es ein stilles
  Durchfallen; der Docstring nennt es ausdrücklich gewollt („ein Aufrufer, der alte oder von Hand
  bearbeitete Zeilen liest, soll einen prüfbaren Wert bekommen statt einer Ausnahme"). Ein
  dokumentiertes Verhalten gegen eine Notiz zu tauschen, die es nicht kannte, wäre keine Behebung
- **`MIGRATIONS_DIR.iterdir()` bei fehlendem Verzeichnis.** Es wirft einen `FileNotFoundError`
  mit dem vollen Pfad. Das ist ein klarer Abbruch beim Start einer kaputten Bereitstellung — die
  Alternative wäre, ihn zu verschlucken und ohne Migrationen weiterzulaufen
- **`ux_assignment_slot_v2` als Zugriffspfad** und die zwei Abfragen je Zeile in
  `constraint_warnings()`. Beides Leistung, beides ohne Messung
