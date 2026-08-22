"""Aenderungsprotokoll: wer hat wann was angefasst.

Protokolliert wird auf Anfrageebene und ohne Anfrageinhalte - ein fachliches
Protokoll wuerde Krankmeldungen ein zweites Mal wegschreiben, und die sind
Gesundheitsdaten nach Art. 9 DSGVO.

Der Haken faengt jeden Fehler ab, damit er nie eine Anfrage kippt. Das macht
ihn still: schreibt er gar nichts, faellt es nirgends auf. Deshalb prueft der
erste Test hier ausdruecklich, dass ein Eintrag ENTSTEHT - beim Bauen hat genau
das einen NameError verdeckt.
"""


def _protokoll(hr_client, **params):
    return hr_client.get('/audit-log', query_string=params).json


def test_eine_aendernde_anfrage_erzeugt_einen_eintrag(hr_client):
    hr_client.post('/employees', json={'name': 'Anna'})

    eintraege = _protokoll(hr_client)

    passend = [e for e in eintraege if e['path'] == '/employees' and e['method'] == 'POST']
    assert len(passend) == 1, eintraege
    assert passend[0]['status'] == 201
    assert passend[0]['username'] == 'hr'
    assert passend[0]['at']


def test_ein_get_erzeugt_keinen_eintrag(hr_client):
    """Gegenprobe: sonst stuende das Protokoll voll mit Seitenaufrufen."""
    hr_client.get('/employees')
    hr_client.get('/shift-types')

    assert [e for e in _protokoll(hr_client) if e['method'] == 'GET'] == []


def test_eine_fehlgeschlagene_anfrage_wird_ebenfalls_protokolliert(hr_client):
    """Ein abgewiesener Versuch, den Plan zu aendern, ist mindestens so
    interessant wie ein gelungener - und ein Log, das nur Erfolge kennt,
    verschweigt genau die Faelle, wegen derer man hineinsieht."""
    antwort = hr_client.post('/employees', json={})
    assert antwort.status_code == 400

    passend = [e for e in _protokoll(hr_client) if e['path'] == '/employees']
    assert [e['status'] for e in passend] == [400]


def test_die_anmeldung_wird_nicht_protokolliert(hr_client):
    """Sie traegt ein Passwort im Rumpf, und login_attempts ist der dafuer
    gebaute Ort. Zwei Protokolle ueber denselben Vorgang waeren eines zu viel."""
    hr_client.post('/logout')
    hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'})

    pfade = {e['path'] for e in _protokoll(hr_client)}
    assert '/login' not in pfade


def test_ein_eintrag_ueberlebt_das_loeschen_seines_kontos(hr_client):
    """Der Kern der Entscheidung gegen einen Fremdschluessel auf users.

    Ein Protokoll, dessen Eintraege sich loeschen lassen, indem man das Konto
    loescht, ist keines.
    """
    mitarbeiter = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': mitarbeiter['id']}).json

    vorher = len(_protokoll(hr_client, limit=500))
    hr_client.delete(f'/accounts/{konto["id"]}')

    eintraege = _protokoll(hr_client, limit=500)
    assert len(eintraege) > vorher
    # Der Eintrag des Registrierens steht weiterhin da, mit seinem Namen.
    assert any(e['path'] == '/register' for e in eintraege), eintraege


def test_das_protokoll_ist_hr_vorbehalten(hr_client):
    mitarbeiter = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': mitarbeiter['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.get('/audit-log').status_code == 403


def test_limit_wird_gedeckelt_und_geprueft(hr_client):
    hr_client.post('/employees', json={'name': 'Anna'})

    assert len(_protokoll(hr_client, limit=1)) == 1
    assert hr_client.get('/audit-log', query_string={'limit': '9999'}).status_code == 200
    assert hr_client.get('/audit-log', query_string={'limit': 'viel'}).status_code == 400
    assert hr_client.get('/audit-log', query_string={'limit': '0'}).status_code == 400


def test_ein_fehlgeschlagener_schreibvorgang_kippt_die_anfrage_nicht(hr_client, monkeypatch):
    """Ein Protokoll, das eine sonst erfolgreiche Aenderung zu einem 500 macht,
    ist schlimmer als kein Protokoll - es faellt zuerst dann aus, wenn ohnehin
    etwas klemmt."""
    import app as app_module

    class kaputt_datetime:
        @staticmethod
        def now(*_args, **_kwargs):
            raise RuntimeError('kein Zeitstempel')

    # Der Haken benutzt die Verbindung der Anfrage; gebrochen wird deshalb der
    # Schreibvorgang selbst, nicht das Verbindungsaufbauen - sonst spraengte
    # der Test die Route mit und waere aus dem falschen Grund rot.
    monkeypatch.setattr(app_module, 'datetime', kaputt_datetime)

    antwort = hr_client.post('/employees', json={'name': 'Anna'})

    assert antwort.status_code == 201, antwort.json


def test_die_neueste_anfrage_steht_oben(hr_client):
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})

    assert _protokoll(hr_client)[0]['path'] == '/shift-types'
