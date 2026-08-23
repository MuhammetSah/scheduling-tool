#!/bin/bash
# SessionStart-Hook: stellt die Abhaengigkeiten her, damit Tests und Linter in
# einer frischen Sitzung sofort laufen. Laeuft nur in Claude Code on the web -
# lokal ist die Umgebung die des Entwicklers, und ein Hook, der dort ungefragt
# in venv/ und node_modules/ schreibt, waere ein Uebergriff.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# --- Backend ---------------------------------------------------------------
# venv statt globalem pip: die Debian-Pakete des Containers (u.a. blinker)
# tragen keine RECORD-Datei, pip bricht beim Deinstallieren ab. Der Pfad
# backend/venv ist zugleich der, den das README dokumentiert.
cd backend
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

# Nur pytest aus requirements-dev.txt, nicht die Datei selbst: sie zieht
# ortools nach (mehrere hundert MB), und das braucht ausschliesslich
# benchmark.py. Die Version wird aus der Datei gelesen, damit der Pin dort die
# einzige Stelle bleibt - wer ihn anhebt, muss diesen Hook nicht kennen.
PYTEST_PIN="$(grep -oE '^pytest==[0-9.]+' requirements-dev.txt || echo pytest)"
./venv/bin/pip install --quiet --disable-pip-version-check "$PYTEST_PIN"
cd ..

# --- Frontend --------------------------------------------------------------
# npm install statt npm ci: der Containerzustand wird nach dem Hook
# zwischengespeichert, und install nutzt einen vorhandenen node_modules-Baum,
# statt ihn jedes Mal zu loeschen. Die CI bleibt bei npm ci.
cd frontend
npm install --no-audit --no-fund --silent
cd ..

echo "Setup fertig: backend/venv und frontend/node_modules stehen."
