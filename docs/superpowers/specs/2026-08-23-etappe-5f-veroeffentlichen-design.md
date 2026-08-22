# Design: Etappe 5f — Veröffentlichen-Workflow

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §10, Etappe 5
**Status:** Entwurf

---

## 1. Ziel

`schedules.status` gibt es seit dem ersten Tag. Er wird beim Erzeugen auf `'generated'` gesetzt,
in die Antwort geschrieben — und von nichts gelesen. **Jeder Plan ist sichtbar, sobald er
erzeugt wurde**, auch der halbfertige, den HR gerade zum dritten Mal umbaut.

Diese Etappe macht daraus einen Zustand mit Bedeutung: ein Plan ist **Entwurf** oder
**veröffentlicht**, und erst der veröffentlichte ist für Mitarbeiter da.

## 2. Der Zustand

Zwei Werte statt des einen bisherigen:

| Wert | Bedeutung |
|---|---|
| `draft` | Erzeugt, aber nicht freigegeben. Nur HR sieht ihn |
| `published` | Freigegeben. Mitarbeiter sehen ihre eigenen Schichten |

**Migration `0012`** setzt alle bestehenden `'generated'` auf `'published'`. Das ist die
entscheidende Richtung: eine Migration darf nicht ändern, was Leute gestern sehen konnten.
Würde sie auf `draft` setzen, verschwänden alle laufenden Pläne bis jemand sie einzeln
freigibt — und niemand wüsste warum.

## 3. Die Übergänge

| Ereignis | Wirkung |
|---|---|
| Erzeugen | `draft`. Auch beim Neuerzeugen eines veröffentlichten Plans |
| Veröffentlichen | `published`, mit Zeitstempel |
| Zurückziehen | `draft` |
| Handkorrektur | **Keine.** Ein veröffentlichter Plan bleibt veröffentlicht |

**Warum das Neuerzeugen zurück auf Entwurf setzt:** der Plan, den HR freigegeben hat, ist danach
nicht mehr derselbe. Er verwirft ohnehin alle Handkorrekturen und verlangt dafür schon heute
eine Rückfrage. Ihn stillschweigend veröffentlicht zu lassen hieße, den Mitarbeitern einen
anderen Plan unterzuschieben als den, den sie gesehen haben. Die Antwort sagt es ausdrücklich,
damit HR nicht rätselt, warum der Plan wieder verschwunden ist.

**Warum die Handkorrektur nichts ändert:** eine Zuweisung zu tauschen ist der Normalfall im
laufenden Betrieb, kein neuer Plan. Jede Korrektur zum Zurückziehen zu zwingen machte das
Veröffentlichen unbenutzbar.

## 4. Was Mitarbeiter sehen

Ein Entwurf ist für sie **nicht vorhanden**: `404` — aber mit einer eigenen Meldung
(„noch nicht veröffentlicht") statt der bisherigen („noch kein Plan erzeugt"). Der Unterschied
ist der ganze Punkt: „es gibt nichts" und „es ist noch nicht so weit" sind zwei verschiedene
Auskünfte.

Die Oberfläche verschluckt heute die Meldung eines `404` und zeigt ihren eigenen Text. Das
ändert sich: liegt eine Meldung vom Server vor, wird sie gezeigt.

**HR sieht Entwürfe normal**, mit einer Kennzeichnung und dem Knopf zum Veröffentlichen.

## 5. Datenmodell

**Migration `0012_publish_state`:**

```
schedules + published_at TIMESTAMP NULL
UPDATE schedules SET status = 'published' WHERE status = 'generated'
```

`published_at` ist die Antwort auf „seit wann sehen die Leute das?" — eine Frage, die bei einem
Streit über den Dienstplan zuerst kommt. `NULL` bei einem Entwurf.

Kein `CHECK` auf `status`: das Projekt hat auf keiner Tabelle welche, die API ist der einzige
Schreiber, und ein `CHECK` auf SQLite später zu ändern ist unangenehm (Fallstrick 3 in
Verwandtschaft). Die erlaubten Werte stehen an einer Stelle im Code.

## 6. API

| Methode | Route | Zweck |
|---|---|---|
| PUT | `/schedules/<year>/<month>/status` | `{status: 'published'\|'draft'}` (HR) |

Ein unbekannter Wert ist `400`. Denselben Zustand noch einmal zu setzen ist **kein** Fehler —
das ist idempotent und erspart dem Aufrufer eine Fallunterscheidung; `published_at` bleibt beim
erneuten Veröffentlichen stehen, statt sich zu erneuern.

`GET /schedules/<year>/<month>` liefert `status` (das tut es schon) und neu `published_at`.

`POST /schedules/generate` gibt in seiner Antwort mit, dass der Plan wieder Entwurf ist.

## 7. Frontend

- Ein Zustandsabzeichen neben dem Monat: Entwurf oder veröffentlicht seit …
- Ein Knopf zum Veröffentlichen bzw. Zurückziehen. Das Zurückziehen fragt nach — es nimmt
  allen die Sicht auf ihren Plan
- Der leere Zustand zeigt die Servermeldung, wenn es eine gibt

## 8. Tests

| Ebene | Was |
|---|---|
| `test_migrations.py` / `_postgres.py` | Rundlauf `0012`; **ein Bestandsplan mit `'generated'` wird `'published'`** — die Richtung, auf die es ankommt |
| API | Erzeugen ergibt `draft`; Veröffentlichen setzt `published` und `published_at`; erneutes Veröffentlichen ändert den Zeitstempel nicht; Zurückziehen; unbekannter Wert ist 400 |
| API | **Der Kern:** ein Mitarbeiter bekommt beim Entwurf 404 mit der eigenen Meldung, beim veröffentlichten Plan seine Schichten. HR sieht beides |
| API | Neuerzeugen eines veröffentlichten Plans setzt ihn auf `draft` zurück; eine Handkorrektur tut das **nicht** (Gegenprobe) |
| Frontend | Abzeichen und Knopf; der leere Zustand zeigt die Servermeldung |

## 9. Bewusst nicht dabei

- **Benachrichtigung beim Veröffentlichen.** Naheliegend, aber ein eigenes Thema mit eigenen
  Fragen (wer, worüber, wie oft). `mailer.py` gibt es, der Rest nicht
- **Versionierung veröffentlichter Pläne.** Wer wissen will, was am 3. stand, braucht das
  Audit-Log — das ist der nächste Teil
- **Ein Freigabe-Vieraugenprinzip.** Es gibt nur eine HR-Rolle
- **`CHECK`-Constraint auf `status`** (§5)

## 10. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Bestandspläne verschwinden für Mitarbeiter | Die Migration setzt sie auf `published`, mit eigenem Test (§8) |
| HR erzeugt neu und wundert sich, dass der Plan weg ist | Der Zustand steht sichtbar im Kopf der Seite, und die Antwort des Erzeugens sagt es |
| Ein Mitarbeiter liest „kein Plan" statt „noch nicht veröffentlicht" | Eigene Meldung, und die Oberfläche zeigt sie (§4) |
