# Etappe 0 — Fundament: Umsetzungsplan

**Ziel:** Das Schichtplan-Tool auf ein Fundament stellen, auf dem Schemaänderungen sicher sind — versionierte Migrationen, laufende Tests im CI, gepinnte Abhängigkeiten, gehärtete Authentifizierung und verlässliche Fehlerbehandlung.

**Architektur:** Alles bleibt beim bestehenden Aufbau — Flask mit direktem `sqlite3`/`psycopg2`-Zugriff über die Dialektschicht in `db.py`, React mit Vite. Es kommt genau eine neue Datei-Kategorie dazu: ein eigener Migrations-Runner (`backend/migrations.py`) plus ein `backend/migrations/`-Verzeichnis. Keine neuen Laufzeitabhängigkeiten.

**Tech-Stack:** Python 3.13 (Produktion) / 3.14 (lokal ok), Flask 3.1, SQLite lokal + Postgres in Produktion, React 19 + Vite 8, pytest 9 für Backend-Tests, GitHub Actions für CI.

**Spec:** [`docs/entwuerfe/2026-08-16-zeitachsen-dienstplan-design.md`](../specs/2026-08-16-zeitachsen-dienstplan-design.md), Abschnitt 10 „Etappe 0".

## Globale Rahmenbedingungen

- **Keine neuen Laufzeitabhängigkeiten.** `backend/requirements.txt` darf nur die bereits vorhandenen vier Pakete enthalten (gepinnt). Testwerkzeuge gehören in `requirements-dev.txt`.
- **Produktions-Python: 3.13.** CI testet gegen 3.13 **und** 3.14, damit lokale Entwicklung auf 3.14 nicht unbemerkt abdriftet.
- **Jeder nutzersichtbare Text zweisprachig.** Neue Backend-Meldungen kommen als Schlüssel in `backend/i18n.py` mit `de`- und `en`-Eintrag und werden über `t(g.lang, key)` ausgegeben — niemals als Literal. Frontend-Texte entsprechend in `frontend/src/i18n/translations.js`.
- **Die 23 bestehenden Scheduler-Tests bleiben unverändert grün.** Sie sind die Rückwärtskompatibilitätsgarantie. Wird einer rot, ist die Änderung falsch — nicht der Test.
- **Weekday-Konvention:** 0 = Montag … 6 = Sonntag (`date.weekday()`), wie in `db.py` dokumentiert.
- **Zeiten** sind überall `"HH:MM"`-Strings; `end <= start` bedeutet Überschreitung nach Mitternacht.
- **Jede Aufgabe endet mit grünem CI und genau einem Commit.**
- Commit-Nachrichten auf Deutsch, Präfix `feat:`, `fix:`, `chore:`, `test:` oder `docs:`.

## Dateistruktur

| Datei | Verantwortung | Aufgabe |
|---|---|---|
| `backend/requirements.txt` | Laufzeitabhängigkeiten, exakt gepinnt | 1 |
| `backend/requirements-dev.txt` | Testwerkzeuge + Benchmark-Abhängigkeit | 1 |
| `backend/pytest.ini` | pytest-Konfiguration | 1 |
| `.github/workflows/ci.yml` | Backend-Tests, Frontend-Lint und -Build bei jedem Push | 1 |
| `backend/conftest.py` | pytest-Fixtures: isolierte Test-Datenbank, Flask-Testclient | 2 |
| `backend/test_api_auth.py` | Registrierung, Login, Rollentrennung | 2 |
| `backend/migrations.py` | Migrations-Runner: anwenden, zurückrollen, Stand melden | 3 |
| `backend/migrations/0001_baseline.py` | Ausgangsschema (der heutige `init_db()`-Inhalt) | 3 |
| `backend/migrations/0002_indexes.sql` | Indizes und UNIQUE-Constraint | 4 |
| `backend/migrations/0002_indexes.down.sql` | Rücknahme dazu | 4 |
| `backend/migrations/0003_login_attempts.sql` | Tabelle für die Login-Drosselung | 6 |
| `backend/migrations/0003_login_attempts.down.sql` | Rücknahme dazu | 6 |
| `backend/test_migrations.py` | Runner: frische DB, Idempotenz, Rückrollen | 3 |
| `backend/security.py` | `SECRET_KEY`-Prüfung, Security-Header, Login-Drosselung | 5, 6 |
| `backend/test_api_security.py` | Header, Drosselung, fehlender `SECRET_KEY` | 5, 6 |
| `backend/timeutil.py` | Lokale Zeitzone und Monatsgrenzen | 8 |
| `backend/test_timeutil.py` | Monatsgrenzen für feste Daten | 8 |
| `backend/test_api_schedules.py` | Überschreibschutz beim Neugenerieren | 9 |
| `backend/app.py` | wird in fast jeder Aufgabe angepasst | 2, 5–9 |
| `backend/db.py` | `DB_PATH` aus der Umgebung; `init_db()` delegiert an den Runner | 2, 3 |
| `backend/i18n.py` | neue Meldungsschlüssel | 5–9 |
| `frontend/src/pages/SchedulePage.jsx` | Rückfrage vor dem Überschreiben von Handkorrekturen | 9 |
| `frontend/src/i18n/translations.js` | Texte dazu | 9 |
| `render.yaml` | Python-Version, Gunicorn-Konfiguration | 1, 10 |
| `README.md` | Betriebsabschnitt: Backup, Umgebungsvariablen, Runbook | 10 |

---

## Aufgabe 1: Abhängigkeiten pinnen und CI-Pipeline

Ohne CI ist jede folgende Aufgabe ungeprüft, und ohne gepinnte Versionen kann ein fremdes Release den Build brechen. Deshalb zuerst.

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/requirements-dev.txt`
- Create: `backend/pytest.ini`
- Create: `.github/workflows/ci.yml`
- Modify: `render.yaml`

**Interfaces:**
- Consumes: nichts
- Produces: `pytest` läuft aus `backend/` heraus und findet `test_*.py`; CI-Job-Namen `backend` und `frontend`

- [ ] **Schritt 1: Aktuelle Versionen einfrieren**

`backend/requirements.txt` vollständig ersetzen:

```
# Exakt gepinnt: ein unbeaufsichtigtes Major-Release einer dieser
# Bibliotheken darf den naechsten Deploy nicht brechen. Zum Anheben die
# Version hier aendern, CI gruen sehen, committen.
flask==3.1.3
flask-cors==6.0.5
gunicorn==26.0.0
psycopg2-binary==2.9.12
```

`backend/requirements-dev.txt` vollständig ersetzen:

```
# Werkzeuge fuer Tests und den Algorithmus-Benchmark. Die Anwendung selbst
# braucht nichts hiervon.
-r requirements.txt
pytest==9.1.1
ortools
```

- [ ] **Schritt 2: pytest konfigurieren**

`backend/pytest.ini` anlegen:

```ini
[pytest]
testpaths = .
python_files = test_*.py
# Die bestehenden Scheduler-Tests sind unittest-TestCases; pytest fuehrt die
# unveraendert mit aus.
addopts = -v
```

- [ ] **Schritt 3: Prüfen, dass die bestehenden Tests unter pytest laufen**

```bash
cd backend
python -m venv venv
./venv/Scripts/pip install -r requirements-dev.txt
./venv/Scripts/python -m pytest
```

Erwartet: 23 Tests, alle PASS. Unter Linux/macOS statt `venv/Scripts` entsprechend `venv/bin`.

- [ ] **Schritt 4: CI-Workflow anlegen**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        # 3.13 ist die Produktionsversion (siehe render.yaml). 3.14 laeuft
        # mit, damit lokale Entwicklung darauf nicht unbemerkt abdriftet.
        python-version: ['3.13', '3.14']
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: backend/requirements-dev.txt
      - name: Abhaengigkeiten installieren
        run: pip install -r requirements-dev.txt
      - name: Tests
        run: python -m pytest

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '24'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Abhaengigkeiten installieren
        run: npm ci
      - name: Lint
        run: npm run lint
      - name: Build
        run: npm run build
```

- [ ] **Schritt 5: Produktions-Python festnageln**

In `render.yaml` unter `envVars` ergänzen:

