# Design: Etappe 5a — Ruhepausen und Netto-Arbeitszeit

**Datum:** 2026-08-22
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §10, Etappe 5
**Vorgänger:** [`2026-08-22-etappe-4-zuschnitt-design.md`](2026-08-22-etappe-4-zuschnitt-design.md) §3
**Status:** Entwurf, mit dem Nutzer abgestimmt

---

## 1. Warum das hier eine eigene Spec ist

Die Roadmap führt „Etappe 5 — restliche Produktionsreife" als einen Punkt. Das ist ein
Sammelbegriff, kein Vorhaben: `shift_requirements` entfernen, Veröffentlichen-Workflow,
Audit-Log, Exporte, DSGVO und das Arbeitszeitrecht sind sechs unabhängige Dinge.

Auch das Arbeitszeitrecht allein zerfällt in drei:

| Teil | Inhalt | Hängt ab von |
|---|---|---|
| **5a** (dieses Dokument) | Ruhepausen nach § 4, Arbeitszeit netto statt brutto | — |
| **5b** | Sonn- und Feiertagsruhe: Feiertagskalender mit Bundesland, 15 freie Sonntage, Ersatzruhetag, höchstens sechs Tage in Folge | — |
| **5c** | Achtstundenschnitt nach § 3 Satz 2, rollierend über 24 Wochen, gemeldet statt erzwungen | **5a** |

5a kommt zuerst, weil es festlegt, was „Arbeitszeit" im Tool überhaupt bedeutet. 5c rechnet
darauf. 5b ist unabhängig.

## 2. Ziel

Etappe 4 hat drei Regeln des Arbeitszeitgesetzes umgesetzt und drei ausdrücklich offengelassen.
Eine davon ist § 4 — und sie ist die unangenehmste, weil das Tool heute stillschweigend Pläne
erzeugt, die so nicht zulässig sind: ein durchgehender Achtstundenblock verstößt gegen § 4
Satz 3, und die Tagesarbeitszeit wird brutto gerechnet, obwohl § 2 Abs. 1 sie ohne die
Ruhepausen definiert.

Nach dieser Etappe kennt das Tool Ruhepausen, rechnet Arbeitszeit netto, und die Grenzen aus
Etappe 1 (`weekly_hours`) und Etappe 4 (`max_daily_hours`) beziehen sich auf das, was das
Gesetz Arbeitszeit nennt.

## 3. Rechtlicher Rahmen

