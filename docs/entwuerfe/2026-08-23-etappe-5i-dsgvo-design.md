# Design: Etappe 5i — DSGVO

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §10
**Status:** Entwurf, entschieden

---

## 1. Ziel

Der letzte Teil von Etappe 5. Das Tool speichert Krankmeldungen — Gesundheitsdaten nach
Art. 9 DSGVO — und seit 5g ein Protokoll über benannte Personen, beides ohne Frist und ohne
Auskunftsweg. Drei Dinge fehlen:

| | Norm |
|---|---|
| **Auskunft** — alle Daten zu einer Person auf einen Abruf | Art. 15 |
| **Löschung** — die Person verschwindet | Art. 17 |
| **Aufbewahrungsbegrenzung** — Daten verschwinden von selbst | Art. 5 Abs. 1 lit. e |

Zwei Festlegungen kommen vom Nutzer: **sechs Monate** Aufbewahrung, und beim Löschen wird
**anonymisiert**.

## 2. Der Konflikt, der zuerst zu klären war

Sechs Monate lassen sich **nicht** auf den Dienstplan anwenden.
[§ 16 Abs. 2 ArbZG](https://www.gesetze-im-internet.de/arbzg/__16.html): der Arbeitgeber muss
die über acht Stunden hinausgehende Arbeitszeit aufzeichnen, und „die Nachweise sind mindestens
zwei Jahre aufzubewahren". Ein Plan mit Zehnstundentagen nach sechs Monaten zu löschen wäre der
Verstoß gegen eine Norm zur Erfüllung einer anderen.

Die Frist gilt deshalb für das, was **über** die Arbeitszeitaufzeichnung hinausgeht:

| Betroffen | Nicht betroffen |
|---|---|
| Krankmeldungen und Urlaubsmeldungen (`employee_absences`) | Zuweisungen und Pläne — § 16 Abs. 2 |
| Der Abwesenheitsgrund **in** der Zuweisung (`absence_type`, `absent_employee_id`) | Mitarbeiterstammdaten — sie werden über die Löschung entfernt, nicht über eine Frist |
| Die Einträge des Änderungsprotokolls (`audit_log`) | |

Der zweite Punkt ist der, den man übersieht: der Abwesenheitsgrund steht **doppelt** — in
`employee_absences` und denormalisiert in `shift_assignments`. Nur die eine Tabelle zu räumen
ließe die Gesundheitsangabe im Dienstplan stehen.

## 3. Löschen heißt anonymisieren

Heute setzt `ON DELETE SET NULL` die Zuweisungen der gelöschten Person auf „unbesetzt". Das ist
schlechter als es klingt: die Vergangenheit sieht danach unterbesetzt aus, Deckungslücken
erscheinen rückwirkend, und die Arbeitszeitaufzeichnung aus § 16 verliert genau die Zuordnung,
die sie ausmacht.

**Stattdessen wird die Mitarbeiterzeile zum Grabstein**: Name wird zu „Gelöschter Mitarbeiter
#<id>", E-Mail entfällt, `active` auf 0, und alles Persönliche daneben — Arbeitszeitfenster,
gesperrte Daten samt Gründen, Abwesenheiten, erlaubte Schichtarten — wird entfernt. Die
Zuweisungen bleiben, wo sie sind, und zeigen weiter auf diese Zeile.

**Warum das Art. 17 genügt:** Abs. 3 lit. b nimmt Verarbeitung aus, die zur Erfüllung einer
rechtlichen Verpflichtung erforderlich ist — und § 16 Abs. 2 ArbZG ist eine. Was bleibt, ist
die Arbeitszeitaufzeichnung ohne Person; was geht, ist die Person.

`DELETE /employees/<id>` behält seinen Namen und ändert seine Bedeutung. Die Antwort sagt
ausdrücklich, dass die Schichten bestehen bleiben — eine Route, die etwas anderes tut, als ihr
Verb verspricht, muss es wenigstens aussprechen.

Neue Spalte `employees.anonymized_at`, damit ein Grabstein von einem lebenden Datensatz
unterscheidbar ist und die Oberfläche ihn nicht zum Bearbeiten anbietet.

## 4. Auskunft

`GET /employees/<id>/data-export` — `require_self_or_hr`, wie die Fenster und die Abwesenheiten.

Liefert als JSON alles, was das Tool über diese Person weiß: Stammdaten, Einschränkungen,
Arbeitszeitfenster, Abwesenheiten, Zuweisungen mit Zeiten, das verknüpfte Konto (ohne
Passwort-Hash) und die Protokolleinträge dieses Kontos.

**JSON und nicht PDF.** Art. 15 Abs. 3 verlangt „in einem gängigen elektronischen Format";
JSON ist eines, und die Alternative wäre eine Abhängigkeit für Papieroptik.

## 5. Die Frist in der Praxis

Einstellung `retention_months` in der `settings`-Tabelle aus 5d, **Standard 6**.

**Wann geräumt wird:** beim Start der Anwendung, und auf Knopfdruck über
`POST /retention/purge` (HR). Ein Zeitplandienst steht nicht zur Verfügung — Render bietet auf
dem genutzten Plan keinen —, und das gehört gesagt statt vorgetäuscht: bleibt die Anwendung
monatelang ohne Neustart, räumt sie ohne den Knopf nicht. In der Praxis startet der Dienst bei
jedem Deploy neu.

**Der Knopf meldet, was er getan hat** — wie viele Zeilen aus welcher Tabelle. Ein Aufräumen,
das schweigt, lässt niemanden wissen, ob es lief.

## 6. Datenmodell

**Migration `0014_anonymisation`:**

```
employees + anonymized_at TIMESTAMP NULL
```

Mehr nicht. Die Frist lebt in `settings`, das Räumen ist eine Löschoperation.

## 7. Tests

| Ebene | Was |
|---|---|
| `test_migrations.py` / `_postgres.py` | Rundlauf `0014` |
| API | Löschen anonymisiert: Name ersetzt, E-Mail weg, Fenster und Abwesenheiten weg — **und die Zuweisungen zeigen weiter auf die Zeile** (der Kern) |
| API | **Gegenprobe:** die Zuweisungen werden *nicht* unbesetzt. Ohne sie wäre das alte `SET NULL`-Verhalten ebenfalls grün |
| API | Auskunft: self-or-HR; enthält Abwesenheiten und Zuweisungen; enthält **keinen** Passwort-Hash |
| API | Räumen: Abwesenheiten älter als sechs Monate weg, jüngere bleiben; `absence_type` in der Zuweisung mit geräumt; Protokolleinträge geräumt |
| API | **Zuweisungen bleiben stehen** — § 16 Abs. 2, und die Gegenprobe zum Räumen |
| API | Die Frist ist über `settings` änderbar; der Standard ist 6 |

## 8. Bewusst nicht dabei

- **Ein Zeitplandienst** für das Räumen (§5)
- **PDF für die Auskunft** (§4)
- **Einwilligungsverwaltung.** Die Verarbeitung stützt sich auf das Arbeitsverhältnis und auf
  § 16 ArbZG, nicht auf Einwilligung — eine Einwilligungsoberfläche würde eine Rechtsgrundlage
  vortäuschen, die hier nicht die tragende ist
- **Ein Verarbeitungsverzeichnis** (Art. 30). Ein Dokument, kein Programmteil
- **Löschen der Arbeitszeitaufzeichnung nach zwei Jahren.** § 16 nennt ein Minimum, kein
  Maximum; wann darüber hinaus gelöscht wird, ist wieder eine Festlegung des Betreibers, und
  eine zweite Frist ohne Anlass wäre Fläche

## 9. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Frist löscht Arbeitszeitnachweise und verstößt gegen § 16 | Sie gilt ausdrücklich nicht für Zuweisungen (§2), mit eigenem Test |
| Der Abwesenheitsgrund überlebt in der Zuweisung | Beide Orte werden geräumt (§2), mit eigenem Test |
| Anonymisierte Zeilen tauchen als Mitarbeiter auf | `anonymized_at` unterscheidet sie; die Liste blendet sie aus |
| Das Räumen läuft nie, weil niemand neu startet | Dokumentiert (§5), plus Knopf. Kein vorgetäuschter Automatismus |
