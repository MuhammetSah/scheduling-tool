"""API fuer Oeffnungszeiten, Ausnahmen und Bedarfsbaender: GET/PUT
/business-hours, GET/POST/DELETE /business-hours/exceptions sowie GET/PUT
/coverage-requirements.

Deckt Task 4 und Task 5 aus dem Etappenplan ab (siehe Task-Briefs). Task 4:
business_hours_for() liefert (open_time, close_time, closed) fuer ein Datum -
eine Ausnahme schlaegt die Wochentagsregel vollstaendig. Diese Vorrangregel
wird deshalb an zwei Stellen geprueft: direkt an business_hours_for() und
ueber die Routen, die die zugrundeliegenden Zeilen offenlegen - siehe
test_ausnahme_schlaegt_den_wochentag.

Task 5: /coverage-requirements ersetzt beim PUT die Baender aller Wochentage
vollstaendig (dieselbe Semantik wie /business-hours). Drei Regeln werden
serverseitig geprueft: Baender desselben Wochentags duerfen sich nicht
ueberlappen (halboffene Grenze [start, end)), ein Band muss innerhalb der
Oeffnungszeit seines Wochentags liegen, und required_count darf nicht negativ
sein. Ausdruecklich NICHT geprueft: Ueberlappung ueber die Wochentagsgrenze
hinweg (siehe Task-5-Brief) - Baender verschiedener Wochentage koennen sich
unter der Wochenwiederholung theoretisch ueberschneiden, das zu erkennen
haette die Woche als 10080-Minuten-Ring zu behandeln, was bewusst nicht
gebaut wurde.
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


def test_falsche_anzahl_eintraege_ist_400(hr_client):
    sechs_eintraege = [
        {'weekday': tag, 'open_time': '08:00', 'close_time': '18:00', 'closed': False}
        for tag in range(6)
    ]

    antwort = hr_client.put('/business-hours', json=sechs_eintraege)

    assert antwort.status_code == 400
    assert antwort.json['message'] == (
        'Es müssen genau 7 Einträge übergeben werden, einer je Wochentag (Montag bis Sonntag)'
    )


def test_doppelter_wochentag_ist_400(hr_client):
    eintraege = [
        {'weekday': 0, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 0, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 1, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 2, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 3, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 4, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
        {'weekday': 5, 'open_time': '08:00', 'close_time': '18:00', 'closed': False},
    ]

    antwort = hr_client.put('/business-hours', json=eintraege)

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Jeder Wochentag darf nur einmal vorkommen'


def test_eintrag_ohne_objekt_ist_400(hr_client):
    eintraege = [
        {'weekday': tag, 'open_time': '08:00', 'close_time': '18:00', 'closed': False}
        for tag in range(6)
    ]
    eintraege.append('Montag')

    antwort = hr_client.put('/business-hours', json=eintraege)

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Jeder Eintrag muss ein Objekt mit Wochentag, Öffnungs- und Schließzeit sein'


def test_offene_ausnahme_mit_eigenen_zeiten_schlaegt_den_wochentag(hr_client):
    """Eine offene Ausnahme mit eigenen Zeiten - der eigentliche Zweck von Sonderoeffnungszeiten.

    Anders als test_ausnahme_schlaegt_den_wochentag (geschlossene Ausnahme) hier
    eine Ausnahme, die selbst offen ist, aber mit eigenen, vom Wochentag
    abweichenden Zeiten - der Zweig in parse_business_hours_exception() fuer
    closed=False mit gueltigen Zeiten wird sonst von keinem Test durchlaufen.
    """
    from app import business_hours_for, get_db

    # 2026-09-02 ist ein Mittwoch (weekday 2). Die Standardzeile ist nach der
    # Migration 00:00-00:00 (ganztags offen) - die Ausnahme unten setzt fuer
    # genau dieses Datum andere Zeiten, damit Wochentagsregel und Ausnahme
    # nachweislich verschiedene Ergebnisse liefern.
    mittwoch = next(z for z in hr_client.get('/business-hours').json if z['weekday'] == 2)
    assert (mittwoch['open_time'], mittwoch['close_time']) == ('00:00', '00:00')

    antwort = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-09-02', 'open_time': '10:00', 'close_time': '14:00', 'closed': False,
        'label': 'Verkuerzt',
    })

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['open_time'] == '10:00'
    assert antwort.json['close_time'] == '14:00'
    assert antwort.json['closed'] is False

    with hr_client.application.app_context():
        cursor = get_db().cursor()
        assert business_hours_for(cursor, '2026-09-02') == ('10:00', '14:00', False)


def test_nicht_hr_konto_bekommt_403_business_hours(hr_client):
    """Rollenschutz fuer /business-hours. Siehe
    test_nicht_hr_konto_bekommt_403_coverage_requirements fuer /coverage-requirements -
    zwei Namen, damit sich die beiden Tests im selben Modul nicht gegenseitig
    ueberschreiben.
    """
    employee = hr_client.post('/employees', json={'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': employee['id'],
    }).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    antwort = hr_client.get('/business-hours')

    assert antwort.status_code == 403


# ---------- Task 5: GET/PUT /coverage-requirements ----------

def test_baender_setzen_und_lesen(hr_client):
    """PUT ersetzt vollstaendig, GET liest den neuen Bestand zurueck."""
    baender = [
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 3},
        {'weekday': 0, 'start_time': '16:00', 'end_time': '22:00', 'required_count': 2},
        {'weekday': 2, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 1},
    ]

    antwort = hr_client.put('/coverage-requirements', json=baender)
    assert antwort.status_code == 200, antwort.json

    gelesen = hr_client.get('/coverage-requirements').json
    assert len(gelesen) == 3
    montag = [b for b in gelesen if b['weekday'] == 0]
    assert len(montag) == 2
    assert {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 3} in gelesen
    assert {'weekday': 2, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 1} in gelesen

    # Vollstaendiger Ersatz: ein zweites PUT mit weniger Baendern loescht den Rest,
    # dieselbe Semantik wie test_oeffnungszeiten_setzen_ersetzt_vollstaendig oben.
    zweites_put = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '10:00', 'end_time': '12:00', 'required_count': 1},
    ])
    assert zweites_put.status_code == 200, zweites_put.json
    gelesen_danach = hr_client.get('/coverage-requirements').json
    assert gelesen_danach == [
        {'weekday': 1, 'start_time': '10:00', 'end_time': '12:00', 'required_count': 1},
    ]


def test_ueberlappende_baender_sind_400(hr_client):
    """08:00-12:00 und 11:00-15:00 am selben Wochentag. Meldung woertlich pruefen.

    Gegenprobe im selben Test: 08:00-12:00 und 12:00-16:00 gehen durch - die
    Grenze ist halboffen. Ohne diese Haelfte wuerde der Test auch dann gruen
    sein, wenn die Pruefung jede zweite Angabe ablehnt.
    """
    ueberlappend = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
        {'weekday': 0, 'start_time': '11:00', 'end_time': '15:00', 'required_count': 1},
    ])
    assert ueberlappend.status_code == 400
    assert ueberlappend.json['message'] == (
        'Bänder überschneiden sich am Montag: 08:00–12:00 und 11:00–15:00'
    )

    beruehrend = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
        {'weekday': 0, 'start_time': '12:00', 'end_time': '16:00', 'required_count': 1},
    ])
    assert beruehrend.status_code == 200, beruehrend.json


def test_band_ausserhalb_der_oeffnungszeit_ist_400(hr_client):
    """Oeffnung 08:00-18:00, Band 07:00-12:00. Meldung woertlich pruefen."""
    oeffnungszeiten = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    oeffnungszeiten[0] = {'weekday': 0, 'open_time': '08:00', 'close_time': '18:00', 'closed': False}
    gesetzt = hr_client.put('/business-hours', json=oeffnungszeiten)
    assert gesetzt.status_code == 200, gesetzt.json

    antwort = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '07:00', 'end_time': '12:00', 'required_count': 2},
    ])

    assert antwort.status_code == 400
    assert antwort.json['message'] == (
        'Band 07:00–12:00 am Montag liegt außerhalb der Öffnungszeit (08:00–18:00)'
    )


def test_band_an_einem_geschlossenen_tag_ist_400(hr_client):
    oeffnungszeiten = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    oeffnungszeiten[0] = {'weekday': 0, 'open_time': '00:00', 'close_time': '00:00', 'closed': True}
    gesetzt = hr_client.put('/business-hours', json=oeffnungszeiten)
    assert gesetzt.status_code == 200, gesetzt.json

    antwort = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '09:00', 'end_time': '10:00', 'required_count': 1},
    ])

    assert antwort.status_code == 400
    assert antwort.json['message'] == (
        'Am Montag ist geschlossen, dort ist kein Bedarfsband erlaubt (09:00–10:00)'
    )


def test_negativer_bedarf_ist_400(hr_client):
    antwort = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'required_count': -1},
    ])

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Der Bedarf darf nicht negativ sein'


def test_baender_verschiedener_wochentage_stoeren_sich_nicht(hr_client):
    """Montag 08:00-12:00 und Dienstag 08:00-12:00 sind beide erlaubt."""
    antwort = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
        {'weekday': 1, 'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
    ])

    assert antwort.status_code == 200, antwort.json
    gelesen = hr_client.get('/coverage-requirements').json
    assert len(gelesen) == 2
    assert {b['weekday'] for b in gelesen} == {0, 1}


def test_nicht_hr_konto_bekommt_403_coverage_requirements(hr_client):
    employee = hr_client.post('/employees', json={'name': 'Bert', 'email': 'bert@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'bert', 'role': 'employee', 'employee_id': employee['id'],
    }).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    lesen = hr_client.get('/coverage-requirements')
    assert lesen.status_code == 403

    schreiben = hr_client.put('/coverage-requirements', json=[])
    assert schreiben.status_code == 403


# ---------- Task 6: Deckungsluecken im Plan (GET /schedules/<jahr>/<monat>) ----------
#
# 2026-09-01 ist ein Dienstag (Wochentag 1) - derselbe Tag, den
# test_api_assignment_times.py schon fuer aehnliche Zwecke benutzt.

def test_plan_meldet_deckungsluecken(hr_client):
    """Bedarf 2 am Dienstag 06:00-14:00, nur eine Person eingeplant -> eine Luecke."""
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    anna = hr_client.post('/employees', json={'name': 'Anna'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    assert hr_client.put(f'/assignments/{platz["id"]}',
                          json={'employee_id': anna['id']}).status_code == 200

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    # September 2026 hat fuenf Dienstage; der Bedarf gilt fuer den Wochentag und
    # damit fuer alle fuenf, ohne Zuweisung ueberall eine Luecke. Gefiltert auf
    # den einen Tag, um den nicht mit den uebrigen vier zu vermischen.
    luecken_am_ersten = [g for g in antwort.json['coverage_gaps'] if g['date'] == '2026-09-01']
    assert luecken_am_ersten == [
        {'date': '2026-09-01', 'start_time': '06:00', 'end_time': '14:00', 'missing': 1},
    ]


def test_individuelle_zeit_deckt_genau_ihre_zeit_ab(hr_client):
    """Der Anschluss an Etappe 2: eine Person mit eigener Zeit 10:00-16:00 deckt
    10:00-16:00 ab, nicht die 06:00-14:00 ihrer Schichtart.

    Diskriminierung: der Bedarf ist so gelegt, dass beide Lesarten zu
    VERSCHIEDENEN Luecken fuehren. Zwei Baender, 06:00-10:00 und 14:00-16:00,
    je required_count 1: liest die Rechnung die Schichtart-Zeit (06:00-14:00),
    ist 06:00-10:00 gedeckt und 14:00-16:00 die Luecke - genau umgekehrt zur
    tatsaechlichen Zeit, die 06:00-10:00 offen laesst und 14:00-16:00 deckt.
    Ein Aufbau, bei dem beides dieselbe Luecke ergibt, wuerde das nicht zeigen.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '10:00', 'required_count': 1},
        {'weekday': 1, 'start_time': '14:00', 'end_time': '16:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    ben = hr_client.post('/employees', json={'name': 'Ben'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    # Eigene Zeit weicht bewusst von der Schichtart ab - ueber dieselbe Route,
    # die die Anwendung auch benutzt (PUT /assignments/<id> mit start_time/end_time).
    zugewiesen = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': ben['id'], 'start_time': '10:00', 'end_time': '16:00',
    })
    assert zugewiesen.status_code == 200, zugewiesen.json

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    luecken_am_ersten = [g for g in antwort.json['coverage_gaps'] if g['date'] == '2026-09-01']
    assert luecken_am_ersten == [
        {'date': '2026-09-01', 'start_time': '06:00', 'end_time': '10:00', 'missing': 1},
    ]


