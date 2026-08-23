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

### 1. Sichern, **bevor** die Instanz abläuft

Der wichtigste Schritt, und der einzige mit einer Frist. Eine abgelaufene Instanz lässt sich
nicht mehr auslesen.

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_dump" "$DATABASE_URL" \
  --no-owner --format=custom \
  --file="schichtplan-$(date +%Y-%m-%d).dump"
```

Prüfen, dass wirklich etwas drin ist:

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_restore" --list schichtplan-*.dump | grep -c "TABLE DATA"
```

**Die Datei enthält Betriebsdaten im Klartext** — Namen, Schichten, Krankmeldungen. Sie gehört an
einen Ort, der in **keinem** Git-Arbeitsverzeichnis liegt. `C:\Users\muham` ist selbst eines; ein
unbedachtes `git add -A` sammelt sie dort ein, und aus einer Historie ist sie schwer wieder
herauszubekommen.

### 2. Neue Instanz anlegen

In Render, gleiche Region wie der Webdienst.

**Nenne sie wieder `schichtplan-db`.** `render.yaml` verdrahtet `DATABASE_URL` über
`fromDatabase: name: schichtplan-db`; ein anderer Name heißt, die Verdrahtung von Hand
nachzuziehen.

**Das Passwort ist neu und gehört nirgendwo sonst hin.**

### 3. `DATABASE_URL` zeigen lassen

Über die Blueprint-Verdrahtung (wenn der Name stimmt) oder von Hand in den Umgebungsvariablen des
Webdienstes. **`PGSSLMODE` nicht setzen** — `db.py` verlangt ohne diese Variable von sich aus
`sslmode=require`, und das ist für eine gehostete Datenbank das Richtige.

### 4. Deploy auslösen und prüfen

Die Anwendung wendet die Migrationen beim Start selbst an. Danach:

```bash
curl -s https://schichtplan-api.onrender.com/health
```

Erwartet:

```json
{"status":"ok","database":"ok","migrations":{"applied":17,"latest":"0017_qualifications"}}
```

**Diese eine Abfrage beantwortet beide Fragen**: kommt die Datenbank an, und welcher Stand liegt
dort. Ein **503** mit `"database":"unreachable"` heißt, `DATABASE_URL` zeigt auf nichts
Erreichbares — dann nicht weitermachen, sondern Schritt 3 prüfen.

`healthCheckPath` in `render.yaml` zeigt ebenfalls hierher, damit Render einen Dienst ohne
Datenbank nicht für gesund hält.

### 5. Zurückspielen — oder bewusst neu anfangen

**Mit Bestand** (der Weg, der § 16 erfüllt):

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_restore" --clean --no-owner \
  --dbname="$NEUE_DBURL" schichtplan-2026-09-06.dump
```

Danach findet die Anwendung die Migrationen des Dumps als angewandt vor und wendet beim nächsten
Start nur noch die neueren an. Solange Sicherung und Rückspielen im selben Zyklus liegen, gibt es
keine — der Stand ist derselbe. Der Sprung über zehn Migrationen ist trotzdem geprobt, weil der
Dump vom 22.08.2026 auf einem älteren Stand steht (siehe Schritt 0).

**Ohne Bestand**: nichts tun, mit Schritt 6 weitermachen. Der bisherige Plan ist dann fort.

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

- **Datum notieren.** Dreißig Tage ab Schritt 2, und das Sichern gehört ein paar Tage davor.
- **Die alte Dump-Datei** ist nach erfolgreichem Rückspielen Bestand ohne Zweck und enthält
  Namen. Löschen oder bewusst archivieren, nicht liegen lassen.
- **Die IP-Freigabe** der neuen Instanz, falls sie eingeschränkt werden soll.

---

## Wenn etwas schiefgeht

| Symptom | Wahrscheinlich |
|---|---|
| `/health` antwortet 503, `database: unreachable` | `DATABASE_URL` falsch, Instanz noch nicht bereit, oder `PGSSLMODE` gesetzt |
| `/health` antwortet gar nicht | Der Dienst startet nicht — das Deploy-Log lesen, dort steht der Migrationsfehler |
| `applied` kleiner als erwartet | Migrationen nur teilweise angewandt; jede läuft in eigener Transaktion, die fehlgeschlagene steht im Log |
| Plan leer nach dem Rückspielen | Rückspielen lief gegen die falsche Datenbank; `/health` zeigt den Stand, `GET /schedules/<jahr>/<monat>` den Inhalt |
| `pg_dump: command not found` | Kein fehlendes Programm, sondern ein fehlender Pfad — siehe Schritt 0 |