```yaml
      - key: PYTHON_VERSION
        value: 3.13.0
```

- [ ] **Schritt 6: Lokal gegenprüfen, was der CI prüft**

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Erwartet: beides ohne Fehler.

- [ ] **Schritt 7: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/pytest.ini .github/workflows/ci.yml render.yaml
git commit -m "chore: Abhaengigkeiten pinnen und CI-Pipeline einrichten"
```

---

## Aufgabe 2: API-Testgrundgerüst

Alle folgenden Aufgaben ändern Verhalten der API. Ohne API-Tests wären diese Änderungen unbelegt — heute gibt es ausschließlich Scheduler-Tests.

**Files:**
- Modify: `backend/db.py:12`
- Create: `backend/conftest.py`
- Create: `backend/test_api_auth.py`

**Interfaces:**
- Consumes: pytest aus Aufgabe 1
- Produces: Fixtures `client` (nicht angemeldet) und `hr_client` (als HR angemeldet), verwendbar in allen folgenden Testdateien

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`backend/test_api_auth.py` anlegen:

```python
"""Rollentrennung und Anmeldung ueber die echte HTTP-Schicht.

Bewusst gegen den Flask-Testclient statt gegen die Funktionen direkt: die
Regeln, um die es hier geht, stecken in Decorators (@hr_required) und im
Sitzungs-Handling, nicht im Funktionsrumpf.
"""


def test_erste_registrierung_legt_hr_konto_an(client):
    response = client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})

    assert response.status_code == 201
    assert response.json['role'] == 'hr'
    # Das allererste Konto wird direkt angemeldet - es gibt niemanden, der es
    # einladen koennte.
    assert response.json['auth_token']


def test_zweite_registrierung_ohne_anmeldung_wird_abgelehnt(client):
    client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})
    client.post('/logout')

    response = client.post('/register', json={'username': 'zweiter', 'email': 'z@example.com'})

    assert response.status_code == 403


def test_login_mit_falschem_passwort(hr_client):
    hr_client.post('/logout')

    response = hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'})

    assert response.status_code == 401


def test_ohne_anmeldung_kein_zugriff_auf_mitarbeiter(client):
    client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})
    client.post('/logout')

    assert client.get('/employees').status_code == 401


def test_mitarbeiterkonto_darf_die_belegschaft_nicht_lesen(hr_client):
    employee = hr_client.post('/employees', json={'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna',
        'role': 'employee',
        'employee_id': employee['id'],
    }).json

    # Ein eingeladenes Konto hat noch kein Passwort und kann sich deshalb gar
    # nicht anmelden. Die Sitzung wird direkt gesetzt: geprueft werden soll die
    # Rollenregel, nicht der Anmeldeweg.
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    response = hr_client.get('/employees')

    assert response.status_code == 403


def test_sprache_folgt_dem_x_lang_header(client):
    client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})
    client.post('/logout')

    deutsch = client.get('/employees')
    englisch = client.get('/employees', headers={'X-Lang': 'en'})

    assert deutsch.json['message'] == 'Nicht angemeldet'
    assert englisch.json['message'] == 'Not signed in'
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_api_auth.py
```

Erwartet: FAIL — `fixture 'client' not found`.

- [ ] **Schritt 3: `DB_PATH` konfigurierbar machen**

In `backend/db.py` Zeile 12 ersetzen:

```python
DB_PATH = 'schichtplan.db'
```

durch:

```python
# Ueber die Umgebung setzbar, damit Tests gegen eine eigene Wegwerf-Datei
# laufen statt gegen die Entwicklungsdatenbank.
DB_PATH = os.environ.get('SCHICHTPLAN_DB_PATH', 'schichtplan.db')
```

- [ ] **Schritt 4: Fixtures anlegen**

`backend/conftest.py`:

```python
"""Gemeinsame Fixtures fuer die API-Tests.

Jeder Test bekommt eine eigene, leere SQLite-Datei. app.py ruft init_db() beim
Import auf und haelt den Flask-App-Objekt auf Modulebene, deshalb werden `app`
und `db` pro Test frisch importiert - sonst wuerde der erste Test die Datenbank
fuer alle folgenden festlegen.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('SCHICHTPLAN_DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.setenv('SECRET_KEY', 'test-secret-nur-fuer-tests')

    for module in ('app', 'db'):
        sys.modules.pop(module, None)

    import app as app_module

    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def hr_client(client):
    """Angemeldet als das erste HR-Konto."""
    response = client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})
    assert response.status_code == 201, response.json
    return client
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: 23 Scheduler-Tests + 6 API-Tests, alle PASS.

- [ ] **Schritt 6: Commit**

```bash
git add backend/conftest.py backend/test_api_auth.py backend/db.py
git commit -m "test: API-Testgrundgeruest mit isolierter Datenbank"
```

---

## Aufgabe 3: Migrationssystem

`init_db()` flickt das Schema heute bei jedem Import mit handgeschriebenen `ALTER TABLE`-Prüfungen. Es gibt keine Version, keine Reihenfolge und keinen Weg zurück. Ohne das lässt sich Etappe 1 nicht sicher bauen.

Warum kein Alembic: siehe Spec Abschnitt 8.1.

**Files:**
- Create: `backend/migrations.py`
- Create: `backend/migrations/0001_baseline.py`
- Create: `backend/test_migrations.py`
- Modify: `backend/db.py` (`init_db()` delegiert)

**Interfaces:**
- Consumes: `db.get_db_connection()`, `db.use_postgres()`
- Produces:
  - `migrations.apply_pending() -> list[str]` — Namen der angewandten Versionen
  - `migrations.applied_versions() -> list[str]`
  - `migrations.rollback_last() -> str | None`
  - Eine Migration ist `NNNN_name.sql` (+ optional `NNNN_name.down.sql`) oder `NNNN_name.py` mit `up(cursor)` und `down(cursor)`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`backend/test_migrations.py`:

```python
"""Der Migrations-Runner.

Der Runner ist die Stelle, an der ein Fehler still Daten kostet, deshalb wird
er direkt getestet statt nur ueber die App.
"""

import sqlite3

import pytest


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    db_file = tmp_path / 'migrationen.db'
    monkeypatch.setenv('SCHICHTPLAN_DB_PATH', str(db_file))
    monkeypatch.delenv('DATABASE_URL', raising=False)

    import sys
    for module in ('db', 'migrations'):
        sys.modules.pop(module, None)

    import migrations
    return migrations, db_file


def tabellen(db_file):
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def test_frische_datenbank_bekommt_alle_tabellen(fresh_db):
    migrations, db_file = fresh_db

    angewandt = migrations.apply_pending()

    assert '0001_baseline' in angewandt
    assert {'employees', 'users', 'shift_types', 'shift_assignments',
            'schedules', 'schema_migrations'} <= tabellen(db_file)


def test_zweiter_lauf_aendert_nichts(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.apply_pending() == []


def test_angewandte_versionen_werden_protokolliert(fresh_db):
    migrations, _ = fresh_db
    migrations.apply_pending()

    assert migrations.applied_versions() == sorted(migrations.applied_versions())
    assert '0001_baseline' in migrations.applied_versions()
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_migrations.py
```

Erwartet: FAIL — `ModuleNotFoundError: No module named 'migrations'`.

- [ ] **Schritt 3: Den Runner schreiben**

`backend/migrations.py`:

```python
"""Versionierte Schemaaenderungen.

Warum kein Alembic: dieses Projekt spricht die Datenbank direkt ueber sqlite3
bzw. psycopg2 an und uebersetzt den Dialekt selbst (db.py). Alembic erwartet
eine SQLAlchemy-Engine und wuerde gegen diese Schicht arbeiten; ohne
ORM-Modelle bliebe von Alembic ohnehin kaum mehr als eine Versionstabelle
plus op.execute. Der Runner hier nutzt die vorhandene Schicht und kommt ohne
neue Abhaengigkeit aus - dieselbe Ueberlegung wie bei i18n.py gegenueber
Flask-Babel.

Eine Migration ist entweder
  NNNN_name.sql       - Anweisungen, durch Semikolon getrennt
  NNNN_name.down.sql  - optionale Ruecknahme dazu
