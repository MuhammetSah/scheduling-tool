# Design: Etappe 5g — Audit-Log

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §8.1, §10
**Status:** Entwurf

---

## 1. Ziel

Das Tool weiß nicht, wer etwas geändert hat. `published_at` beantwortet seit 5f, *seit wann*
ein Plan sichtbar ist — aber nicht, wer ihn freigegeben hat, wer die Zuweisung am 3. getauscht
hat und wann. Bei einem Streit über den Dienstplan ist das die zweite Frage nach „seit wann",
und heute gibt es keine Antwort.

Die Design-Spec nennt `login_attempts` „den ersten Baustein für das Audit-Log aus Etappe 5".
Das hier ist der zweite.

## 2. Die Weiche: Anfrage oder Fachlichkeit

Zwei Bauarten stehen zur Wahl, und die Entscheidung prägt alles Weitere.

**Fachlich.** Jede bedeutsame Aktion meldet sich selbst: „Anna auf Frühschicht am 03.03.
gesetzt", „Bedarfsband Montag geändert". Lesbar wie ein Tagebuch — aber der Code verteilt sich
über gut zwei Dutzend Aufrufstellen, jede neue Route muss daran denken, und **die Details
enthalten Art.-9-Daten**: eine Krankmeldung ist eine Gesundheitsangabe, und sie ein zweites Mal
in eine Protokolltabelle zu schreiben ist eine datenschutzrechtliche Entscheidung, keine
technische.

**Auf Anfrageebene.** Ein `after_request`-Haken protokolliert jede verändernde Anfrage: wer,
wann, welche Methode, welcher Pfad, welcher Status. Eine Stelle, lückenlos per Konstruktion,
keine vergessene Route — und **ohne Anfrageinhalte**, also ohne das Art.-9-Problem.

**Gebaut wird die zweite.** Sie beantwortet die Frage, die wirklich gestellt wird — *wer hat
diese Zuweisung angefasst und wann* —, ohne eine Entscheidung vorwegzunehmen, die dem Nutzer
gehört. Was sie nicht beantwortet, ist *worauf* etwas geändert wurde; das steht ausdrücklich
unter „nicht dabei" und ist der Preis.

## 3. Was protokolliert wird

Jede Anfrage mit einer anderen Methode als `GET`, `HEAD` oder `OPTIONS`.

| Spalte | Inhalt |
|---|---|
| `at` | Zeitstempel |
| `user_id` | Wer, oder `NULL` bei einer nicht angemeldeten Anfrage |
| `username` | **Mitgeschrieben, nicht verknüpft** — siehe §4 |
| `method`, `path` | `PUT`, `/assignments/17` |
| `status` | Der HTTP-Status der Antwort |

**Auch fehlgeschlagene Anfragen.** Ein abgewiesener Versuch, den Plan zu ändern, ist für ein
Protokoll mindestens so interessant wie ein gelungener — und ein Log, das nur Erfolge kennt,
verschweigt genau die Fälle, wegen derer man hineinsieht.

**Nicht protokolliert:** `POST /login` und `POST /invitations/<token>`. Sie tragen Passwörter im
Rumpf; der Pfad selbst ist harmlos, aber `login_attempts` deckt sie ohnehin ab und ist der
dafür gebaute Ort. Zwei Protokolle über denselben Vorgang wären eines zu viel.

## 4. Warum der Benutzername mitgeschrieben und nicht verknüpft wird

Ein Fremdschlüssel auf `users` wäre die saubere Normalform — und genau falsch. Konten werden
gelöscht (`DELETE /accounts/<id>` gibt es), und mit `ON DELETE CASCADE` verschwände das
Protokoll mit; ohne läge eine tote Referenz da. Ein Protokoll, dessen Einträge sich löschen
lassen, indem man das Konto löscht, ist kein Protokoll.

`user_id` bleibt als Zahl stehen, ohne Fremdschlüssel, damit man zusammenhängende Einträge
findet. Der Name daneben ist die Kopie, die den Vorgang lesbar hält.

**Das ist zugleich ein DSGVO-Thema**, kein gelöstes: ein Protokoll über benannte Personen ist
personenbezogen und braucht eine Aufbewahrungsfrist. Die festzulegen ist Sache des Nutzers und
gehört zum DSGVO-Teil, nicht hierher. Der Abschnitt „Offen" im Handoff hält es fest.

