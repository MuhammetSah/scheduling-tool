"""Was noch fehlt, bevor ein Plan entstehen kann.

Etappe 11 hat gezeigt, dass "Plan erzeugen" auf einer leeren Datenbank
schweigend nichts tut - behoben, aber erst NACHDEM man gedrueckt hat. Der
Leertext davor sagt "fuer November wurde noch kein Plan generiert": wahr, und
am ersten Tag nutzlos.

Gemeldet wird nur, was einen brauchbaren Plan tatsaechlich verhindert. Eine
Liste, die auch alles Waehlbare aufzaehlt, ist eine Aufgabenliste, die nie
leer wird - und wird deshalb ignoriert.
"""


def _hr(hr_client):
    """Der hr_client ist bereits angemeldet - hier nur zur Lesbarkeit."""
    return hr_client


def test_eine_leere_einrichtung_nennt_alle_drei(hr_client):
    stand = hr_client.get('/setup-status').json

    assert stand['ready'] is False
    assert {e['key'] for e in stand['missing']} == {
        'employees', 'shift_types', 'coverage_requirements'}


def test_jeder_eintrag_sagt_wohin(hr_client):
    """Ein Hinweis ohne Weg ist eine Beschwerde."""
    stand = hr_client.get('/setup-status').json

    assert all(e['text'] and e['route'] for e in stand['missing'])


def test_angelegtes_verschwindet_aus_der_liste(hr_client):
    hr_client.post('/employees', json={'name': 'Anna'})

    stand = hr_client.get('/setup-status').json

    assert 'employees' not in {e['key'] for e in stand['missing']}
    assert len(stand['missing']) == 2


def test_vollstaendig_eingerichtet_meldet_bereit(hr_client):
    """Die Gegenprobe, und die wichtigste: eine Umsetzung, die immer etwas
    vermisst, waere sonst ebenfalls gruen."""
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}])

    stand = hr_client.get('/setup-status').json

    assert stand['ready'] is True
    assert stand['missing'] == []


def test_ein_inaktiver_mitarbeiter_zaehlt_nicht(hr_client):
    """Wer nicht eingeplant wird, richtet den Betrieb nicht ein."""
    hr_client.post('/employees', json={'name': 'Anna', 'active': False})

    stand = hr_client.get('/setup-status').json

    assert 'employees' in {e['key'] for e in stand['missing']}


def test_ein_anonymisierter_datensatz_zaehlt_auch_nicht(hr_client):
    """Ein Grabstein ist kein Personal (Etappe 5i)."""
    anna = hr_client.post('/employees', json={'name': 'Anna'}).json
    hr_client.delete('/employees/%d' % anna['id'])

    stand = hr_client.get('/setup-status').json

    assert 'employees' in {e['key'] for e in stand['missing']}


# ---------- Hinweise, die nichts verhindern ----------


def test_das_fehlende_bundesland_ist_ein_hinweis_kein_mangel(hr_client):
    """Ohne Bundesland kennt das Werkzeug keinen Feiertag - aber ein Plan
    entsteht trotzdem. Das gehoert nicht in dieselbe Liste."""
    stand = hr_client.get('/setup-status').json

    assert 'holiday_region' not in {e['key'] for e in stand['missing']}
    assert 'holiday_region' in {h['key'] for h in stand['notes']}


def test_ein_gesetztes_bundesland_verschwindet_aus_den_hinweisen(hr_client):
    hr_client.put('/settings', json={'holiday_region': 'BY'})

    stand = hr_client.get('/setup-status').json

    assert 'holiday_region' not in {h['key'] for h in stand['notes']}


def test_die_paragraph_10_frage_steht_nicht_darin(hr_client):
    """Die Gegenprobe zur Zurueckhaltung.

    "Nicht ausgenommen" ist keine fehlende Angabe, sondern genau das, was
    Paragraph 9 Abs. 1 sagt. Sie als Mangel zu fuehren hiesse, den Regelfall
    zum Versaeumnis zu erklaeren.
    """
    stand = hr_client.get('/setup-status').json

    schluessel = {e['key'] for e in stand['missing']} | {h['key'] for h in stand['notes']}
    assert 'sunday_work_permitted' not in schluessel


def test_bereit_heisst_bereit_auch_mit_offenen_hinweisen(hr_client):
    """Hinweise sind keine Mängel: ein Betrieb ohne Bundesland ist
    einsatzbereit, er sieht nur keine Feiertage."""
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}])

    stand = hr_client.get('/setup-status').json

    assert stand['ready'] is True
    assert stand['notes']


# ---------- Wer das sehen darf ----------


def test_ein_mitarbeiter_sieht_den_einrichtungsstand_nicht(hr_client):
    """Was dem Betrieb noch fehlt, ist die Sache der Personalabteilung."""
    anna = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.get('/setup-status').status_code == 403
