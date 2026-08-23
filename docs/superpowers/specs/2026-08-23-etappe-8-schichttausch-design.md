# Design: Etappe 8 — Der geführte Schichttausch

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Roadmap-Punkt v1.1. Getauscht werden konnte schon vorher — aber nur durch die Personalabteilung
und nur sofort: zwei Zellen anklicken, fertig, Warnungen hinterher. Wer selbst tauschen wollte,
musste jemanden bitten, es für ihn zu tun.

Drei Schritte, und jeder ist tragend:

1. Der Antragsteller bietet eine **eigene** Schicht an und nennt eine Kollegin oder einen Kollegen.
2. Der Tauschpartner stimmt zu und wählt dabei selbst, welche **seiner** Schichten er dagegen gibt.
3. Die Personalabteilung genehmigt. Erst dann bewegt sich etwas.

## 2. Die tragende Entscheidung: wann ein Tausch abgelehnt wird

Ein Tausch ist der einzige Vorgang im Tool, der die Belastung von **zwei** Menschen gleichzeitig
ändert. `constraint_findings()` prüft beide Seiten — aber nicht jede Feststellung wiegt gleich:

| Feststellung | Charakter | Blockiert einen Mitarbeitertausch |
|---|---|---|
| Ruhezeit § 5 Abs. 1 | zwingendes Recht | **ja** |
| Tagesarbeitszeit § 3 | zwingendes Recht | **ja** |
| Pause § 4 | zwingendes Recht | **ja** |
| Siebter Tag in Folge, § 11 Abs. 3 | zwingendes Recht | **ja** |
| Sonntagsbudget § 11 Abs. 1 | zwingendes Recht | **ja** |
| Überlappende Blöcke | kein Recht, sondern Physik | **ja** |
| Feiertag § 9 / § 10 | *nicht entscheidbar* | nein |
| Gesperrter Wochentag, Arbeitszeitfenster, erlaubte Schichtarten | Absprache | nein |
| Wochenstunden, Monatskontingent | Vertrag | nein |