oder
  NNNN_name.py        - mit up(cursor) und down(cursor)

SQL-Dateien duerfen den Platzhalter {auto_id} verwenden; er wird je nach
Datenbank durch SERIAL PRIMARY KEY oder INTEGER PRIMARY KEY AUTOINCREMENT
ersetzt.
"""

import importlib.util
import re
from pathlib import Path

from db import get_db_connection, use_postgres

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'

_VERSION_PATTERN = re.compile(r'^(\d{4}_[a-z0-9_]+)$')


def _placeholders():
    return {
        'auto_id': 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT',
    }


def _ensure_version_table(cursor):
    auto_id = _placeholders()['auto_id']
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schema_migrations(
            id {auto_id},
            version TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _statements(path):
    """SQL-Anweisungen einer Datei.

    Bewusst simpel: Aufteilung am Semikolon. Migrationen dieses Projekts
    enthalten keine Semikolons in Zeichenketten oder Prozedurkoerpern. Falls
    das je noetig wird, gehoert die Migration in eine .py-Datei.
    """
    text = path.read_text(encoding='utf-8').format(**_placeholders())
    return [statement.strip() for statement in text.split(';') if statement.strip()]


def _python_module(path):
    spec = importlib.util.spec_from_file_location(f'migration_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def available_versions():
    """Alle Migrationen in Anwendungsreihenfolge."""
    versions = set()
    for path in MIGRATIONS_DIR.iterdir():
        if path.suffix not in ('.sql', '.py') or path.name.startswith('__'):
            continue
        stem = path.stem.removesuffix('.down')
        if _VERSION_PATTERN.match(stem):
            versions.add(stem)
    return sorted(versions)


def _run(cursor, version, direction):
    """Wendet eine Migration in eine Richtung an. direction: 'up' oder 'down'."""
    python_path = MIGRATIONS_DIR / f'{version}.py'
    if python_path.exists():
        getattr(_python_module(python_path), direction)(cursor)
        return True

    suffix = '.sql' if direction == 'up' else '.down.sql'
    sql_path = MIGRATIONS_DIR / f'{version}{suffix}'
    if not sql_path.exists():
        return False
    for statement in _statements(sql_path):
        cursor.execute(statement)
    return True


def applied_versions():
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        connection.commit()
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version')
        return [row['version'] for row in cursor.fetchall()]
    finally:
        connection.close()


def apply_pending():
    """Wendet alle noch nicht angewandten Migrationen an, aelteste zuerst.

    Jede Migration bekommt ihre eigene Transaktion: schlaegt die dritte fehl,
    bleiben die ersten beiden angewandt und protokolliert, statt dass alles
    in einem unklaren Zwischenzustand endet.
    """
    connection = get_db_connection()
    newly_applied = []
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        connection.commit()

        cursor.execute('SELECT version FROM schema_migrations')
        already = {row['version'] for row in cursor.fetchall()}

        for version in available_versions():
            if version in already:
                continue
            try:
                _run(cursor, version, 'up')
                cursor.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            newly_applied.append(version)
        return newly_applied
    finally:
        connection.close()


def rollback_last():
    """Nimmt die zuletzt angewandte Migration zurueck. Gibt deren Namen zurueck."""
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version DESC')
        rows = cursor.fetchall()
        if not rows:
            return None

        version = rows[0]['version']
        try:
            if not _run(cursor, version, 'down'):
                raise RuntimeError(f'Migration {version} hat keine Ruecknahme')
            cursor.execute('DELETE FROM schema_migrations WHERE version = ?', (version,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return version
    finally:
        connection.close()


if __name__ == '__main__':
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else 'up'
    if command == 'up':
        applied = apply_pending()
        print('Angewandt:', ', '.join(applied) if applied else 'nichts offen')
    elif command == 'down':
        print('Zurueckgerollt:', rollback_last() or 'nichts angewandt')
    elif command == 'status':
        applied = set(applied_versions())
        for version in available_versions():
            print(('[x] ' if version in applied else '[ ] ') + version)
    else:
        print('Verwendung: python migrations.py [up|down|status]')
        sys.exit(1)
```

- [ ] **Schritt 4: Die Ausgangsmigration anlegen**

`backend/migrations/0001_baseline.py` — der heutige `init_db()`-Rumpf, unverändert übernommen. Das ist bewusst eine Python- und keine SQL-Migration: die bedingten `ALTER TABLE`-Ergänzungen brauchen die `table_columns()`-Abfrage, und eine bereits laufende Produktionsdatenbank muss sie fehlerfrei überstehen.

```python
"""Ausgangsschema.

Wortgleich der bisherige init_db()-Rumpf aus db.py. Alle CREATE-Anweisungen
sind IF NOT EXISTS und die Spaltenergaenzungen sind bedingt, deshalb ist diese
Migration auf einer bestehenden Produktionsdatenbank ein reiner No-op, der nur
die Version protokolliert.

