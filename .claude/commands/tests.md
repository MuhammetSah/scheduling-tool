---
description: Fährt dieselbe Suite wie die CI (Backend, Lint, Build, Frontend)
allowed-tools: Bash(cd:*), Bash(./venv/bin/python -m pytest:*), Bash(npm test:*), Bash(npm run lint:*), Bash(npm run build:*)
---

Führe die vier Prüfungen aus, die auch `.github/workflows/ci.yml` fährt, und
melde am Ende eine Zeile je Prüfung mit Ergebnis:

1. `cd backend && ./venv/bin/python -m pytest`
2. `cd frontend && npm run lint`
3. `cd frontend && npm run build`
4. `cd frontend && npm test -- --run`

Wenn `$ARGUMENTS` einen Pfad oder ein Testmuster enthält, beschränke Schritt 1
bzw. 4 darauf; ohne Argument läuft alles.

Zwei Dinge gehören in die Meldung, weil ein grüner Lauf sie sonst verdeckt:
- wie viele Tests **übersprungen** wurden (lokal sind das die Postgres-Tests,
  die ohne `TEST_DATABASE_URL` nichts prüfen),
- ob ein Fehlschlag aus dem Backend oder dem Frontend kommt.

Repariere nichts ungefragt — melde erst, was rot ist.
