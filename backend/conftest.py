"""Gemeinsame Fixtures fuer die API-Tests.

Jeder Test bekommt eine eigene, leere SQLite-Datei. app.py ruft init_db() beim
Import auf und haelt den Flask-App-Objekt auf Modulebene, deshalb werden `app`
und `db` pro Test frisch importiert - sonst wuerde der erste Test die Datenbank
fuer alle folgenden festlegen.

Ist TEST_DATABASE_URL gesetzt, laeuft dieselbe Fixture stattdessen gegen ein
frisches Postgres-Schema (siehe pg_testsupport.py) - der Standardfall ohne
diese Variable bleibt davon unberuehrt: dieselben monkeypatch-Aufrufe, dieselbe
Modul-Neuimportierung wie zuvor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pg_testsupport import resolve_test_database_url, temporary_schema


def _fresh_app_client():
    for module in ('app', 'db', 'migrations'):
        sys.modules.pop(module, None)

    import app as app_module

    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.setenv('SECRET_KEY', 'test-secret-nur-fuer-tests')

    base_url = resolve_test_database_url()
    if base_url:
        with temporary_schema(base_url) as (schema_url, _schema):
            monkeypatch.setenv('DATABASE_URL', schema_url)
            monkeypatch.delenv('SCHICHTPLAN_DB_PATH', raising=False)
            yield from _fresh_app_client()
    else:
        monkeypatch.setenv('SCHICHTPLAN_DB_PATH', str(tmp_path / 'test.db'))
        monkeypatch.delenv('DATABASE_URL', raising=False)
        yield from _fresh_app_client()


@pytest.fixture
def hr_client(client):
    """Angemeldet als das erste HR-Konto."""
    response = client.post('/register', json={'username': 'hr', 'password': 'passwort-123'})
    assert response.status_code == 201, response.json
    return client