Ab 0002 sind Migrationen einfache SQL-Dateien.
"""

from db import table_columns, use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    auto_id = _auto_id()

    # HIER den vollstaendigen Inhalt von db.py's init_db() zwischen
    # `cursor = connection.cursor()` und `connection.commit()` einfuegen,
    # unveraendert bis auf: AUTO_ID -> auto_id.
    ...


def down(cursor):
    """Es gibt keinen Weg hinter das Ausgangsschema zurueck."""
    raise RuntimeError('Das Ausgangsschema kann nicht zurueckgerollt werden')
```

> **Wichtig für den Bearbeiter:** Das `...` oben ist der einzige Platzhalter in diesem Plan und **muss** durch den echten Inhalt ersetzt werden. Öffne `backend/db.py`, kopiere alles aus `init_db()` zwischen `cursor = connection.cursor()` (Zeile 111) und `connection.commit()` (Zeile 320) hierher, und ersetze jedes `{AUTO_ID}` durch `{auto_id}`. Nichts inhaltlich ändern — Kommentare mitnehmen. Kopieren statt neu schreiben ist hier Absicht: das Schema ist über mehrere Versionen gewachsen, und jede Abweichung wäre ein stiller Datenfehler. `table_columns` wird von den bedingten `ALTER TABLE`-Zweigen gebraucht und ist oben schon importiert.

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_migrations.py
```

Erwartet: 3 Tests PASS.

- [ ] **Schritt 6: `init_db()` an den Runner übergeben**

In `backend/db.py` den kompletten `init_db()`-Rumpf ersetzen durch:

```python
def init_db():
    """Bringt das Schema auf den aktuellen Stand.

    Der eigentliche Inhalt liegt jetzt in backend/migrations/ - siehe
    migrations.py. Diese Funktion bleibt als Einstiegspunkt bestehen, damit
    app.py sich nicht aendern muss.
    """
    from migrations import apply_pending
    apply_pending()
```

Der Import steht bewusst *in* der Funktion: `migrations.py` importiert seinerseits aus `db.py`, ein Import auf Modulebene wäre zirkulär.

- [ ] **Schritt 7: `conftest.py` nachziehen**

In `backend/conftest.py` die Liste der zurückgesetzten Module erweitern:

```python
    for module in ('app', 'db', 'migrations'):
        sys.modules.pop(module, None)
```

Das ist nicht kosmetisch: `migrations.py` bindet mit `from db import get_db_connection` das Funktionsobjekt des *damaligen* `db`-Moduls. Bliebe `migrations` zwischen zwei Tests im Cache, läse dieses alte Funktionsobjekt weiterhin `DB_PATH` aus dem alten Modul — der zweite Test schriebe in die Datenbank des ersten.

- [ ] **Schritt 8: Gesamte Suite laufen lassen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle Tests PASS, insbesondere die 6 API-Tests aus Aufgabe 2 — die belegen, dass die App über den neuen Weg immer noch ein vollständiges Schema bekommt.

- [ ] **Schritt 9: Commit**

```bash
git add backend/migrations.py backend/migrations/ backend/test_migrations.py backend/db.py backend/conftest.py
git commit -m "feat: versionierte Datenbankmigrationen statt init_db-Flickwerk"
```

---

## Aufgabe 4: Indizes und UNIQUE-Constraint

`shift_assignments` wird bei jeder Warnungsprüfung nach `(date, employee_id)` durchsucht — heute ohne Index. Und nichts hindert zwei Zeilen daran, denselben Platz zu belegen.

**Files:**
- Create: `backend/migrations/0002_indexes.sql`
- Create: `backend/migrations/0002_indexes.down.sql`
- Modify: `backend/test_migrations.py`

**Interfaces:**
- Consumes: Runner aus Aufgabe 3
- Produces: Indizes `ix_assignments_date_employee`, `ix_assignments_schedule`, `ix_absences_date`; UNIQUE-Index `ux_assignment_slot`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `backend/test_migrations.py` anhängen:

```python
def indizes(db_file):
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def test_indizes_werden_angelegt(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    assert {'ix_assignments_date_employee', 'ix_assignments_schedule',
            'ix_absences_date', 'ux_assignment_slot'} <= indizes(db_file)


def test_derselbe_platz_kann_nicht_doppelt_belegt_werden(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    connection = sqlite3.connect(db_file)
    try:
        connection.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 3, 'generated')")
        connection.execute(
            "INSERT INTO shift_types (name, start_time, end_time) VALUES ('Frueh', '06:00', '14:00')")
        for _ in range(2):
            connection.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index) '
                'VALUES (1, ?, 1, 0)', ('2026-03-02',))
        with pytest.raises(sqlite3.IntegrityError):
            connection.commit()
    finally:
        connection.close()


def test_indexmigration_laesst_sich_zurueckrollen(fresh_db):
    migrations, db_file = fresh_db
    migrations.apply_pending()

    # Nicht auf "die letzte Migration" verlassen: spaetere Aufgaben haengen
    # weitere Migrationen hinten an, und dieser Test soll davon unberuehrt
    # bleiben. Stattdessen zurueckrollen, bis 0002 weg ist.
    while '0002_indexes' in migrations.applied_versions():
        migrations.rollback_last()

    assert 'ix_assignments_date_employee' not in indizes(db_file)
    assert '0002_indexes' not in migrations.applied_versions()
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_migrations.py
```

Erwartet: die drei neuen Tests FAIL, die drei aus Aufgabe 3 weiterhin PASS.

- [ ] **Schritt 3: Migration schreiben**

`backend/migrations/0002_indexes.sql`:

```sql
-- shift_assignments wird bei jeder Warnungspruefung nach (date, employee_id)
-- durchsucht (constraint_warnings in app.py) und beim Laden eines Monats nach
-- schedule_id. Beides ohne Index.
CREATE INDEX IF NOT EXISTS ix_assignments_date_employee
    ON shift_assignments(date, employee_id);

CREATE INDEX IF NOT EXISTS ix_assignments_schedule
    ON shift_assignments(schedule_id);

CREATE INDEX IF NOT EXISTS ix_absences_date
    ON employee_absences(date);

-- Ein Platz ist durch (Plan, Datum, Schichtart, Index) eindeutig bestimmt.
-- Bisher hielt nur die Anwendungslogik das ein.
CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot
    ON shift_assignments(schedule_id, date, shift_type_id, slot_index)
```

`backend/migrations/0002_indexes.down.sql`:

```sql
DROP INDEX IF EXISTS ux_assignment_slot;
DROP INDEX IF EXISTS ix_absences_date;
DROP INDEX IF EXISTS ix_assignments_schedule;
DROP INDEX IF EXISTS ix_assignments_date_employee
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

> **Falls `test_derselbe_platz_kann_nicht_doppelt_belegt_werden` beim ersten Anlauf durchgeht statt zu scheitern:** dann existieren im Test noch keine kollidierenden Zeilen — prüfe, dass beide INSERTs wirklich identische `(schedule_id, date, shift_type_id, slot_index)` haben.

> **Falls die Migration auf der Produktionsdatenbank scheitert,** weil dort bereits doppelte Plätze liegen: vor dem Deploy mit
> `SELECT schedule_id, date, shift_type_id, slot_index, COUNT(*) FROM shift_assignments GROUP BY 1,2,3,4 HAVING COUNT(*) > 1;`
> prüfen und die Duplikate von Hand bereinigen. Der UNIQUE-Index wird sonst nicht angelegt.

- [ ] **Schritt 5: Commit**

```bash
git add backend/migrations/0002_indexes.sql backend/migrations/0002_indexes.down.sql backend/test_migrations.py
git commit -m "feat: Indizes und Eindeutigkeit fuer shift_assignments"
```

---

## Aufgabe 5: SECRET_KEY-Härtung und Security-Header

`app.secret_key` fällt heute still auf `'schichtplan-local-dev'` zurück. Fehlt die Variable in Produktion, kann jeder gültige Bearer-Token signieren — der Wert steht öffentlich im Quelltext.

**Files:**
- Create: `backend/security.py`
- Create: `backend/test_api_security.py`
- Modify: `backend/app.py:19` und Bereich nach `init_db()`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `security.resolve_secret_key() -> str` — wirft `RuntimeError` in Produktion ohne Wert
  - `security.register_security_headers(app) -> None`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`backend/test_api_security.py`:

```python
"""Absicherung der HTTP-Schicht: Schluesselpflicht und Antwort-Header."""

import pytest


def test_produktion_ohne_secret_key_startet_nicht(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)

    import sys
    sys.modules.pop('security', None)
    import security

    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        security.resolve_secret_key()


def test_lokal_ohne_secret_key_ist_erlaubt(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('SECRET_KEY', raising=False)

    import sys
    sys.modules.pop('security', None)
    import security

    assert security.resolve_secret_key()


def test_antworten_tragen_security_header(client):
    response = client.get('/')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_hsts_nur_in_produktion(client):
    # Die client-Fixture entfernt FLASK_ENV, das ist also der lokale Fall.
    assert 'Strict-Transport-Security' not in client.get('/').headers
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_api_security.py
```

Erwartet: FAIL — `ModuleNotFoundError: No module named 'security'`.

- [ ] **Schritt 3: `security.py` schreiben**

```python
"""Absicherung der HTTP-Schicht.

