"""API fuer Oeffnungszeiten und Ausnahmen: GET/PUT /business-hours sowie
GET/POST/DELETE /business-hours/exceptions.

Deckt Task 4 aus dem Etappenplan ab (siehe Task-Brief). business_hours_for()
liefert (open_time, close_time, closed) fuer ein Datum - eine Ausnahme
schlaegt die Wochentagsregel vollstaendig. Diese Vorrangregel wird deshalb an
zwei Stellen geprueft: direkt an business_hours_for() und ueber die Routen,
die die zugrundeliegenden Zeilen offenlegen - siehe
test_ausnahme_schlaegt_den_wochentag.
"""


def test_oeffnungszeiten_kommen_als_sieben_zeilen(hr_client):
    """Immer sieben, immer nach Wochentag sortiert - auch frisch nach der Migration."""
    antwort = hr_client.get('/business-hours')

    assert antwort.status_code == 200, antwort.json
    zeilen = antwort.json
    assert len(zeilen) == 7
    assert [zeile['weekday'] for zeile in zeilen] == list(range(7))
    for zeile in zeilen:
        assert zeile['open_time'] == '00:00'
        assert zeile['close_time'] == '00:00'
        assert zeile['closed'] is False


def test_oeffnungszeiten_setzen_ersetzt_vollstaendig(hr_client):
    """Gleiche Semantik wie die bestehenden Constraint-Listen."""
    neue_zeiten = [
        {'weekday': tag, 'open_time': '08:00', 'close_time': '20:00', 'closed': False}
        for tag in range(7)
    ]
    neue_zeiten[6] = {'weekday': 6, 'open_time': '00:00', 'close_time': '00:00', 'closed': True}

    antwort = hr_client.put('/business-hours', json=neue_zeiten)
    assert antwort.status_code == 200, antwort.json

    gelesen = hr_client.get('/business-hours').json
    assert len(gelesen) == 7
    for tag in range(6):
        zeile = gelesen[tag]
        assert zeile['weekday'] == tag
        assert zeile['open_time'] == '08:00'
        assert zeile['close_time'] == '20:00'
        assert zeile['closed'] is False
    assert gelesen[6]['weekday'] == 6
    assert gelesen[6]['closed'] is True


def test_geschlossener_tag_braucht_keine_zeiten(hr_client):
    antwort = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-12-25', 'closed': True, 'label': 'Weihnachten',
    })

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['open_time'] is None
    assert antwort.json['close_time'] is None
    assert antwort.json['closed'] is True

    gelesen = hr_client.get('/business-hours/exceptions').json
    assert len(gelesen) == 1
    assert gelesen[0]['date'] == '2026-12-25'
    assert gelesen[0]['open_time'] is None
    assert gelesen[0]['close_time'] is None


def test_ausnahme_schlaegt_den_wochentag(hr_client):
    """Der 03.10. ist geschlossen, obwohl freitags offen ist.

    Geprueft ueber business_hours_for() UND ueber die Route - beide Wege muessen
    dasselbe sagen.
    """
    from app import business_hours_for, get_db

    # 2025-10-03 ist ein Freitag (weekday 4). Die Standardzeile fuer Freitag ist
    # nach der Migration 00:00-00:00 mit closed=0, also "den ganzen Tag offen" -
    # das laesst sich unveraendert ueber die Route pruefen. Die Ausnahme unten
    # sagt fuer genau dieses Datum das Gegenteil: geschlossen.
    freitag = next(zeile for zeile in hr_client.get('/business-hours').json if zeile['weekday'] == 4)
    assert freitag['closed'] is False

    ausnahme = hr_client.post('/business-hours/exceptions', json={
        'date': '2025-10-03', 'closed': True, 'label': 'Betriebsausflug',
    })
    assert ausnahme.status_code == 201, ausnahme.json
    assert ausnahme.json['closed'] is True

    # Weg 1: direkt an business_hours_for().
    with hr_client.application.app_context():
        cursor = get_db().cursor()
        assert business_hours_for(cursor, '2025-10-03') == (None, None, True)

    # Weg 2: ueber die Route - die Ausnahme ist die einzige Zeile, die fuer
    # dieses Datum existiert, und sie sagt ebenfalls "geschlossen", waehrend die
    # Wochentagszeile fuer Freitag weiterhin "offen" bleibt (oben schon geprueft).
    ausnahmen = hr_client.get('/business-hours/exceptions').json
    eintrag = next(e for e in ausnahmen if e['date'] == '2025-10-03')
    assert eintrag['closed'] is True
    assert eintrag['open_time'] is None
    assert eintrag['close_time'] is None


def test_zweite_ausnahme_fuer_dasselbe_datum_ist_400(hr_client):
    erste = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-12-24', 'closed': True, 'label': 'Heiligabend',
    })
    assert erste.status_code == 201, erste.json

    zweite = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-12-24', 'open_time': '08:00', 'close_time': '12:00', 'closed': False,
    })
    assert zweite.status_code == 400

    gelesen = hr_client.get('/business-hours/exceptions').json
    assert len(gelesen) == 1
    assert gelesen[0]['closed'] is True


def test_nicht_hr_konto_bekommt_403(hr_client):
    employee = hr_client.post('/employees', json={'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': employee['id'],
    }).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    antwort = hr_client.get('/business-hours')

    assert antwort.status_code == 403