**Warum abgelehnt und nicht nur gemeldet:** [§ 22 Abs. 1
ArbZG](https://www.gesetze-im-internet.de/arbzg/__22.html) macht einen Verstoß zur
Ordnungswidrigkeit **des Arbeitgebers**, § 23 in schweren Fällen zur Straftat. §§ 3 und 5 lassen
sich nicht durch Einzelabrede abbedingen — nur nach § 7 durch Tarifvertrag, den dieses Tool nicht
abbildet. Zwei Kolleginnen, die einen rechtswidrigen Tausch unter sich verabreden und der
Personalabteilung die vollendete Tatsache vorlegen, verschöben eine Haftung, die das Gesetz beim
Arbeitgeber verortet.

**Warum der Direkttausch der Personalabteilung weiter nur warnt:** sie trägt die Verantwortung und
kann etwas wissen, das das Tool nicht weiß — einen Notfall nach § 14, einen Tarifvertrag nach § 7.
Ihr denselben Riegel vorzuschieben hieße, ihr die Entscheidung zu nehmen, für die sie haftet.

**Warum der Feiertag nicht blockiert:** § 9 verbietet Feiertagsarbeit, § 10 nimmt ganze Branchen
aus, und auf welcher Seite dieser Betrieb steht, ist eine Tatsache über den Betrieb, die das Tool
nicht hat. Zu blockieren hieße, sie zu behaupten.

## 3. Warum der Antrag eine Person nennt und keine fremde Schicht

**Der erste Entwurf hatte hier ein Loch, und es fiel erst beim Anschließen der Oberfläche auf.**
Er ließ den Antragsteller beide Schichten benennen. Ein Mitarbeiter sieht aber ausschließlich
**seine eigenen** (Etappe 5f) — er hätte die Gegenschicht gar nicht auswählen können. Das Merkmal
wäre für seine Hauptnutzer unbenutzbar gewesen.

Ihm dafür den Dienstplan aller anderen zu zeigen wäre die naheliegende und die falsche Antwort:
sie nähme eine Datensparsamkeit zurück, die bewusst so entschieden wurde, und zwar für ein
Nebenziel.

**Stattdessen:** der Antrag nennt eine Person. Der Partner weiß selbst am besten, welche seiner
Schichten er entbehren kann, und seine Zustimmung wird dadurch inhaltlich statt bloß formal.
`partner_assignment_id` ist deshalb NULL-bar und wird erst mit der Zustimmung gesetzt.

Neu dafür: `GET /colleagues` — Namen und Kennungen der aktiven Belegschaft, für jeden Angemeldeten.
Die kleinstmögliche Offenlegung, die den Antrag ermöglicht: **wer hier arbeitet, und nichts
darüber, wann.** Anonymisierte Zeilen bleiben draußen; ein Grabstein ist kein Kollege.

## 4. Warum erst getauscht und dann geprüft wird

`perform_swap()` führt den Tausch aus und liest **danach** die Feststellungen. Aufrufer, die nur
gefragt haben, rollen die Transaktion zurück.

Vorher zu urteilen hieße, den falschen Zustand zu beurteilen: prüft man den Partner gegen das
Datum des Antragstellers, während er seine eigene Schicht noch hält, zählt ein Block mit, der
gleich seine Hände verlässt. Zwei Schichten an benachbarten Tagen melden dann eine
Ruhezeitverletzung, die der Tausch gerade **auflöst** — ein rechtlich einwandfreier Tausch
scheiterte an der Reihenfolge der Prüfung.

Die Alternative wäre eine zweite, parallele Rechnung „als ob" gewesen. Eine zweite Kopie einer
Regel ist eine Regel, die auseinanderläuft — dieselbe Lehre wie in Etappe 6c.

**Beides hat einen Test**, und der zur Reihenfolge wurde gegengeprobt: mit der Prüfung vor dem
Tausch wird er rot.

## 5. Geprüft wird zweimal

Bei der Zustimmung (erster Moment, in dem beide Schichten feststehen) **und** bei der Genehmigung.
Zwischen beiden liegen Tage. Wer nur einmal prüft, genehmigt später einen Tausch, der inzwischen
rechtswidrig geworden ist — und die Prüfung von damals steht als Beleg dafür in der Akte, dass
alles geprüft worden sei.

## 6. Was bewusst fehlt

- **Ein Begründungsfeld.** Ein Kasten „warum möchtest du tauschen" holt sich „Arzttermin" und
  „meine Mutter ist im Krankenhaus" — Gesundheitsdaten nach Art. 9 DSGVO, in einer Tabelle ohne
  eigene Frist. Aus demselben Grund protokolliert Etappe 5g keine Anfrageinhalte
- **Ein Tauschbrett** („diese Schicht gebe ich ab, wer will?"). Reizvoll, aber es zeigt allen die
  Dienste aller — dieselbe Rücknahme der Datensparsamkeit, nur freiwillig
- **Mitbestimmung nach § 87 Abs. 1 Nr. 2 BetrVG.** Ob und wann ein Betriebsrat bei der Verteilung
  der Arbeitszeit mitzureden hat, hängt vom Betrieb und von bestehenden Vereinbarungen ab. Das ist
  keine Frage, die ein Werkzeug beantworten darf
- **Benachrichtigungen.** Es gibt keinen Versandweg außer den Einladungsmails, und ein Merkmal,
  das lautlos auf eine Seite wartet, die niemand aufruft, wäre besser ehrlich als halb
- **Ein Tausch über die Monatsgrenze.** Beide Schichten müssen zum selben Plan gehören. Die
  Monatsgrenze ist die bekannte Einschränkung des Werkzeugs, und sie hier einseitig aufzuweichen
  wäre eine eigene Entscheidung

## 7. Was das Prüfen im Browser gefunden hat

Zwei Dinge, die kein Unit-Test gezeigt hätte:

1. **„Schicht entfallen" stand da, wo die Schicht noch gar nicht gewählt war.** Zwei verschiedene
   Sachverhalte, eine Meldung — im ersten Fall schlicht falsch.
2. **Der Ablehnungsgrund verschwand nach vier Sekunden.** Die Flash-Meldung blendet sich aus; ein
   rechtlicher Grund ist aber genau das, was jemand lesen und behalten muss. Er steht jetzt am
   Antrag, bis sich etwas ändert.

## 8. Tests

`backend/test_api_schichttausch.py` (26), `frontend/src/pages/SwapRequests.test.jsx` (7), dazu der
Rundlauf von `0015_swap_requests` in SQLite und Postgres samt `ON DELETE CASCADE`.

Die Gegenproben sind auch hier die eigentliche Arbeit: ohne sie wären eine Umsetzung, die *jeden*
Tausch ablehnt, eine, die die Absprachen mitblockiert, und eine Oberfläche ganz ohne Knöpfe
sämtlich grün.
