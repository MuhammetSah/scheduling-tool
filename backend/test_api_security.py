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


def test_hsts_in_produktion_gesetzt(client, monkeypatch):
    # is_production() liest FLASK_ENV bei jeder Anfrage neu (siehe
    # register_security_headers), daher reicht es, die Umgebungsvariable fuer
    # die Dauer dieser einen Anfrage zu setzen - die App selbst wurde von der
    # client-Fixture bereits ohne FLASK_ENV importiert.
    monkeypatch.setenv('FLASK_ENV', 'production')
    assert 'Strict-Transport-Security' in client.get('/').headers


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