| Norm | Inhalt |
|---|---|
| [§ 2 Abs. 1](https://www.gesetze-im-internet.de/arbzg/__2.html) | „Arbeitszeit im Sinne dieses Gesetzes ist die Zeit vom Beginn bis zum Ende der Arbeit **ohne die Ruhepausen**" |
| [§ 4](https://www.gesetze-im-internet.de/arbzg/__4.html) | Die Arbeit ist durch **im Voraus feststehende** Ruhepausen zu unterbrechen: mindestens **30 Minuten** bei mehr als sechs bis zu neun Stunden, **45 Minuten** bei mehr als neun Stunden. Aufteilbar in Abschnitte von je mindestens 15 Minuten. Länger als sechs Stunden am Stück darf nicht ohne Ruhepause gearbeitet werden |

Zwei Dinge sind daran wichtig und werden unten unterschiedlich behandelt:

- die **Mindestdauer** hängt allein von der Länge der Arbeitszeit ab und ist damit aus einem
  Block ableitbar;
- die **Sechsstundenregel** hängt von der *Lage* der Pause ab und ist es nicht.

## 4. Entschiedene Fragen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Pausenmodell | **Dauer am Block**, keine Uhrzeit | Die Mindestdauer wird damit prüfbar, die Nettoarbeitszeit korrekt. Die Lage der Pause mitzuführen hieße Schema, Planer, Zeitachsendarstellung und die Blockplanung aus Etappe 4 anzufassen — für eine Regel, die in der Praxis ohnehin der Dienstplan vor Ort auflöst |
| Vorgabewert | **Die gesetzliche Mindestpause für die Blocklänge** | § 4 *verlangt* die Pause. Ein Plan, der sie nicht einrechnet, behauptet, jemand arbeite acht Stunden durch — was so nicht zulässig wäre. Der Standard nimmt an, was das Gesetz ohnehin vorschreibt |
| Vorgabewert je Schichtart | **Nein** | Die Mindestpause ist aus der Blocklänge ableitbar; ein zweiter Vorgabewert wäre Fläche ohne Nutzen (YAGNI) |
| Wirkung auf die Grenzen | **Netto** | § 2 Abs. 1 lässt keine andere Lesart zu |

## 5. Datenmodell

**Migration `0009_break_minutes`:**

```
shift_assignments + break_minutes INTEGER NULL
```

`NULL` heißt: **die gesetzliche Mindestpause für die Länge dieses Blocks.** Ein gesetzter Wert
ist die tatsächliche Pause dieses Blocks — auch 0, wenn HR das bewusst so einträgt.

Damit folgt das Feld demselben dreistufigen Muster, das das Projekt für Zeiten schon zweimal
benutzt (eigene Zeit → Datums-Override → Schichtart): der Regelfall steht nirgends geschrieben
und ergibt sich, nur die Abweichung wird gespeichert. **Alle bestehenden Zeilen bleiben damit
unverändert gültig** und bekommen rückwirkend die richtige Pause.

Nullbar, nicht `NOT NULL DEFAULT 0`: eine 0 wäre eine Aussage („keine Pause"), und die wollen
wir von „nicht abweichend geregelt" unterscheiden können. Das ist der Unterschied zu
`max_daily_hours` aus Etappe 4, wo genau umgekehrt argumentiert wurde — dort ist der Standard
eine Sicherheitsgrenze, die nie unbesetzt sein soll, hier ist er eine Ableitung.

`.py`-Migration mit `table_columns()`-Wächter, Rundlauftest up → down → up. Fallstrick 3.

## 6. Netto und brutto — die zentrale Unterscheidung

Ab dieser Etappe sind **Anwesenheit** und **Arbeitszeit** zwei verschiedene Größen. Wer
08:00–16:00 im Plan steht, ist acht Stunden anwesend und arbeitet siebeneinhalb.

**Anwesenheit (brutto)** — bleibt, was sie ist:

- `coverage_gaps` und alles in `coverage_model.py`. Wer 08:00–16:00 eingeteilt ist, deckt diese
  acht Stunden ab; die Pause fällt nicht aus der Besetzung heraus
- die Überschneidungsprüfung zweier Blöcke am selben Tag
- die Ruhezeit nach § 5 (sie misst von Ende bis Beginn, nicht Arbeitszeit)
- die Arbeitszeitfenster-Prüfung (`window_contains_shift`) — wer von 08:00 bis 16:00 verfügbar
  ist, ist es auch während seiner Pause

**Arbeitszeit (netto)** — rechnet ab jetzt ohne Pause:

| Stelle | heute |
|---|---|
| `scheduler.py`, Tagesgrenze in `eligible_candidates()` | `slot['duration_minutes']` |
| `scheduler.py`, Wochengrenze in `eligible_candidates()` | `slot['duration_minutes']` |
| `scheduler.py`, `day_minutes`/`week_minutes` in `backtrack()` | `slot['duration_minutes']` |
| `app.py`, Tagesgrenze in `constraint_warnings()` | `shift_duration_minutes(...)` |
| `app.py`, Wochenstunden in `constraint_warnings()` | `shift_duration_minutes(...)` |

Das sind alle. Ausdrücklich geprüft: sonst rechnet nichts im Projekt mit Arbeitszeit.

### 6.1 Wie es im Slot aussieht

`duration_minutes` **behält seine Bedeutung** — die Spanne von Beginn bis Ende. Daneben tritt
`working_minutes`, die Nettozeit. Den bestehenden Namen umzudeuten wäre die gefährlichere
Variante: jede Stelle, die ihn heute liest, müsste einzeln geprüft werden, und eine übersehene
fiele nicht auf.

### 6.2 Zwei neue Funktionen in `scheduler.py`

```python
legal_break_minutes(duration_minutes) -> int
net_working_minutes(duration_minutes, break_minutes) -> int
```

Sie gehören zu `shift_duration_minutes()` in dieselbe Datei — dieselbe Domäne, dieselbe
Minutenachse, und `app.py` wie `block_planner.py` importieren von dort ohnehin schon. Ein
viertes Modul für zwei Funktionen wäre Ballast.

**Die erste Funktion nimmt die Spanne, nicht die Arbeitszeit — und das ist die eigentliche
Schwierigkeit dieser Etappe.** § 4 bemisst die Pause an der Arbeitszeit; die Arbeitszeit ist
aber die Spanne *minus* der Pause. Wer die Regel wörtlich auf die Arbeitszeit anwendet, dreht
sich im Kreis: eine Spanne von 6:30 h ergibt ohne Pause 6:30 h Arbeitszeit, das ist „mehr als
sechs Stunden" und verlangt 30 Minuten — mit denen die Arbeitszeit auf genau 6:00 h fällt, was
*keine* Pause mehr verlangen würde.

Aufgelöst wird das über die Frage „welche Pause ist für die Arbeitszeit, die dabei
herauskommt, ausreichend?" — und davon die kleinste. Für 6:30 h ist das 30 Minuten: ohne Pause
wären 30 gefordert und nicht genommen, mit 30 Minuten sind 0 gefordert und 30 genommen. Auf
die Spanne umgerechnet ergeben sich drei Schwellen:

| Spanne | Pause |
|---|---|
| bis einschließlich 6:00 h | 0 |
| über 6:00 h bis einschließlich 9:30 h | 30 Min |
| über 9:30 h | 45 Min |

Die 9:30 h sind die Stelle, an der das Verfahren zählt und eine naive Umsetzung falsch liegt:
bei 9:31 h Spanne reichen 30 Minuten nicht mehr, weil 9:01 h Arbeitszeit übrig blieben — mehr
als neun Stunden, also 45 gefordert. Der Test hält genau diese vier Kanten fest.

## 7. Wer prüft was

**Der Generator** rechnet mit `working_minutes` und plant damit von sich aus innerhalb der
Grenzen. Er setzt `break_minutes` nicht — die Blöcke bekommen die Mindestpause über den
`NULL`-Standard, und genau das ist die richtige Annahme.

**Der Handkorrektur-Pfad** warnt zusätzlich, wenn HR eine Pause **unter** der gesetzlichen
Mindestdauer einträgt. Dieselbe Haltung wie überall: Warnung statt Verbot, HR bleibt der Chef.
Ein neuer i18n-Schlüssel `warn_break_below_minimum`, deutsch und englisch.

Ohne diese Warnung wäre die Prüfung leer: solange `break_minutes` `NULL` bleibt, ist jeder Plan
per Konstruktion konform. Die Warnung ist der einzige Ort, an dem § 4 überhaupt verletzt werden
kann.

## 8. API

- `PUT /assignments/<id>` nimmt zusätzlich `break_minutes` entgegen. Fehlt der Schlüssel im
  Rumpf, wird auf `NULL` gesetzt — **dieselbe Falle wie bei `start_time`/`end_time`**
  (Fallstrick 14 des Handoffs), und aus demselben Grund: die Route schreibt vollständig. Das
  Frontend muss den Wert mitschicken
- `GET /schedules/<year>/<month>` liefert je Zuweisung `break_minutes` (der gesetzte Wert oder
  `null`) und `effective_break_minutes` (der tatsächlich wirksame), analog zum bereits
  bestehenden Paar aus gesetzter und aufgelöster Zeit
- `POST /schedules/generate` unverändert

## 9. Frontend

- `ShiftCell.jsx`: die Pause je Person, dort wo schon die individuelle Zeit bearbeitet wird.
  Angezeigt wird sie nur, wenn sie abweicht — dasselbe Muster wie bei den Zeiten, sonst steht
  auf jeder Zeile dieselbe Zahl
- Die Zeitanzeige nennt bei einer Pause über 0 die Nettozeit, damit „08:00–16:00" nicht wie
  acht Stunden Arbeit aussieht
- Neue Texte in beiden Sprachen

## 10. Tests

| Ebene | Was |
|---|---|
| `test_scheduler.py` (23 Bestandstests) | Unverändert grün. Sie liefern keine Zeiten, also auch keine Pausen |
| `test_working_time.py` (neu) | Die drei Schwellen von `legal_break_minutes()` und ihre Kanten: 6:00 h → 0, 6:01 h → 30, 9:30 h → 30, 9:31 h → 45. Dazu die zirkuläre Auflösung an der 6:30-h-Kante |
| `test_scheduler_split_shifts.py` (erweitert) | Die Tagesgrenze rechnet netto: zwei Blöcke von je 5 h mit je 0 Pause sprengen eine Grenze von 9 h, zwei Blöcke von je 7 h mit je 30 Min Pause nicht. **Gegenprobe**: dieselben Blöcke brutto gerechnet ergäben das umgekehrte Bild |
| `test_migrations.py` / `_postgres.py` | Rundlauf `0009` up → down → up |
| API | `break_minutes` schreiben, lesen, und `effective_break_minutes` bei `NULL`; die Warnung unter der Mindestdauer; die Falle aus §8 (fehlender Schlüssel setzt auf `NULL`) |
| `test_api_coverage.py` (erweitert) | **Die wichtigste Gegenprobe der Etappe**: eine Zuweisung mit Pause deckt weiterhin ihre volle Anwesenheit ab. Ein Block 08:00–16:00 mit 30 Min Pause schließt ein Bedarfsband 08:00–16:00 vollständig — die Pause darf keine Deckungslücke erzeugen |
| Frontend (Vitest) | Abweichende Pause wird angezeigt, nicht abweichende nicht |

## 11. Fallstricke, die hier greifen

- **3** — `ADD COLUMN` in einer `.py`-Migration mit Wächter, Rundlauftest Pflicht
- **4** — Tests, die nichts prüfen. Fünf Fälle bisher, einer davon in Etappe 4
- **6** — die 23 Bestandstests bleiben unverändert
- **7** — Kommentarsprache folgt der Datei
- **10** — Postgres-Verhalten nie aus SQLite schließen
- **14** — `PUT /assignments/<id>` schreibt vollständig; `break_minutes` erbt diese Falle

## 12. Bewusst nicht dabei

- **Die Lage der Pause** und damit § 4 Satz 3 („nicht länger als sechs Stunden am Stück")
- **Die Aufteilung in Abschnitte** von je mindestens 15 Minuten — gespeichert wird eine Summe
- **„Im Voraus feststehend"** aus § 4 Satz 1 als eigene Prüfung; der Plan *ist* die
  Voraus-Festlegung
- **Pausen als Vorgabewert an der Schichtart**
- **Der Achtstundenschnitt** (5c) und **die Sonn- und Feiertagsruhe** (5b)

## 13. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Umstellung auf netto lockert bestehende Grenzen unbemerkt | Sie ist die korrekte Lesart von § 2 Abs. 1, aber sie ändert Pläne. Steht in der Migration, im README und im Handoff; ein Test hält die Richtung ausdrücklich fest |
| Anwesenheit und Arbeitszeit geraten durcheinander | §6 listet beide Seiten vollständig auf; die Deckungs-Gegenprobe in `test_api_coverage.py` ist genau dafür da |
| `duration_minutes` wird an einer übersehenen Stelle als Arbeitszeit gelesen | Der Name behält seine Bedeutung, statt umgedeutet zu werden — eine übersehene Stelle rechnet dann weiter brutto und ist damit höchstens zu streng, nie zu lax |
| Die zirkuläre Ableitung der Mindestpause wird falsch aufgelöst | Eigene Testdatei nur dafür, mit den Kanten als Fälle |