Zwei Dinge, die nichts mit Fachlogik zu tun haben und deshalb nicht in app.py
gehoeren: die Pflicht zu einem echten Signierschluessel und die Header, die
jede Antwort tragen soll.
"""

import os

# Nur fuer lokale Entwicklung. Der Wert steht im oeffentlichen Quelltext und
# ist damit kein Geheimnis - in Produktion wird er deshalb verweigert.
DEV_SECRET_KEY = 'schichtplan-local-dev'

SECURITY_HEADERS = {
    # Verhindert, dass ein Browser den Inhaltstyp einer Antwort errät.
    'X-Content-Type-Options': 'nosniff',
    # Diese API gehoert in keinen fremden Rahmen.
    'X-Frame-Options': 'DENY',
    # Keine Pfade oder Query-Parameter an fremde Seiten weitergeben.
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Opener-Policy': 'same-origin',
}


def is_production():
    return os.environ.get('FLASK_ENV') == 'production'


def resolve_secret_key():
    """Der Schluessel fuer Sitzungscookie und Bearer-Token.

    Faellt lokal auf einen festen Entwicklungswert zurueck, verweigert in
    Produktion aber den Start: mit einem bekannten Schluessel kann jeder
    gueltige Anmeldetoken erzeugen, und ein stiller Fallback ist genau die
    Art Fehler, die niemandem auffaellt.
    """
    secret = os.environ.get('SECRET_KEY')
    if secret:
        return secret
    if is_production():
        raise RuntimeError(
            'SECRET_KEY muss in der Produktionsumgebung gesetzt sein. Er signiert '
            'Sitzungscookie und Bearer-Token; der Entwicklungswert steht im Quelltext.'
        )
    return DEV_SECRET_KEY


def register_security_headers(app):
    """Haengt die Header an jede Antwort.

    Keine Content-Security-Policy: diese Anwendung liefert ausschliesslich
    JSON aus. Die CSP gehoert vor das Frontend (Vercel), nicht hierher.
    """
    @app.after_request
    def _add_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if is_production():
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response
```

- [ ] **Schritt 4: In `app.py` einhängen**

Zeile 19 ersetzen:

```python
app.secret_key = os.environ.get('SECRET_KEY', 'schichtplan-local-dev')
```

durch:

```python
app.secret_key = security.resolve_secret_key()
```

Import bei den übrigen lokalen Imports ergänzen (nach `import mailer`):

```python
import security
```

Und direkt nach dem `CORS(...)`-Block, vor `init_db()`:

```python
security.register_security_headers(app)
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

- [ ] **Schritt 6: Commit**

```bash
git add backend/security.py backend/test_api_security.py backend/app.py
git commit -m "feat: SECRET_KEY in Produktion erzwingen und Security-Header setzen"
```

---

## Aufgabe 6: Login-Drosselung

`/login` nimmt heute unbegrenzt viele Versuche an. Ebenso `/invitations/<token>`, wo ein Treffer direkt ein Konto übernimmt.

Warum keine Bibliothek: siehe Spec Abschnitt 8.1.

**Files:**
- Create: `backend/migrations/0003_login_attempts.sql`
- Create: `backend/migrations/0003_login_attempts.down.sql`
- Modify: `backend/security.py`
- Modify: `backend/app.py` (`login()`, `redeem_invitation()`)
- Modify: `backend/i18n.py`
- Modify: `backend/test_api_security.py`

**Interfaces:**
- Consumes: Runner aus Aufgabe 3, `security.py` aus Aufgabe 5
- Produces:
  - `security.MAX_FAILED_ATTEMPTS = 10`, `security.ATTEMPT_WINDOW_MINUTES = 15`
  - `security.is_locked_out(cursor, identifier) -> bool` — die Sperre gilt pro Benutzername, die IP wird nur protokolliert
  - `security.record_attempt(cursor, identifier, ip, succeeded) -> None`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `backend/test_api_security.py` anhängen:

```python
def test_zu_viele_fehlversuche_werden_gesperrt(hr_client):
    hr_client.post('/logout')

    for _ in range(10):
        assert hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'}).status_code == 401

    gesperrt = hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'})
    assert gesperrt.status_code == 429

    # Auch das richtige Passwort kommt waehrend der Sperre nicht durch -
    # sonst waere die Drosselung als Bremse wertlos.
    assert hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'}).status_code == 429


def test_erfolgreiche_anmeldung_setzt_den_zaehler_zurueck(hr_client):
    hr_client.post('/logout')

    for _ in range(9):
        hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'})

    assert hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'}).status_code == 200

    # Nach dem Zuruecksetzen sind wieder zehn Versuche frei.
    hr_client.post('/logout')
    for _ in range(9):
        assert hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'}).status_code == 401


def test_ein_anderer_benutzername_ist_nicht_mitgesperrt(hr_client):
    hr_client.post('/logout')
    for _ in range(11):
        hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'})

    # 401 (unbekannter Benutzer), nicht 429 - die Sperre gilt pro Benutzername.
    assert hr_client.post('/login', json={'username': 'jemand', 'password': 'x'}).status_code == 401


def test_sperrmeldung_kommt_in_der_angeforderten_sprache(hr_client):
    hr_client.post('/logout')
    for _ in range(11):
        hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'})

    antwort = hr_client.post('/login', json={'username': 'hr', 'password': 'falsch'},
                             headers={'X-Lang': 'en'})
    assert 'too many' in antwort.json['message'].lower()
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_api_security.py
```

Erwartet: die vier neuen Tests FAIL (jeweils `401 != 429` bzw. `KeyError`).

- [ ] **Schritt 3: Migration schreiben**

`backend/migrations/0003_login_attempts.sql`:

```sql
-- Anmeldeversuche, um Passwortraten auszubremsen.
--
-- In der Datenbank statt im Arbeitsspeicher: der Zaehler muss einen Neustart
-- ueberleben und ueber mehrere Gunicorn-Worker hinweg derselbe sein. Das ist
-- ausserdem der erste Baustein des Audit-Logs aus Etappe 5.
--
-- attempted_at ist TEXT im ISO-Format, nicht TIMESTAMP: so laesst es sich in
-- SQLite und Postgres identisch mit einem in Python gerechneten Grenzwert
-- vergleichen. password_invitations.expires_at macht es genauso.
CREATE TABLE IF NOT EXISTS login_attempts(
    id {auto_id},
    identifier TEXT NOT NULL,
    ip TEXT NOT NULL,
    succeeded INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_login_attempts_lookup
    ON login_attempts(identifier, attempted_at)
```

`backend/migrations/0003_login_attempts.down.sql`:

```sql
DROP INDEX IF EXISTS ix_login_attempts_lookup;
DROP TABLE IF EXISTS login_attempts
```

- [ ] **Schritt 4: Drosselung in `security.py` ergänzen**

Am Kopf der Datei ergänzen:

```python
from datetime import datetime, timedelta, timezone
```

Und ans Ende anhängen:

```python
# Zehn Versuche in einer Viertelstunde: hoch genug, dass ein vertippter Mensch
# nie dagegen laeuft, niedrig genug, dass Raten unbrauchbar langsam wird.
MAX_FAILED_ATTEMPTS = 10
ATTEMPT_WINDOW_MINUTES = 15


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _window_start_iso():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)
    return cutoff.isoformat(timespec='seconds')


def is_locked_out(cursor, identifier):
    """Sind fuer diesen Benutzernamen zu viele Fehlversuche im Zeitfenster?

    Die Sperre gilt pro Benutzername, nicht pro IP: eine IP-Sperre trifft bei
    einem Buero hinter einem gemeinsamen Anschluss alle Kolleginnen und
    Kollegen mit, und ein Angreifer mit wechselnden Adressen umgeht sie
    ohnehin. Sie blockiert waehrend der Sperre auch das richtige Passwort -
    sonst waere sie als Bremse wirkungslos.
    """
    cursor.execute(
        'SELECT COUNT(*) AS n FROM login_attempts '
        'WHERE identifier = ? AND succeeded = 0 AND attempted_at >= ?',
        (identifier, _window_start_iso()),
    )
    return cursor.fetchone()['n'] >= MAX_FAILED_ATTEMPTS


def record_attempt(cursor, identifier, ip, succeeded):
    """Protokolliert einen Versuch. Ein Erfolg loescht die Fehlversuche davor."""
    if succeeded:
        cursor.execute('DELETE FROM login_attempts WHERE identifier = ?', (identifier,))
    cursor.execute(
        'INSERT INTO login_attempts (identifier, ip, succeeded, attempted_at) VALUES (?, ?, ?, ?)',
        (identifier, ip or 'unbekannt', 1 if succeeded else 0, _now_iso()),
    )
    # Gelegenheitsaufraeumen: alles ausserhalb des Zeitfensters ist wertlos.
    cursor.execute('DELETE FROM login_attempts WHERE attempted_at < ?', (_window_start_iso(),))
```

- [ ] **Schritt 5: Meldungsschlüssel ergänzen**

In `backend/i18n.py` im `TRANSLATIONS`-Dictionary bei den Auth-Meldungen ergänzen:

```python
    'too_many_login_attempts': {
        'de': 'Zu viele fehlgeschlagene Anmeldeversuche. Bitte in {minutes} Minuten erneut versuchen.',
        'en': 'Too many failed sign-in attempts. Please try again in {minutes} minutes.',
    },
```

- [ ] **Schritt 6: `login()` umbauen**

In `backend/app.py` die Funktion `login()` ersetzen durch:

```python
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    connection = get_db()
    cursor = connection.cursor()

    if username and security.is_locked_out(cursor, username):
        return jsonify({'message': t(g.lang, 'too_many_login_attempts',
                                     minutes=security.ATTEMPT_WINDOW_MINUTES)}), 429

    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()

    # An invited account has no password yet. Saying so is safe - the invitation
    # went to that person's mailbox, not to whoever is guessing here - and it is
    # far more useful than "wrong password" to someone who never set one.
    if user and not user['hash']:
        return jsonify({'message': t(g.lang, 'password_not_set_yet')}), 403

    # Same message either way, so the response cannot be used to find out which
    # usernames exist.
    if not user or not check_password_hash(user['hash'], password):
        if username:
            security.record_attempt(cursor, username, request.remote_addr, succeeded=False)
            connection.commit()
        return jsonify({'message': t(g.lang, 'login_failed')}), 401

    security.record_attempt(cursor, username, request.remote_addr, succeeded=True)
    connection.commit()

    session.clear()
    session['user_id'] = user['id']
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
        'auth_token': issue_auth_token(user['id']),
    }), 200
```

- [ ] **Schritt 7: `redeem_invitation()` drosseln**

In `backend/app.py` in `redeem_invitation(token)` direkt nach `cursor = connection.cursor()` einfügen:

```python
    # Ein Treffer hier uebernimmt ein Konto, also wird auch das Einloesen
    # gedrosselt. Gezaehlt wird pro Token, nicht pro Konto - welches Konto
    # gemeint ist, weiss man ohne gueltigen Token gar nicht.
    attempt_key = f'invitation:{hash_token(token)}'
    if security.is_locked_out(cursor, attempt_key):
        return jsonify({'message': t(g.lang, 'too_many_login_attempts',
                                     minutes=security.ATTEMPT_WINDOW_MINUTES)}), 429
```

Und im Zweig `if not invitation:` **vor** dem `return`:

```python
        security.record_attempt(cursor, attempt_key, request.remote_addr, succeeded=False)
        connection.commit()
```

- [ ] **Schritt 8: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

- [ ] **Schritt 9: Commit**

```bash
git add backend/migrations/0003_login_attempts.sql backend/migrations/0003_login_attempts.down.sql backend/security.py backend/app.py backend/i18n.py backend/test_api_security.py
git commit -m "feat: Anmeldeversuche drosseln"
```

---

## Aufgabe 7: Globaler Fehler-Handler und Logging

Ein unerwarteter Fehler liefert heute Flasks HTML-Fehlerseite. Das Frontend versucht sie als JSON zu lesen, scheitert und zeigt „unerwartete Antwort" — eine Meldung, die auf eine falsche Fährte führt (siehe `frontend/src/api.js`, `parseFailed`).

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/i18n.py`
- Modify: `backend/test_api_security.py`

**Interfaces:**
- Consumes: `security.is_production()` aus Aufgabe 5
- Produces: Jede Fehlerantwort ist JSON mit `message`; unerwartete Fehler zusätzlich mit `request_id`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `backend/test_api_security.py` anhängen:

```python
def test_unbekannte_route_liefert_json(client):
    response = client.get('/gibt-es-nicht')

    assert response.status_code == 404
    assert response.is_json
    assert response.json['message']


def test_falsche_methode_liefert_json(client):
    response = client.delete('/login')

    assert response.status_code == 405
    assert response.is_json


def test_unerwarteter_fehler_liefert_json_mit_request_id(client, monkeypatch):
    import app as app_module

    def kaputt():
        raise RuntimeError('absichtlich')

    monkeypatch.setitem(app_module.app.view_functions, 'index', kaputt)
    # Flask reicht Ausnahmen im Testmodus sonst durch, statt sie zu behandeln.
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = False

    response = client.get('/')

    assert response.status_code == 500
    assert response.is_json
    assert response.json['request_id']
    # Kein Stacktrace nach aussen.
    assert 'absichtlich' not in response.get_data(as_text=True)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_api_security.py
```

Erwartet: die drei neuen Tests FAIL — die Antworten sind HTML, nicht JSON.

- [ ] **Schritt 3: Meldungsschlüssel ergänzen**

In `backend/i18n.py`:

```python
    'server_error': {
        'de': 'Unerwarteter Serverfehler. Bitte erneut versuchen.',
        'en': 'Unexpected server error. Please try again.',
    },
    'not_found': {
        'de': 'Diese Adresse gibt es nicht',
        'en': 'This address does not exist',
    },
    'method_not_allowed': {
        'de': 'Diese Methode ist hier nicht erlaubt',
        'en': 'This method is not allowed here',
    },
```

- [ ] **Schritt 4: Handler und Logging in `app.py` einbauen**

Imports ergänzen:

```python
import logging
import uuid

from werkzeug.exceptions import HTTPException
```

Den `before_request`-Hook `resolve_request_lang` erweitern:

```python
@app.before_request
def resolve_request_lang():
    """The language of this one request, read fresh every time (never stored)
    from the header frontend/src/api.js sends on every call. Every message
    this API returns goes through t(g.lang, ...) rather than a hardcoded
    string - see i18n.py.
    """
    g.lang = resolve_lang(request.headers.get('X-Lang', DEFAULT_LANG))
    # Kurze Kennung, die in der Fehlerantwort und im Log steht, damit eine
    # Nutzermeldung ("Fehler a1b2c3d4") im Protokoll wiederfindbar ist.
    g.request_id = uuid.uuid4().hex[:8]
```

Und vor `@app.route('/')` am Dateiende einfügen:

```python
# ---------- error handling ----------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)


def _request_lang():
    """g.lang, oder die Standardsprache falls der before_request-Hook nie lief."""
    return getattr(g, 'lang', DEFAULT_LANG)


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    """Flasks eigene Fehler (404, 405, 413 ...) als JSON statt als HTML.

    Ohne das bekommt frontend/src/api.js eine HTML-Seite mit Fehlerstatus,
    scheitert beim Parsen und meldet "unerwartete Antwort" - was nach einer
    falsch konfigurierten API-URL aussieht statt nach dem, was wirklich war.
    """
    keys = {404: 'not_found', 405: 'method_not_allowed'}
    key = keys.get(error.code)
    message = t(_request_lang(), key) if key else (error.description or error.name)
    return jsonify({'message': message}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Alles, was sonst als Stacktrace beim Nutzer landen wuerde.

    Die Kennung geht an den Aufrufer, der Grund nur ins Protokoll - eine
    Ausnahmemeldung kann Tabellen-, Spalten- oder Dateinamen enthalten.
    """
    request_id = getattr(g, 'request_id', '-')
    app.logger.exception(
        'Unbehandelter Fehler [%s] %s %s', request_id, request.method, request.path)
    return jsonify({
        'message': t(_request_lang(), 'server_error'),
        'request_id': request_id,
    }), 500
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