def test_unbesetzter_platz_deckt_nichts_ab(hr_client):
    """Ein Platz ohne Mitarbeiter deckt nichts ab, auch wenn er existiert."""
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Platz existiert, bleibt aber unbesetzt - "initially unassigned" (add_slot).
    hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    })

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    luecken_am_ersten = [g for g in antwort.json['coverage_gaps'] if g['date'] == '2026-09-01']
    assert luecken_am_ersten == [
        {'date': '2026-09-01', 'start_time': '06:00', 'end_time': '14:00', 'missing': 1},
    ]


def test_geschlossener_ausnahmetag_hat_keine_luecke(hr_client):
    """Auch wenn fuer den Wochentag Baender hinterlegt sind."""
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Unbesetzter Platz - ohne die Ausnahme unten waere das die Luecke aus
    # test_unbesetzter_platz_deckt_nichts_ab.
    hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    })

    ausnahme = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-09-01', 'closed': True, 'label': 'Betriebsausflug',
    })
    assert ausnahme.status_code == 201, ausnahme.json

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    # Andere Dienstage im Monat bleiben unberuehrt (sie haben ihre eigene Luecke,
    # da dort niemand eingeplant ist) - hier zaehlt nur, dass der 01.09. keine hat.
    assert not any(g['date'] == '2026-09-01' for g in antwort.json['coverage_gaps'])
