"""Veroeffentlichen-Workflow: wer sieht wann welchen Plan.

schedules.status gab es seit dem ersten Tag und wurde von nichts gelesen -
jeder Plan war sichtbar, sobald er erzeugt war. Seit Etappe 5f ist er Entwurf
oder veroeffentlicht, und erst der veroeffentlichte ist fuer Mitarbeiter da.
"""


def _plan_mit_mitarbeiter(hr_client):
    """Ein besetzter Maerzplan und ein Konto, das an Anna haengt."""
    anna = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wochentag, 'start_time': '08:00', 'end_time': '16:00',
         'required_count': 1}
        for wochentag in range(5)
    ])
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3}).json
    assert any(z['employee_id'] == anna['id'] for z in plan['assignments']), plan
    return anna


def _als_mitarbeiter(hr_client, employee_id, username='anna'):
    """Meldet die Sitzung auf ein Mitarbeiterkonto um.

    Dasselbe Vorgehen wie in test_api_auth.py: ein eingeladenes Konto hat noch
    kein Passwort, geprueft werden soll die Sichtbarkeitsregel und nicht der
    Anmeldeweg.
    """
    konto = hr_client.post('/register', json={
        'username': username, 'role': 'employee', 'employee_id': employee_id}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']
    return hr_client


def test_ein_erzeugter_plan_ist_zunaechst_entwurf(hr_client):
    _plan_mit_mitarbeiter(hr_client)

    plan = hr_client.get('/schedules/2026/3').json

    assert plan['status'] == 'draft'
    assert plan['published_at'] is None


def test_ein_mitarbeiter_sieht_den_entwurf_nicht(hr_client):
    """Der Kern der Etappe.

    Und die Meldung zaehlt: "es gibt nichts" und "es ist noch nicht so weit"
    sind zwei verschiedene Auskuenfte.
    """
    anna = _plan_mit_mitarbeiter(hr_client)
    client = _als_mitarbeiter(hr_client, anna['id'])

    antwort = client.get('/schedules/2026/3')

    assert antwort.status_code == 404
    assert antwort.json['message'] == 'Der Plan für diesen Monat ist noch nicht veröffentlicht'


def test_ein_mitarbeiter_sieht_den_veroeffentlichten_plan(hr_client):
    """Die Gegenprobe, die den Test darueber erst aussagekraeftig macht."""
    anna = _plan_mit_mitarbeiter(hr_client)
    hr_client.put('/schedules/2026/3/status', json={'status': 'published'})
    client = _als_mitarbeiter(hr_client, anna['id'])

    antwort = client.get('/schedules/2026/3')

    assert antwort.status_code == 200, antwort.json
    assert antwort.json['scope'] == 'own'
    assert antwort.json['assignments']


def test_hr_sieht_den_entwurf_normal(hr_client):
    _plan_mit_mitarbeiter(hr_client)

    antwort = hr_client.get('/schedules/2026/3')

    assert antwort.status_code == 200
    assert antwort.json['assignments']


def test_veroeffentlichen_setzt_den_zeitstempel(hr_client):
    _plan_mit_mitarbeiter(hr_client)

    antwort = hr_client.put('/schedules/2026/3/status', json={'status': 'published'})

    assert antwort.status_code == 200, antwort.json
    assert antwort.json['status'] == 'published'
    assert antwort.json['published_at'] is not None


def test_erneutes_veroeffentlichen_ruehrt_den_zeitstempel_nicht_an(hr_client):
    """Idempotent, und "seit wann sehen die Leute das?" soll sich nicht
    aendern, nur weil jemand den Knopf zweimal drueckt."""
    _plan_mit_mitarbeiter(hr_client)
    erst = hr_client.put('/schedules/2026/3/status',
                         json={'status': 'published'}).json['published_at']

    erneut = hr_client.put('/schedules/2026/3/status',
                           json={'status': 'published'}).json['published_at']

    assert erneut == erst


def test_zurueckziehen_macht_wieder_einen_entwurf(hr_client):
    anna = _plan_mit_mitarbeiter(hr_client)
    hr_client.put('/schedules/2026/3/status', json={'status': 'published'})

    antwort = hr_client.put('/schedules/2026/3/status', json={'status': 'draft'})

    assert antwort.json['status'] == 'draft'
    assert antwort.json['published_at'] is None
    client = _als_mitarbeiter(hr_client, anna['id'])
    assert client.get('/schedules/2026/3').status_code == 404


def test_unbekannter_zustand_ist_400(hr_client):
    _plan_mit_mitarbeiter(hr_client)

    antwort = hr_client.put('/schedules/2026/3/status', json={'status': 'irgendwas'})

    assert antwort.status_code == 400


def test_neuerzeugen_setzt_einen_veroeffentlichten_plan_zurueck(hr_client):
    """Der Plan, den HR freigegeben hat, ist danach nicht mehr derselbe -
    Neuerzeugen verwirft ohnehin jede Handkorrektur."""
    _plan_mit_mitarbeiter(hr_client)
    hr_client.put('/schedules/2026/3/status', json={'status': 'published'})

    erneut = hr_client.post('/schedules/generate',
                            json={'year': 2026, 'month': 3, 'confirm': True}).json

    assert erneut['status'] == 'draft'
    assert erneut['published_at'] is None


def test_eine_handkorrektur_zieht_den_plan_nicht_zurueck(hr_client):
    """Die Gegenprobe zum Test darueber.

    Eine Zuweisung zu tauschen ist der Normalfall im laufenden Betrieb, kein
    neuer Plan. Jede Korrektur zum Zurueckziehen zu zwingen machte das
    Veroeffentlichen unbenutzbar.
    """
    anna = _plan_mit_mitarbeiter(hr_client)
    hr_client.put('/schedules/2026/3/status', json={'status': 'published'})
    plan = hr_client.get('/schedules/2026/3').json
    zuweisung = next(z for z in plan['assignments'] if z['employee_id'] == anna['id'])

    hr_client.put(f'/assignments/{zuweisung["id"]}', json={'employee_id': None})

    assert hr_client.get('/schedules/2026/3').json['status'] == 'published'
