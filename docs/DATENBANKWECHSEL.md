# Der Datenbankzyklus

Die kostenlose Postgres-Instanz bei Render läuft nach **30 Tagen** ab. Die Entscheidung des
Betreibers: ablaufen lassen und eine neue aufziehen. Das ist damit **kein Termin, sondern ein
Zyklus** — er wiederholt sich, solange der freie Plan der Plan bleibt.

Dieses Blatt ist die Reihenfolge für einen Durchlauf. Der erste fällt auf den **07.09.2026**.

---

## Die Folge, die man einmal gelesen haben muss

**Eine Datenbank, die alle 30 Tage neu anfängt, hält keine Arbeitszeitnachweise.**

[§ 16 Abs. 2 ArbZG](https://www.gesetze-im-internet.de/arbzg/__16.html) verlangt, Nachweise über
die acht Stunden hinausgehende Arbeitszeit **mindestens zwei Jahre** aufzubewahren. Das ganze
Werkzeug ist darauf ausgelegt: die Aufbewahrungsfrist nimmt Zuweisungen ausdrücklich aus, und
Löschen anonymisiert statt zu löschen, damit die Aufzeichnung ganz bleibt.

Ein Zyklus ohne Rückspielen macht das zunichte — nicht als Fehler des Werkzeugs, sondern als
Folge der Betriebsentscheidung. **Es gibt genau zwei Wege, die das auflösen:**

1. **Jeden Zyklus sichern und zurückspielen** (Schritt 1 und 5). Dann wächst der Bestand über die
   Zyklen hinweg weiter, und die zwei Jahre sind erreichbar.
2. **Einen bezahlten Plan nehmen.** Kostet Geld und spart diesen Zettel.

Was nicht funktioniert: den Zyklus fahren und das Sichern auslassen. Nach zwei Monaten gibt es
den ersten Monat nicht mehr, und keine Nachträglichkeit holt ihn zurück.

Das ist eine Feststellung, keine Empfehlung — welcher Weg richtig ist, hängt davon ab, ob das
Werkzeug echte Dienstpläne trägt oder noch erprobt wird.

---

## Der Durchlauf

**Die Reihenfolge ist der Punkt.** Zurückgespielt wird, *bevor* die Anwendung auf die neue
Instanz zeigt — sonst läuft sie eine Weile gegen eine leere Datenbank, jemand legt dort das erste
Konto an, und das anschließende `pg_restore --clean` wischt es wieder weg. Und die alte Instanz
wird erst gesichert, wenn niemand mehr hineinschreibt.

### 0. Vorher wissen

| | Stand |
|---|---|
| Migrationen auf einer **leeren** Datenbank | Läuft bei jedem CI-Lauf (`backend-postgres`) |
| Der **Bestandsweg** über zehn Migrationen auf gefüllten Tabellen | Geprobt, `backend/test_migrations_bestand.py` |
| Der erste Tag: Konto, Schichtart, Bedarf, Plan | Geprüft, `backend/test_api_tag_eins.py` |
| Die Instanz selbst, Passwort, IP-Freigabe | Liegt beim Betreiber — Zugangsdaten fasst das Werkzeug nicht an |

**`pg_dump` und `pg_restore` sind nicht im PATH.** Sie liegen unter
`C:\Program Files\PostgreSQL\18\bin\`; die Befehle unten nennen deshalb den vollen Pfad. Ohne ihn
antwortet die Eingabeaufforderung nur mit „Befehl nicht gefunden", und das sieht aus wie ein
fehlendes Programm statt wie ein fehlender Pfad.

Für den ganzen Durchlauf einmal festlegen:

```bash
DUMP="$HOME/sicherungen/schichtplan-$(date +%Y-%m-%d).dump"
PGBIN="/c/Program Files/PostgreSQL/18/bin"
ALT_DBURL="…"      # die noch laufende Instanz
```

`$DUMP` wird unten überall benutzt, damit nicht gesichert und danach eine andere Datei
zurückgespielt wird. **Der Ordner gehört an einen Ort, der in keinem Git-Arbeitsverzeichnis
liegt** — `C:\Users\muham` ist selbst eines, und ein unbedachtes `git add -A` sammelt die Datei
dort ein.

### 1. Neue Instanz anlegen — **solange die alte noch läuft**

Beide existieren dann eine Weile nebeneinander, und genau das ist gewollt: Sichern und
Zurückspielen brauchen beide gleichzeitig. Wer wartet, bis die alte abgelaufen ist, hat nichts
mehr zu sichern.

In Render, gleiche Region wie der Webdienst. **Nenne sie wieder `schichtplan-db`** —
`render.yaml` verdrahtet `DATABASE_URL` über `fromDatabase: name: schichtplan-db`; ein anderer
Name heißt, die Verdrahtung von Hand nachzuziehen.

**Das Passwort ist neu und gehört nirgendwo sonst hin.** Die Verbindungszeichenkette der neuen
Instanz für die folgenden Schritte:

```bash
NEU_DBURL="…"      # aus dem Render-Dashboard der neuen Instanz
```

### 2. Schreiben beenden, dann sichern

Der Schritt mit der Frist. Eine abgelaufene Instanz lässt sich nicht mehr auslesen.

**Erst dafür sorgen, dass niemand mehr schreibt** — Absprache genügt, das Werkzeug hat keinen
Wartungsmodus. Was nach dem Dump noch eingetragen wird, ist danach fort, und niemand merkt es.

```bash
mkdir -p "$(dirname "$DUMP")"
"$PGBIN/pg_dump" "$ALT_DBURL" --no-owner --format=custom --file="$DUMP"
```

Prüfen, dass wirklich etwas drin ist:

```bash
"$PGBIN/pg_restore" --list "$DUMP" | grep -c "TABLE DATA"
```

Null Treffer heißt: leerer Dump. Dann nicht weitermachen.

### 3. Zurückspielen — oder bewusst neu anfangen

**Mit Bestand** (der Weg, der § 16 erfüllt), und zwar **bevor** die Anwendung die neue Instanz
sieht:

```bash
"$PGBIN/pg_restore" --clean --no-owner --dbname="$NEU_DBURL" "$DUMP"
```

Die Anwendung findet die Migrationen des Dumps danach als angewandt vor und wendet beim nächsten
Start nur noch die neueren an. Liegen Sicherung und Rückspielen im selben Zyklus, gibt es keine —
der Stand ist derselbe. Der Sprung über zehn Migrationen ist trotzdem geprobt, weil der Dump vom
22.08.2026 auf einem älteren Stand steht (siehe Schritt 0).

**Ohne Bestand**: diesen Schritt auslassen. Der bisherige Plan ist dann fort — siehe den
Abschnitt oben, warum das eine Entscheidung mit rechtlicher Folge ist.

### 4. `DATABASE_URL` umbiegen und deployen

Über die Blueprint-Verdrahtung (wenn der Name stimmt) oder von Hand in den Umgebungsvariablen des
Webdienstes. **`PGSSLMODE` nicht setzen** — `db.py` verlangt ohne diese Variable von sich aus
`sslmode=require`, und das ist für eine gehostete Datenbank das Richtige.

### 5. Prüfen

```bash
curl -s https://schichtplan-api.onrender.com/health
```

Erwartet:

```json
{"status":"ok","database":"ok","migrations":{"applied":17,"latest":"0017_qualifications"}}
```

**Diese eine Abfrage beantwortet beide Fragen**: kommt die Datenbank an, und welcher Stand liegt
dort.

Kommt ein **503** mit `"database":"unreachable"`, sagt das nur: die Anwendung erreicht die
Datenbank nicht. Es unterscheidet **nicht** zwischen einer neuen Instanz, die noch hochfährt,
einer falschen `DATABASE_URL`, einer gesetzten `PGSSLMODE` und einem Netzproblem. Erst ein paar
Minuten geben, dann Schritt 4 prüfen, dann das Deploy-Log lesen.

`healthCheckPath` in `render.yaml` zeigt ebenfalls hierher, damit Render einen Dienst ohne
Datenbank nicht für gesund hält.

Mit zurückgespieltem Bestand zusätzlich prüfen, dass der Inhalt da ist — `/health` sagt darüber
nichts:

```bash
curl -s -H "Authorization: Bearer …" \
  https://schichtplan-api.onrender.com/schedules/2026/8 | head -c 200
```

### 6. Nur beim Neuanfang: einrichten

Die Datenbank ist leer. Das Werkzeug sagt selbst, was fehlt — die Planseite zeigt es, solange
etwas fehlt (siehe `GET /setup-status`).

1. **Erstes Konto anlegen.** Solange es keines gibt, ist `/register` offen; danach nicht mehr.
   Der erste Zugang ist der, der zuerst da ist — leg ihn sofort an.
2. **Bundesland** setzen (Öffnungszeiten → Feiertage).
3. **§-10-Frage** beantworten (Öffnungszeiten → Sonn- und Feiertagsarbeit). Vorgabe ist „nicht
   ausgenommen": jede Sonntagsschicht wird dann gemeldet.
4. **Aufbewahrungsfrist** prüfen (Öffnungszeiten → Datenschutz). Vorgabe sechs Monate.
5. **Mitarbeiter, Schichtarten, Bedarfsbänder** — in dieser Reihenfolge.
6. **Plan erzeugen.**

### 7. Für den nächsten Zyklus

- **Datum notieren.** Dreißig Tage ab Schritt 1, und Schritt 2 gehört ein paar Tage davor.
- **Die alte Instanz** kann jetzt ablaufen. Nichts weiter zu tun.
- **Die alte Dump-Datei** ist nach erfolgreichem Rückspielen Bestand ohne Zweck und enthält
  Namen. Löschen oder bewusst archivieren, nicht liegen lassen.
- **Die IP-Freigabe** der neuen Instanz, falls sie eingeschränkt werden soll.

---

## Wenn etwas schiefgeht

| Symptom | Wahrscheinlich |
|---|---|
| `/health` antwortet 503, `database: unreachable` | Die Anwendung erreicht die Datenbank nicht — mehr sagt die Meldung nicht. Instanz fährt noch hoch, `DATABASE_URL` falsch, `PGSSLMODE` gesetzt oder ein Netzproblem |
| `/health` antwortet gar nicht | Der Dienst startet nicht — das Deploy-Log lesen, dort steht der Migrationsfehler |
| `applied` kleiner als erwartet | Migrationen nur teilweise angewandt; jede läuft in eigener Transaktion, die fehlgeschlagene steht im Log |
| Plan leer nach dem Rückspielen | Rückspielen lief gegen die falsche Datenbank; `/health` zeigt den Stand, `GET /schedules/<jahr>/<monat>` den Inhalt |
| `pg_dump: command not found` | Kein fehlendes Programm, sondern ein fehlender Pfad — siehe Schritt 0 |
| Nichts mehr zu sichern | Die alte Instanz war schon abgelaufen. Schritt 1 gehört vor ihr Ende, nicht danach |
