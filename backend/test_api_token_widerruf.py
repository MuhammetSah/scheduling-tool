"""Der Widerruf ausgegebener Anmeldetoken.

Der Fall, der diese Tests ausgeloest hat, laesst sich in einem Satz sagen: HR
setzt ein Passwort zurueck, weil ein Geraet abhanden gekommen ist - und das
Geraet liest weiter den Dienstplan. Das Bearer-Token ist zustandslos, das alte
Passwort war fuer seine Gueltigkeit nie noetig.

Geprueft wird deshalb nicht die Signatur (die kann itsdangerous), sondern die
eine Frage, die vorher niemand gestellt hat: ueberlebt ein Token den Vorgang,
der es beenden soll?
"""


def _mitarbeiterkonto(hr_client, name='Anna'):
    employee = hr_client.post('/employees', json={
        'name': name, 'email': f'{name.lower()}@example.com'}).json
    account = hr_client.post('/register', json={
        'username': name.lower(), 'role': 'employee', 'employee_id': employee['id'],
    }).json
    return employee, account


def _einladungstoken(hr_client, account_id):
    """Der Rohtoken aus der zuletzt ausgestellten Einladung.

    Gespeichert wird nur sein SHA-256; ueber die HTTP-Schicht kommt er
    ausschliesslich per Mail heraus, und die ist im Test nicht konfiguriert.
    Deshalb hier ueber den Mailer, den app.py aufruft.
    """
    import app as app_module
    gesendet = {}
    original = app_module.mailer.send_invitation

    def merken(email, username, token, tage, lang=None):
        gesendet['token'] = token
        return original(email, username, token, tage, lang=lang)

    app_module.mailer.send_invitation = merken
    try:
        hr_client.post(f'/accounts/{account_id}/invitation', json={})
    finally:
        app_module.mailer.send_invitation = original
    return gesendet['token']


def test_zuruecksetzen_entwertet_das_ausgegebene_token(hr_client):
    _, account = _mitarbeiterkonto(hr_client)
    token = _einladungstoken(hr_client, account['id'])
    hr_client.post(f'/invitations/{token}', json={'password': 'annas-passwort'})

    angemeldet = hr_client.post('/login', json={
        'username': 'anna', 'password': 'annas-passwort'}).json
    kopf = {'Authorization': f"Bearer {angemeldet['auth_token']}"}
    # Cookie loeschen, damit wirklich das Token geprueft wird und nicht die
    # Sitzung, die derselbe Testclient noch mitfuehrt.
    hr_client.post('/logout')
    assert hr_client.get('/me', headers=kopf).status_code == 200

    # HR setzt zurueck - genau der Griff, den man tut, wenn ein Geraet weg ist.
    # Auf einem zweiten Client, damit der erste weiterhin nur das Token
    # mitfuehrt: current_auth_claim() bevorzugt das Cookie, und ein
    # HR-Cookie auf demselben Client wuerde die Pruefung an der Frage
    # vorbeifuehren.
    import app as app_module
    with app_module.app.test_client() as personalabteilung:
        personalabteilung.post('/login', json={'username': 'hr', 'password': 'passwort-123'})
        personalabteilung.post(f'/accounts/{account["id"]}/invitation', json={})

    assert hr_client.get('/me', headers=kopf).status_code == 401
    assert hr_client.get('/employees/1/absences', headers=kopf).status_code == 401


def test_neues_passwort_entwertet_das_alte_token(hr_client):
    _, account = _mitarbeiterkonto(hr_client)
    token = _einladungstoken(hr_client, account['id'])
    hr_client.post(f'/invitations/{token}', json={'password': 'erstes-passwort'})
    altes = hr_client.post('/login', json={
        'username': 'anna', 'password': 'erstes-passwort'}).json['auth_token']
    hr_client.post('/logout')

    # Zweite Einladung, neues Passwort - der Weg "Passwort vergessen".
    hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'})
    zweiter = _einladungstoken(hr_client, account['id'])
    hr_client.post('/logout')
    hr_client.post(f'/invitations/{zweiter}', json={'password': 'zweites-passwort'})

    assert hr_client.get('/me', headers={'Authorization': f'Bearer {altes}'}).status_code == 401
    # Und das Passwort selbst ebenso - beide Wege, nicht nur einer.
    assert hr_client.post('/login', json={
        'username': 'anna', 'password': 'erstes-passwort'}).status_code == 401


def test_neues_token_nach_dem_zuruecksetzen_gilt(hr_client):
    """Der Widerruf darf nicht das Konto selbst unbrauchbar machen."""
    _, account = _mitarbeiterkonto(hr_client)
    token = _einladungstoken(hr_client, account['id'])
    hr_client.post(f'/invitations/{token}', json={'password': 'erstes-passwort'})

    hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'})
    zweiter = _einladungstoken(hr_client, account['id'])
    hr_client.post('/logout')
    hr_client.post(f'/invitations/{zweiter}', json={'password': 'zweites-passwort'})

    neu = hr_client.post('/login', json={
        'username': 'anna', 'password': 'zweites-passwort'}).json
    hr_client.post('/logout')

    antwort = hr_client.get('/me', headers={'Authorization': f"Bearer {neu['auth_token']}"})
    assert antwort.status_code == 200
    assert antwort.json['username'] == 'anna'


def test_zuruecksetzen_entwertet_auch_das_sitzungscookie(hr_client):
    """Dieselbe Regel auf dem zweiten Anmeldeweg.

    Das Cookie ueberlebte ein Zuruecksetzen genauso wie das Token. Eine Regel,
    die nur einen von zwei Wegen deckt, ist genau die Luecke, um die es hier
    geht.
    """
    _, account = _mitarbeiterkonto(hr_client)
    token = _einladungstoken(hr_client, account['id'])
    hr_client.post(f'/invitations/{token}', json={'password': 'annas-passwort'})
    hr_client.post('/login', json={'username': 'anna', 'password': 'annas-passwort'})
    assert hr_client.get('/me').status_code == 200

    # Das Zuruecksetzen macht ein zweiter Client, damit die Sitzung des ersten
    # unangetastet bleibt - so, wie es im Betrieb zwei Geraete waeren.
    import app as app_module
    with app_module.app.test_client() as personalabteilung:
        personalabteilung.post('/login', json={'username': 'hr', 'password': 'passwort-123'})
        personalabteilung.post(f'/accounts/{account["id"]}/invitation', json={})

    assert hr_client.get('/me').status_code == 401


def test_token_ohne_epoche_gilt_weiter(hr_client):
    """Die Umstellung meldet niemanden ab.

    Ein vor Migration 0018 ausgestelltes Token traegt kein `epoch`. Es als
    ungueltig zu behandeln haette beim Aufspielen jede laufende Anmeldung
    beendet - eine Sicherheitsverbesserung, die als Ausfall ankommt.
    """
    import app as app_module

    altes = app_module._auth_serializer.dumps({'user_id': 1})

    antwort = hr_client.get('/me', headers={'Authorization': f'Bearer {altes}'})
    assert antwort.status_code == 200
    assert antwort.json['username'] == 'hr'