- [ ] **Schritt 6: Commit**

```bash
git add backend/app.py backend/i18n.py backend/test_api_security.py
git commit -m "feat: Fehlerantworten immer als JSON, mit nachverfolgbarer Kennung"
```

---

## Aufgabe 8: Zeitzone Europe/Berlin

`current_month_bounds()` und `list_absences()` nutzen `date.today()` — auf Render ist das UTC. Am Monatsersten zwischen 00:00 und 02:00 deutscher Zeit hält der Server noch den Vormonat für aktuell und weist die Krankmeldung eines Mitarbeiters ab.

**Files:**
- Create: `backend/timeutil.py`
- Create: `backend/test_timeutil.py`
- Modify: `backend/app.py` (`current_month_bounds`, `list_absences`)
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `timeutil.today_local() -> datetime.date`
  - `timeutil.month_bounds(day: date) -> tuple[str, str]` — reine Funktion, testbar mit festen Daten
  - `timeutil.timezone_name() -> str` — der konfigurierte Zonenname, mit Rückfall auf `Europe/Berlin`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`backend/test_timeutil.py`:

```python
"""Monatsgrenzen und lokale Zeitzone.

month_bounds() ist bewusst eine reine Funktion: so laesst sich das Verhalten
an Monatsraendern mit festen Daten pruefen, ohne die Uhr zu manipulieren.
"""

from datetime import date


def test_monatsgrenzen_eines_langen_monats():
    from timeutil import month_bounds

    assert month_bounds(date(2026, 3, 17)) == ('2026-03-01', '2026-03-31')


def test_monatsgrenzen_eines_kurzen_monats():
    from timeutil import month_bounds

    assert month_bounds(date(2026, 2, 1)) == ('2026-02-01', '2026-02-28')


def test_monatsgrenzen_im_schaltjahr():
    from timeutil import month_bounds

    assert month_bounds(date(2028, 2, 29)) == ('2028-02-01', '2028-02-29')


def test_lokales_datum_folgt_der_konfigurierten_zeitzone(monkeypatch):
    import sys
    monkeypatch.setenv('APP_TIMEZONE', 'Pacific/Kiritimati')
    sys.modules.pop('timeutil', None)
    import timeutil
    kiritimati = timeutil.today_local()

    monkeypatch.setenv('APP_TIMEZONE', 'Pacific/Niue')
    sys.modules.pop('timeutil', None)
    import timeutil as timeutil_niue
    niue = timeutil_niue.today_local()

    # 25 Stunden Zeitunterschied - die beiden koennen nie derselbe Tag sein.
    assert kiritimati != niue


def test_unbekannte_zeitzone_faellt_auf_berlin_zurueck(monkeypatch):
    import sys
    monkeypatch.setenv('APP_TIMEZONE', 'Nicht/Existent')
    sys.modules.pop('timeutil', None)
    import timeutil

    assert timeutil.timezone_name() == 'Europe/Berlin'
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_timeutil.py
```

