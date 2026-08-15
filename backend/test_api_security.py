"""Absicherung der HTTP-Schicht: Schluesselpflicht und Antwort-Header."""

import pytest

import security


def test_produktion_ohne_secret_key_startet_nicht(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)

    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        security.resolve_secret_key()


def test_lokal_ohne_secret_key_ist_erlaubt(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('SECRET_KEY', raising=False)

    assert security.resolve_secret_key()


def test_antworten_tragen_security_header(client):
    response = client.get('/')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_hsts_nur_in_produktion(client):
    # Die client-Fixture entfernt FLASK_ENV, das ist also der lokale Fall.
    assert 'Strict-Transport-Security' not in client.get('/').headers
