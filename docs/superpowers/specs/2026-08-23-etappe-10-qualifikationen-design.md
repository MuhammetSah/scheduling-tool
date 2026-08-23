# Design: Etappe 10 — Nachweise

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Der letzte Punkt der Roadmap:

> Skill/qualification matching, so a shift can require a specific certification

## 2. Die interessante Hälfte ist das Ablaufdatum

Die Zuordnung selbst ist eine Verknüpfungstabelle. Was sie tragfähig macht, ist `valid_until`.

Ein Ersthelferschein läuft nach zwei Jahren ab — DGUV Vorschrift 1 § 26 verlangt die Auffrischung;
ein Staplerschein ebenso. **Ein Nachweis ohne Ablaufdatum ist einer, den der Dienstplan noch Jahre
nach seinem Ende weiter beachtet** — und damit genau der Fehler, den die Arbeitszeitfenster mit
`valid_from`/`valid_until` schon vermeiden.

Drei Entscheidungen dazu, jede mit eigenem Test:

- **NULL heißt „läuft nicht ab", nicht „abgelaufen".** Die andere Lesart machte jeden Nachweis ohne
  Datum wertlos
- **Die Grenze ist einschließend**: ein Nachweis bis zum 15. trägt den 15. noch. Dieselbe Auslegung
  wie bei `valid_until` der Fenster — zwei benachbarte Regeln, die „bis" verschieden lesen, sind
  eine Falle
- **Das Datum geht durch `parse_iso_date()`**, nicht durch eine bloße Prüfung. Fallstrick 19:
  `'20261115'` passiert `date.fromisoformat()` und verliert danach jeden Zeichenkettenvergleich —
  der Nachweis liefe **nie** ab

## 3. Hart im Generator, Warnung bei der Handkorrektur

Dieselbe Aufteilung, die das ganze Werkzeug hat. Ein erzeugter Plan, der von Hand nachgearbeitet
werden muss, ist keine Hilfe; eine Handkorrektur, die blockiert, nimmt der Personalabteilung die
Entscheidung.

**Zwei verschiedene Meldungen**, weil sie zu Verschiedenem auffordern: „hat den Nachweis nicht" und
„der Nachweis ist am 31.10. abgelaufen". Die zweite sagt, was zu tun ist.

**Ausdrücklich keine Sperre beim Tausch.** Ob ein Nachweis rechtlich verlangt ist (Ersthelfer nach
DGUV Vorschrift 1) oder eine Hausregel („kennt die Kaffeemaschine"), kann das Tool nicht wissen —
und eine Sperre darauf zu gründen hieße, es zu behaupten. Dieselbe Zurückhaltung wie beim Feiertag
in Etappe 9. `ARBZG_BLOCKERS` bleibt, was der Name sagt.

## 4. Wo die Anforderung hängt, und was das kostet

**An der Schichtart.** Sie gilt für **jeden** auf dieser Schicht, nicht für einen davon —
„mindestens ein Ersthelfer je Schicht" wäre eine Anzahl innerhalb einer Anzahl und braucht ein
eigenes Modell.

**Der Preis, und er gehört genannt:** ein Block **ohne** Vorlage trägt keine Anforderung. Seit
Etappe 4 schneidet der Planer Blöcke zu, die keiner Schichtart mehr entsprechen, und die erben
nichts. Die Alternative wäre, die Anforderung an das Bedarfsband zu hängen — dort entstehen die
Blöcke —, aber die Schichtart ist die Einheit, die die Personalabteilung benennt und wiedererkennt.
Das ist eine bewusste Wahl, keine Auslassung.

**Das Gegenstück zu `allowed_shift_types`:** das hängt an der *Person* („Anna macht nur
Frühschichten") und ist eine Absprache. Die Anforderung hängt an der *Arbeit* und sagt, warum. Beide
bleiben, weil sie Verschiedenes bedeuten.

## 5. Der Katalog

Ein Name je Zeile, mit `UNIQUE`. „Ersthelfer" zweimal anzulegen erzeugt zwei Nachweise, die dasselbe
meinen — danach trägt die eine Hälfte der Belegschaft den einen und die andere den anderen, während
jede Schicht genau einen verlangt.

**Löschen räumt überall auf**, und die Rückfrage sagt das: der Nachweis verschwindet bei allen, die
ihn halten, und bei allen Schichten, die ihn verlangen. Eine Schicht, die etwas verlangt, das es
nicht mehr gibt, wäre unbesetzbar für immer. Die Löschung steht ausdrücklich im Code und verlässt
sich nicht auf `ON DELETE CASCADE` — SQLite erzwingt Fremdschlüssel nur mit eingeschaltetem
`PRAGMA`, und daran darf das nicht hängen.

## 6. Tests

`backend/test_api_qualifikationen.py` (17), vier in `ShiftTypes.test.jsx`, dazu der Rundlauf von
`0017` in SQLite und Postgres samt Kaskadenprobe.

**Ein Bestandstest wurde geändert**, und das ist die einzige Stelle, an der diese Etappe an
Vorhandenem rüttelt: `test_schichtart_traegt_keine_bedarfszahlen_mehr` nagelt den Schlüsselsatz der
Schichtart fest, damit auffällt, wenn die Vorlage wieder anfängt, Dinge zu sammeln. Genau das ist
passiert — bewusst. Der Test nennt jetzt den neuen Schlüssel *und* den Unterschied: die alten
Bedarfszahlen sagten, **wie viele** gebraucht werden (das gehört in die Bänder), die Nachweise
sagen, **wer** die Arbeit machen darf.

**Und der Postgres-Schreibtest hat getan, wofür er da ist.** Der erste Entwurf gab beiden
Verknüpfungstabellen einen zusammengesetzten Primärschlüssel statt einer eigenen `id` — sauber
modelliert, auf SQLite einwandfrei, und auf Postgres ein 500er in jeder schreibenden Route.
Fallstrick 16: die Dialektschicht hängt jedem `INSERT` ohne `RETURNING` ein `RETURNING id` an, und
eine Tabelle ohne `id`-Spalte scheitert daran mit `UndefinedColumn`.

**Der lokale Lauf war grün, der `backend-postgres`-Job rot** — genau die Konstellation, für die
Fallstrick 21 im Handoff steht. Beide Tabellen tragen jetzt eine `id` und sagen die Eindeutigkeit
mit `UNIQUE`, wie `employee_allowed_shift_types` seit `0001_baseline.py`. Dem vorhandenen Muster zu
folgen wäre von Anfang an richtig gewesen.

Ein Frontend-Test-Helfer wurde ebenfalls angefasst: seine Zusage antwortete auf jeden Pfad mit
derselben Liste, und die Seite lädt jetzt zwei. Ohne die Unterscheidung erschienen die Schichtarten
ein zweites Mal als Nachweise.

## 7. Bewusst nicht dabei

- **„Mindestens ein Ersthelfer je Schicht"** (§4)
- **Eine Anforderung am Bedarfsband** (§4)
- **Eine Warnung, wenn ein Nachweis demnächst abläuft.** Reizvoll und die naheliegende Fortsetzung
  — aber es braucht eine Frist („wie lange vorher?"), und die ist eine Festlegung des Betreibers,
  keine des Werkzeugs
- **Nachweise als Pflichtangabe.** Ein Betrieb ohne Katalog merkt von dieser Etappe nichts, und das
  ist richtig so