Erwartet: FAIL — `ModuleNotFoundError: No module named 'timeutil'`.

- [ ] **Schritt 3: `timeutil.py` schreiben**

```python
"""Lokales Datum und Monatsgrenzen.

Warum ueberhaupt: "der aktuelle Monat" entscheidet, ob ein Mitarbeiterkonto
eine Krankmeldung eintragen darf. date.today() liefert das Datum der
Serverzeitzone - auf einem Hoster ist das UTC. Am Monatsersten zwischen 00:00
und 02:00 deutscher Zeit haelt der Server dann noch den Vormonat fuer aktuell
und weist die Meldung ab.
"""

import calendar
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = 'Europe/Berlin'


def timezone_name():
    """Der konfigurierte Zonenname, oder Berlin falls er unbekannt ist.

    Ein Tippfehler in der Umgebungsvariablen soll den Start nicht verhindern -
    eine falsche Zone ist ein Schoenheitsfehler, eine nicht startende
    Anwendung ist ein Ausfall.
    """
    name = os.environ.get('APP_TIMEZONE', DEFAULT_TIMEZONE)
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TIMEZONE
    return name


def today_local():
    """Das Datum, das gerade am Betriebsstandort gilt."""
    return datetime.now(ZoneInfo(timezone_name())).date()


def month_bounds(day):
    """Erster und letzter Tag des Monats, in dem `day` liegt, als ISO-Strings."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1).isoformat(), day.replace(day=last_day).isoformat()
```

- [ ] **Schritt 4: In `app.py` verwenden**

Import ergänzen:

```python
import timeutil
```

`current_month_bounds()` ersetzen durch:

```python
def current_month_bounds():
    """The server's own idea of "this month", as (first day, last day) ISO strings.

    Never derived from client input - self-service reporting is only ever
    allowed for the month the server's clock says it is right now. Die Zone
    kommt aus timeutil, nicht aus der Serverzeitzone: siehe dortiger
    Modulkommentar.
    """
    return timeutil.month_bounds(timeutil.today_local())
```

In `list_absences()` beide Vorkommen ersetzen:

```python
        year = int(request.args['year']) if 'year' in request.args else date.today().year
        month = int(request.args['month']) if 'month' in request.args else date.today().month
```

durch:

```python
        heute = timeutil.today_local()
        year = int(request.args['year']) if 'year' in request.args else heute.year
        month = int(request.args['month']) if 'month' in request.args else heute.month
```

- [ ] **Schritt 5: Umgebungsvariable dokumentieren**

An `backend/.env.example` anhängen:

```
# Zeitzone des Betriebs. Bestimmt, welcher Monat als "aktuell" gilt, wenn ein
# Mitarbeiterkonto Krankheit oder Urlaub meldet. Standard: Europe/Berlin.
APP_TIMEZONE=Europe/Berlin
```

- [ ] **Schritt 6: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

- [ ] **Schritt 7: Commit**

```bash
git add backend/timeutil.py backend/test_timeutil.py backend/app.py backend/.env.example
git commit -m "fix: aktuellen Monat in der Betriebszeitzone bestimmen statt in UTC"
```

---

## Aufgabe 9: Schutz vor dem Überschreiben von Handkorrekturen

`POST /schedules/generate` löscht heute wortlos alle Zuweisungen des Monats — auch jede, die HR von Hand gesetzt hat. Es gibt keine Rückfrage und kein Zurück.

**Files:**
- Modify: `backend/app.py` (`generate_schedule_route`)
- Modify: `backend/i18n.py`
- Create: `backend/test_api_schedules.py`
- Modify: `frontend/src/pages/SchedulePage.jsx`
- Modify: `frontend/src/i18n/translations.js`

**Interfaces:**
- Consumes: `hr_client`-Fixture aus Aufgabe 2
- Produces: `POST /schedules/generate` antwortet mit `409` und `{message, manually_edited_count}`, wenn Handkorrekturen bestehen und `confirm` nicht `true` ist

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`backend/test_api_schedules.py`:

```python
"""Planerzeugung: Schutz vor stillem Datenverlust."""


def plan_vorbereiten(hr_client):
    """Ein Mitarbeiter, eine Schichtart, ein erzeugter Maerzplan."""
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Frueh',
        'start_time': '06:00',
        'end_time': '14:00',
        'requirements': [1, 1, 1, 1, 1, 0, 0],
    })
    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})
    assert antwort.status_code == 201, antwort.json
    return antwort.json


def test_erzeugen_ohne_handkorrekturen_laeuft_durch(hr_client):
    plan_vorbereiten(hr_client)

    erneut = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})

    assert erneut.status_code == 201


def test_erzeugen_mit_handkorrekturen_fragt_nach(hr_client):
    plan = plan_vorbereiten(hr_client)
    erste = plan['assignments'][0]
    assert hr_client.put(f'/assignments/{erste["id"]}', json={'employee_id': None}).status_code == 200

    erneut = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})

    assert erneut.status_code == 409
    assert erneut.json['manually_edited_count'] == 1


def test_bestaetigtes_erzeugen_ueberschreibt(hr_client):
    plan = plan_vorbereiten(hr_client)
    erste = plan['assignments'][0]
    hr_client.put(f'/assignments/{erste["id"]}', json={'employee_id': None})

    erneut = hr_client.post('/schedules/generate',
                            json={'year': 2026, 'month': 3, 'confirm': True})

    assert erneut.status_code == 201
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest test_api_schedules.py
```

Erwartet: `test_erzeugen_mit_handkorrekturen_fragt_nach` FAIL mit `201 != 409`, die beiden anderen PASS.

- [ ] **Schritt 3: Meldungsschlüssel ergänzen**

In `backend/i18n.py`:

```python
    'regenerate_would_discard_edits': {
        'de': 'Der Plan enthaelt {n} von Hand bearbeitete Schichten, die beim '
              'Neuerzeugen verloren gehen. Zum Fortfahren bestaetigen.',
        'en': 'The schedule contains {n} manually edited shifts that would be lost '
              'by regenerating. Confirm to continue.',
    },
```

- [ ] **Schritt 4: Prüfung in `generate_schedule_route()` einbauen**

In `backend/app.py`, direkt nach dem Block, der `existing` ermittelt, und **vor** dem `DELETE FROM shift_assignments`:

```python
    if existing:
        schedule_id = existing['id']
        # Neuerzeugen verwirft jede Zuweisung des Monats, auch die von Hand
        # gesetzten. Ohne Rueckfrage waere das ein Klick, der stunden- bis
        # tagelange Nacharbeit still loescht - und es gibt kein Zurueck.
        cursor.execute(
            'SELECT COUNT(*) AS n FROM shift_assignments '
            'WHERE schedule_id = ? AND manually_edited = 1',
            (schedule_id,),
        )
        manually_edited = cursor.fetchone()['n']
        if manually_edited and not data.get('confirm'):
            return jsonify({
                'message': t(g.lang, 'regenerate_would_discard_edits', n=manually_edited),
                'manually_edited_count': manually_edited,
            }), 409

        cursor.execute('DELETE FROM shift_assignments WHERE schedule_id = ?', (schedule_id,))
```

Der Rest des Zweigs (`UPDATE schedules SET status = 'generated' ...`) bleibt unverändert.

