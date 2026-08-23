# Datenbankwechsel am 07.09.2026

Die kostenlose Postgres-Instanz läuft ab. Die Entscheidung ist am 22.08.2026 gefallen: **die
Instanz darf ablaufen, die Datenbank wird neu aufgezogen** — kein bezahlter Plan, kein Umzug des
Bestands.

Dieses Blatt ist die Reihenfolge für den Tag, mit den Prüfungen dazwischen. Es ersetzt kein
Nachdenken, aber es nimmt die Fragen ab, die man um 22 Uhr nicht mehr stellen möchte.

---

## Vorher: was schon geprüft ist, und was nicht

| | Stand |
|---|---|
| Migrationen `0001`–`0017` auf einer **leeren** Datenbank | Läuft bei jedem CI-Lauf (`backend-postgres`) |
| Der **Bestandsweg** `0007` → `0017` auf gefüllten Tabellen | Geprobt, siehe `backend/test_migrations_bestand.py` |
| Der erste Tag: Konto, Schichtart, Bedarf, Plan | Geprüft, siehe `backend/test_api_tag_eins.py` |
| Die **neue Instanz selbst** | Liegt bei dir — Zugangsdaten fasst das Werkzeug nicht an |

**Das Backup steht auf Stand `0007`**, nicht auf dem heutigen. `schema_migrations` hat sieben
Zeilen. Wer es zurückspielt, lässt zehn Migrationen darüber laufen. Genau dieser Sprung ist
inzwischen geprobt — mit nachgebauten Daten derselben Form, nicht mit dem echten Dump.

---

## Der Ablauf

### 1. Neue Postgres-Instanz anlegen

In Render, gleicher Region wie der Webdienst.

**Nenne sie wieder `schichtplan-db`.** `render.yaml` verdrahtet `DATABASE_URL` über
`fromDatabase: name: schichtplan-db`; ein anderer Name bedeutet, dass du die Verdrahtung von Hand
nachziehen musst.

**Das Passwort ist neu und gehört nirgendwo sonst hin.** Das alte stand in einem früheren
Chatverlauf — es stirbt mit der Instanz, aber prüfe, ob du es anderswo verwendet hast.

### 2. `DATABASE_URL` zeigen lassen

Entweder über die Blueprint-Verdrahtung (wenn der Name stimmt) oder von Hand in den Umgebungs-
variablen des Webdienstes. **`PGSSLMODE` nicht setzen** — `db.py` verlangt ohne diese Variable von
sich aus `sslmode=require`, und das ist für eine gehostete Datenbank das Richtige.

### 3. Deploy auslösen

Die Anwendung wendet die Migrationen beim Start selbst an (`init_db()` beim Modulimport). Auf
einer leeren Datenbank laufen `0001`–`0017` durch; `0007_derive_coverage` findet nichts zum
Ableiten und tut nichts — das ist der Wächter in der Migration, kein Fehler.

**Im Deploy-Log erwarten:**

```
Migrationen angewandt: 0001_baseline, 0002_indexes, … , 0017_qualifications
```

Kommt die Zeile nicht, ist `DATABASE_URL` falsch oder die Instanz nicht erreichbar. Nicht
weitermachen.

### 4. Prüfen, dass sie steht

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://schichtplan-api.onrender.com/
```

200 erwartet. Und eine geschützte Route ohne Anmeldung:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://schichtplan-api.onrender.com/employees
```

401 erwartet — **nicht** 200 und nicht 500. Ein 500 heißt, die Datenbank antwortet nicht.

### 5. Den ersten Tag durchlaufen

Die Datenbank ist leer: kein Konto, keine Mitarbeiter, kein Bedarf.

1. **Erstes Konto anlegen.** Solange es keines gibt, ist `/register` offen — danach nicht mehr.
   Der erste Zugang ist damit der, der zuerst da ist; leg ihn sofort an.
2. **Bundesland setzen** (Öffnungszeiten → Feiertage). Ohne Angabe kennt das Werkzeug keinen
   Feiertag und schweigt dazu.
3. **§-10-Frage beantworten** (Öffnungszeiten → Sonn- und Feiertagsarbeit). Vorgabe ist „nicht
   ausgenommen": jede Sonntagsschicht wird dann gemeldet. Für eine Gaststätte oder Klinik ist das
   Rauschen — für einen Betrieb ohne Ausnahme ist es richtig.
4. **Aufbewahrungsfrist prüfen** (Öffnungszeiten → Datenschutz). Vorgabe sechs Monate.
5. **Mitarbeiter, Schichtarten, Bedarfsbänder** anlegen — in dieser Reihenfolge.
6. **Plan erzeugen.**

**Wenn der Plan leer bleibt**, sagt das Werkzeug jetzt warum: ohne Bedarfsband gibt es nichts zu
planen, und der Hinweis steht in der Meldung. Vor dieser Etappe blieb er stumm.

---

## Falls der Bestand doch gebraucht wird

Nicht der Plan, aber der Weg steht:

```bash
pg_restore --clean --no-owner --dbname="$NEUE_DBURL" schichtplan-2026-08-22.dump
```

Danach findet die Anwendung `0001`–`0007` als angewandt vor (`schema_migrations` ist Teil des
Dumps) und wendet beim nächsten Start `0008`–`0017` an. **Das ist der geprobte Sprung.** Was
dabei passiert:

- Jeder Mitarbeiter bekommt `max_daily_hours = 10` (§ 3 ArbZG)
- `shift_requirements` fällt weg; der Bedarf lebt in `coverage_requirements` weiter, abgeleitet
  von `0007`
- Jeder vorhandene Plan wird von `generated` auf **`published`** gehoben — er ist danach für
  Mitarbeiterkonten sichtbar. Wenn das nicht gewollt ist, vorher zurückziehen
- Vier Tabellen kommen leer dazu (Einstellungen, Protokoll, Tauschanträge, Nachweise)

Die Dump-Datei liegt unter `C:\Users\muham\schichtplan-2026-08-22.dump` und **enthält
Betriebsdaten im Klartext**.

**Sie liegt dort schlecht.** Der Ablageort wurde gewählt, weil er außerhalb des
Projektverzeichnisses liegt — aber `C:\Users\muham` ist selbst ein Git-Repository, und die Datei
steht dort unversioniert mitten drin. Ein unbedachtes `git add -A` sammelt sie ein, und ein Dump
mit Namen und zweiundsechzig Schichten ist aus einer Historie schwer wieder herauszubekommen.

**Vor dem Wechsel:** verschiebe sie an einen Ort, der in keinem Arbeitsverzeichnis liegt — oder
lösche sie, sobald die neue Datenbank steht und ein frisches Backup existiert.

---

## Was danach noch offen bleibt

- **Die IP-Freigabe** der neuen Instanz, falls du sie einschränken willst
- **Ein neues Backup**, sobald wieder echte Daten drin sind. Der Befehl steht im README unter
  *Operations*
- **Das alte Backup aufheben oder löschen** — es ist ab dem Wechsel Bestand ohne Zweck, und es
  enthält Namen
