---
description: Zieht docs/HANDOFF.md auf den aktuellen Stand nach
---

Aktualisiere [`docs/HANDOFF.md`](../../docs/HANDOFF.md) so, dass eine neue
Sitzung ohne Vorwissen weiterarbeiten kann.

Sieh dir zuerst an, was seit dem dort verzeichneten Stand passiert ist
(`git log`, offene Branches, offene PRs), und ziehe dann nach:

- **Aktueller Stand**: Branch-Situation, Testzahlen (passed/skipped),
  CI-Jobs, höchste Migrationsnummer, Laufzeitabhängigkeiten.
- **Erster Schritt einer neuen Sitzung**: was als Nächstes ansteht — und was
  ausdrücklich beim Nutzer liegt und nicht bei Claude.
- **Zurückgestellte Befunde**: Erledigtes wird **durchgestrichen, nicht
  gelöscht** — wer später liest, soll sehen, dass es geprüft wurde.
- **Fallstricke**: nur ergänzen, wenn diese Etappe wirklich einen neuen gezeigt
  hat. Ein Fallstrick ist etwas, das jemanden Zeit gekostet hat, keine
  Stilfrage.

Sprache: deutsch, im Ton der vorhandenen Datei. Datum im Kopf mitziehen.

Prüfe jede Aussage, die du übernimmst, gegen den Quelltext — in einer früheren
Etappe waren vier Punkte der Liste längst erledigt, ohne dass es jemand notiert
hatte, und ungeprüft danach zu arbeiten hieße, Vorhandenes zu „reparieren".