> **Achtung:** Der `generate_schedule(...)`-Aufruf steht heute **vor** dieser Stelle. Er ist ein reiner Rechenschritt ohne Schreibzugriff, die Rückfrage bleibt also korrekt — sie kostet nur einen unnötigen Suchlauf. Wer das sauberer will, verschiebt die Zählung vor den `generate_schedule`-Aufruf; dafür muss `existing` dann ebenfalls vorher ermittelt werden.

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

```bash
cd backend
./venv/Scripts/python -m pytest
```

Erwartet: alle PASS.

- [ ] **Schritt 6: Frontend-Texte ergänzen**

In `frontend/src/i18n/translations.js` im `schedule`-Abschnitt beider Sprachen:

```js
    confirmRegenerate: 'Der Plan enthält {n} von Hand bearbeitete Schichten, die dabei verloren gehen. Trotzdem neu erzeugen?',
```

```js
    confirmRegenerate: 'The schedule contains {n} manually edited shifts that will be lost. Regenerate anyway?',
```

- [ ] **Schritt 7: Rückfrage im Frontend einbauen**

In `frontend/src/pages/SchedulePage.jsx` die Funktion, die `POST /schedules/generate` aufruft, so ergänzen, dass sie den 409 abfängt und nach Bestätigung erneut mit `confirm: true` sendet. Das Muster:

```jsx
  // Der Parameter heißt bewusst nicht `confirm`: das würde window.confirm
  // innerhalb dieser Funktion verdecken, und genau die brauchen wir unten.
  async function generate(bestaetigt = false) {
    try {
      const result = await api.post('/schedules/generate', {
        year, month, weekend_weight: weekendWeight, ...(bestaetigt ? { confirm: true } : {}),
      })
      setSchedule(result)
      setFlash({ type: 'success', text: t('schedule.flashGenerated') })
    } catch (err) {
      // Der Plan enthält Handkorrekturen - einmal nachfragen, dann bestätigt
      // wiederholen. err.data trägt manually_edited_count aus der Antwort.
      if (err.data?.manually_edited_count) {
        const weiter = window.confirm(
          t('schedule.confirmRegenerate', { n: err.data.manually_edited_count }))
        return weiter ? generate(true) : undefined
      }
      setFlash({ type: 'error', text: err.message })
    }
  }
```

Die vorhandenen Aufrufstellen von `generate` bleiben unverändert — ohne Argument ist `bestaetigt` `false`.

Damit `err.data` ankommt, muss `frontend/src/api.js` den Antwortkörper auch bei anderen Fehlerstatus als 401 mitgeben. Im `if (!response.ok)`-Block die Zeile

```js
    throw new Error(message)
```

ersetzen durch:

```js
    // Der Antwortkoerper haengt am Fehler, damit Aufrufer strukturierte
    // Zusatzangaben lesen koennen (z.B. manually_edited_count beim 409 von
    // /schedules/generate) statt die Meldung parsen zu muessen.
    const error = new Error(message)
    error.data = data
    throw error
```

- [ ] **Schritt 8: Frontend prüfen**

```bash
cd frontend
npm run lint
npm run build
```

Erwartet: beides ohne Fehler.

- [ ] **Schritt 9: Commit**

```bash
git add backend/app.py backend/i18n.py backend/test_api_schedules.py frontend/src/pages/SchedulePage.jsx frontend/src/api.js frontend/src/i18n/translations.js
git commit -m "feat: Rueckfrage bevor Neuerzeugen Handkorrekturen verwirft"
```

---

## Aufgabe 10: Betriebsdokumentation und Gunicorn-Konfiguration

Der Planer darf bis zu 8 Sekunden rechnen. Gunicorn läuft in `render.yaml` ohne Angaben — ein synchroner Worker, der in dieser Zeit niemandem sonst antwortet. Und für die Datenbank existiert kein Backup-Verfahren.

**Files:**
- Modify: `render.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: nichts
- Produces: nichts (Dokumentation und Deployment-Konfiguration)

- [ ] **Schritt 1: Gunicorn konfigurieren**

In `render.yaml` `startCommand` ersetzen:

```yaml
    startCommand: >-
      gunicorn app:app --bind 0.0.0.0:$PORT
      --workers 2 --threads 4 --timeout 60 --access-logfile -
```

Begründung als Kommentar darüber:

```yaml
    # Der Planer rechnet bis zu 8 Sekunden (DEFAULT_TIME_BUDGET_SECONDS in
    # scheduler.py). Mit einem einzigen synchronen Worker antwortet die API in
    # dieser Zeit niemandem sonst. Zwei Worker mit je vier Threads halten den
    # Rest bedienbar; --timeout 60 laesst dem Planer Luft, ohne einen wirklich
    # haengenden Worker ewig stehen zu lassen.
```

- [ ] **Schritt 2: Betriebsabschnitt ins README**

Im README nach dem Abschnitt „Deployment" einfügen:

````markdown
### Betrieb

**Migrationen.** Das Schema wird beim Start automatisch aktualisiert (`init_db()` → `migrations.apply_pending()`). Von Hand:

```bash
cd backend
./venv/bin/python migrations.py status   # was ist angewandt
./venv/bin/python migrations.py up       # offene anwenden
./venv/bin/python migrations.py down     # letzte zuruecknehmen
```

**Backup.** Renders kostenloser Postgres-Plan hat **keine Backups und wird nach 30 Tagen gelöscht.** Für echten Betrieb ist ein bezahlter Plan die Voraussetzung, nicht eine Option. Solange das nicht der Fall ist, mindestens wöchentlich von Hand sichern:

```bash
pg_dump "$DATABASE_URL" --no-owner --format=custom --file="schichtplan-$(date +%Y-%m-%d).dump"
```

Zurückspielen:

```bash
pg_restore --clean --no-owner --dbname="$DATABASE_URL" schichtplan-2026-08-16.dump
```

**Umgebungsvariablen.** Vollständige Liste in `backend/.env.example`. Zwingend in Produktion:

| Variable | Ohne sie |
|---|---|
| `SECRET_KEY` | Die Anwendung startet nicht (Absicht — mit bekanntem Schlüssel kann jeder Anmeldetoken fälschen) |
| `DATABASE_URL` | SQLite auf einem Dateisystem, das jeder Neustart leert — alle Pläne wären weg |
| `ALLOWED_ORIGINS` | Das Frontend bekommt bei jedem Aufruf einen CORS-Fehler |
| `APP_BASE_URL` | Einladungslinks zeigen auf `localhost` |
| `FLASK_ENV=production` | Kein sicheres Cookie, kein HSTS, kein Zwang zum `SECRET_KEY` |

**Fehlersuche.** Jede unerwartete Fehlerantwort enthält eine `request_id`. Dieselbe Kennung steht im Protokoll der Instanz — im Render-Dashboard unter „Logs" danach suchen.
````

- [ ] **Schritt 3: Commit**

```bash
git add render.yaml README.md
git commit -m "docs: Betriebsabschnitt und Gunicorn-Konfiguration"
```

---

## Abnahme für Etappe 0

Erledigt, wenn alles davon zutrifft:

- [ ] `python -m pytest` in `backend/` ist grün — die 23 ursprünglichen Scheduler-Tests **unverändert** plus die neuen API-, Migrations-, Sicherheits- und Zeittests
- [ ] `npm run lint` und `npm run build` in `frontend/` laufen fehlerfrei
- [ ] Der CI-Workflow ist auf `main` grün, für Python 3.13 **und** 3.14
- [ ] `python migrations.py status` zeigt `0001`, `0002` und `0003` als angewandt
- [ ] Ein Start mit `FLASK_ENV=production` und ohne `SECRET_KEY` bricht mit klarer Meldung ab
- [ ] Elf falsche Anmeldeversuche in Folge führen zu `429`
- [ ] `GET /gibt-es-nicht` liefert JSON, kein HTML
- [ ] Neuerzeugen eines Plans mit Handkorrekturen fragt zurück
- [ ] Der Betriebsabschnitt im README nennt Backup-Befehl und Pflichtvariablen

Danach beginnt **Etappe 1 — Arbeitszeitfenster** mit einem eigenen Plan.