## 5. Datenmodell

**Migration `0013_audit_log`:**

```
audit_log(id, at TIMESTAMP, user_id INTEGER, username TEXT, method TEXT,
          path TEXT, status INTEGER)
INDEX ix_audit_log_at ON audit_log(at)
```

`id` ist Pflicht, nicht Zierde — Fallstrick 16.

Kein Fremdschlüssel auf `users` (§4). Der Index liegt auf `at`, weil jede Abfrage „die letzten
N" lautet.

## 6. Wie der Haken sich verhält

Ein `after_request`-Haken, der **niemals die Anfrage kippen darf**. Ein Protokoll, das eine
sonst erfolgreiche Änderung zu einem `500` macht, ist schlimmer als kein Protokoll — es fällt
zuerst dann aus, wenn ohnehin etwas klemmt. Der Schreibvorgang läuft deshalb in einem
`try/except`, das den Fehlschlag ins Anwendungslog schreibt und die Antwort durchlässt.

Er schreibt **nach** dem eigentlichen Vorgang und mit eigenem `commit`. Damit steht ein Eintrag
auch dann, wenn die Anfrage selbst zurückgerollt wurde — was richtig ist: der Versuch hat
stattgefunden.

## 7. API

| Methode | Route | Zweck |
|---|---|---|
| GET | `/audit-log` | Die letzten Einträge, neueste zuerst (HR). `?limit=` bis 500, Standard 100 |

Nur lesen. Es gibt bewusst keine Route zum Löschen: was sich per Knopfdruck leeren lässt, ist
kein Protokoll. Die Aufbewahrung kommt mit dem DSGVO-Teil und dann als Frist, nicht als
Schaltfläche.

## 8. Frontend

Eine Seite unter den Konten, HR-only: Zeitpunkt, Benutzer, Methode, Pfad, Status. Bewusst roh —
sie ist ein Nachschlagewerk, keine Erzählung, und alles Hübschere täuschte eine Fachlichkeit
vor, die die Einträge nicht haben.

## 9. Tests

| Ebene | Was |
|---|---|
| `test_migrations.py` / `_postgres.py` | Rundlauf `0013`; Schreibtest gegen Postgres (Fallstrick 16) |
| API | Eine `PUT`-Anfrage erzeugt genau einen Eintrag mit Benutzer, Pfad und Status |
| API | **Gegenprobe:** ein `GET` erzeugt keinen |
| API | Eine **fehlgeschlagene** Anfrage (403, 400) wird ebenfalls protokolliert |
| API | `POST /login` wird nicht protokolliert |
| API | Der Eintrag überlebt das Löschen des Kontos, das ihn erzeugt hat — der Kern von §4 |
| API | `/audit-log` ist HR-only; `limit` wird gedeckelt |
| API | Ein Fehlschlag beim Schreiben kippt die Anfrage nicht (§6) |

## 10. Bewusst nicht dabei

- **Was inhaltlich geändert wurde** (§2). Der Preis der Anfrageebene, und die Alternative
  verlangt eine DSGVO-Entscheidung, die nicht hier fällt
- **Anfrage- oder Antwortrümpfe** — dieselbe Begründung
- **Eine Aufbewahrungsfrist.** Gehört zum DSGVO-Teil (§4)
- **Löschen über die API** (§7)
- **IP-Adressen.** `login_attempts` führt sie für die Drosselung; für ein Änderungsprotokoll
  sind sie zusätzliches personenbezogenes Datum ohne zusätzliche Aussage

## 11. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Das Protokoll kippt eine Anfrage | `try/except` um den Schreibvorgang, mit eigenem Test (§6, §9) |
| Die Tabelle wächst unbegrenzt | Real, und bewusst offen: die Frist ist eine Entscheidung des Nutzers. Bei dieser Größenordnung — ein Betrieb, wenige Schreibzugriffe am Tag — ist es Jahre hin unkritisch, aber es steht im Handoff |
| Einträge verschwinden mit dem Konto | Kein Fremdschlüssel, Name mitgeschrieben, eigener Test (§4, §9) |
