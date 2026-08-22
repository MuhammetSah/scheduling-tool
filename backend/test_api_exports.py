"""Exporte ueber die HTTP-Schicht: wer darf was herunterladen.

Die Formatierung selbst prueft test_exports.py. Hier geht es um Zugriff,
Veroeffentlichungszustand und die Kopfzeilen der Antwort.
"""


def _plan(hr_client, veroeffentlichen=False):
    anna = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wochentag, 'start_time': '08:00', 'end_time': '16:00',
         'required_count': 1}
        for wochentag in range(5)
    ])
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})
    if veroeffentlichen:
        hr_client.put('/schedules/2026/3/status', json={'status': 'published'})
    return anna


def _als_mitarbeiter(hr_client, employee_id, username='anna'):
    konto = hr_client.post('/register', json={
        'username': username, 'role': 'employee', 'employee_id': employee_id}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']
    return hr_client


# ---------- iCal ----------


def test_ein_mitarbeiter_laedt_seinen_eigenen_kalender(hr_client):
    anna = _plan(hr_client, veroeffentlichen=True)
    client = _als_mitarbeiter(hr_client, anna['id'])

    antwort = client.get(f'/employees/{anna["id"]}/schedule.ics?year=2026&month=3')

    assert antwort.status_code == 200, antwort.data[:200]
    assert antwort.mimetype == 'text/calendar'
    assert 'attachment' in antwort.headers['Content-Disposition']
    assert antwort.data.decode('utf-8').startswith('BEGIN:VCALENDAR')


def test_ein_entwurf_wird_nicht_ausgeliefert(hr_client):
    """Der Kern: ein Entwurf ist fuer Mitarbeiter nicht vorhanden, und ein
    Export, der ihn doch ausliefert, waere die Hintertuer daneben."""
    anna = _plan(hr_client, veroeffentlichen=False)
    client = _als_mitarbeiter(hr_client, anna['id'])

    antwort = client.get(f'/employees/{anna["id"]}/schedule.ics?year=2026&month=3')

    assert antwort.status_code == 404


def test_auch_hr_bekommt_den_entwurf_nicht_als_ical(hr_client):
    """Sonst verschickt jemand versehentlich einen Entwurf - der Zweck der
    Datei ist, das Haus zu verlassen."""
    anna = _plan(hr_client, veroeffentlichen=False)

    antwort = hr_client.get(f'/employees/{anna["id"]}/schedule.ics?year=2026&month=3')

    assert antwort.status_code == 404


def test_ein_fremder_kalender_ist_verboten(hr_client):
    anna = _plan(hr_client, veroeffentlichen=True)
    berta = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com'}).json
    client = _als_mitarbeiter(hr_client, berta['id'], username='berta')

    antwort = client.get(f'/employees/{anna["id"]}/schedule.ics?year=2026&month=3')

    assert antwort.status_code == 403


def test_ohne_jahr_und_monat_ist_es_400(hr_client):
    anna = _plan(hr_client, veroeffentlichen=True)

    assert hr_client.get(f'/employees/{anna["id"]}/schedule.ics').status_code == 400


def test_der_kalender_enthaelt_nur_die_eigenen_schichten(hr_client):
    anna = _plan(hr_client, veroeffentlichen=True)
    berta = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com'}).json

    text = hr_client.get(
        f'/employees/{berta["id"]}/schedule.ics?year=2026&month=3').data.decode('utf-8')

    # Berta hat keine Schichten - der Kalender ist leer, aber gueltig.
    assert 'BEGIN:VCALENDAR' in text
    assert 'BEGIN:VEVENT' not in text
    assert anna['id'] != berta['id']


# ---------- CSV ----------


def test_hr_laedt_den_monat_als_csv(hr_client):
    _plan(hr_client, veroeffentlichen=True)

    antwort = hr_client.get('/schedules/2026/3/export.csv')

    assert antwort.status_code == 200
    assert antwort.mimetype == 'text/csv'
    text = antwort.data.decode('utf-8')
    assert text.startswith('﻿')
    assert 'Mitarbeiter' in text.split('\r\n')[0]


def test_die_csv_liefert_auch_einen_entwurf(hr_client):
    """Die Gegenprobe zum iCal. Der Unterschied ist der Empfaenger: HR zieht
    die CSV fuer sich, das iCal landet im Telefon eines Mitarbeiters."""
    _plan(hr_client, veroeffentlichen=False)

    assert hr_client.get('/schedules/2026/3/export.csv').status_code == 200


def test_die_csv_ist_hr_vorbehalten(hr_client):
    anna = _plan(hr_client, veroeffentlichen=True)
    client = _als_mitarbeiter(hr_client, anna['id'])

    assert client.get('/schedules/2026/3/export.csv').status_code == 403


def test_ohne_plan_ist_es_404(hr_client):
    assert hr_client.get('/schedules/2026/7/export.csv').status_code == 404
