"""Absicherung der HTTP-Schicht: Schluesselpflicht und Antwort-Header."""

import sys

import pytest
from flask import request

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


def test_ip_wird_ausserhalb_der_produktion_nicht_aus_x_forwarded_for_uebernommen(client, monkeypatch):
    """Ohne is_production() ist ProxyFix nicht eingehaengt (siehe app.py):
    lokal gibt es keinen Proxy, der den Header setzt, also darf ein Client
    ihn nicht selbst setzen koennen, um die in login_attempts.ip
    protokollierte Adresse zu faelschen.
    """
    import app as app_module

    def erfasse_ip():
        return {'ip': request.remote_addr}, 200
    monkeypatch.setitem(app_module.app.view_functions, 'index', erfasse_ip)

    antwort = client.get('/', headers={'X-Forwarded-For': '203.0.113.5'})

    assert antwort.json['ip'] != '203.0.113.5'


def test_ip_wird_in_produktion_ueber_proxyfix_aus_x_forwarded_for_gelesen(monkeypatch, tmp_path):
    """In Produktion (Render) schreibt der vorgeschaltete Proxy diesen Header
    selbst, deshalb ist er dort vertrauenswuerdig - siehe die Begruendung bei
    ProxyFix in app.py.
    """
    monkeypatch.setenv('SCHICHTPLAN_DB_PATH', str(tmp_path / 'proxyfix.db'))
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('SECRET_KEY', 'test-secret-nur-fuer-tests')
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.setenv('FLASK_ENV', 'production')

    for module in ('app', 'db', 'migrations'):
        sys.modules.pop(module, None)
    import app as app_module

    def erfasse_ip():
        return {'ip': request.remote_addr}, 200
    monkeypatch.setitem(app_module.app.view_functions, 'index', erfasse_ip)

    with app_module.app.test_client() as test_client:
        antwort = test_client.get('/', headers={'X-Forwarded-For': '203.0.113.5'})

    assert antwort.json['ip'] == '203.0.113.5'


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
    # Ohne einen registrierten Exception-Handler wuerde Flask im Testmodus die
    # Ausnahme durchreichen statt sie zu behandeln (PROPAGATE_EXCEPTIONS
    # default True bei TESTING=True) - dann wuerde client.get() selbst mit dem
    # RuntimeError abbrechen statt eine Response zurueckzugeben. Sobald unten
    # ein @app.errorhandler(Exception) registriert ist, greift Flask ihn schon
    # in handle_user_exception, bevor PROPAGATE_EXCEPTIONS ueberhaupt geprueft
    # wird - diese Zeile wird dann redundant, schadet aber nicht.
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = False

    response = client.get('/')

    assert response.status_code == 500
    assert response.is_json
    assert response.json['request_id']
    # Kein Stacktrace und keine Ausnahmemeldung nach aussen.
    body = response.get_data(as_text=True)
    assert 'absichtlich' not in body
    assert 'RuntimeError' not in body
    assert 'Traceback' not in body
