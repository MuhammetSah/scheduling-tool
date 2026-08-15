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
