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
import calendar
from datetime import date


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
    from app import (
        business_hours_exceptions_by_date, business_hours_for, get_db,
        load_business_hours_by_weekday,
    )

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

    # Weg 1: direkt an business_hours_for(). Die Funktion rechnet auf
    # vorgeladenen Dicts statt selbst abzufragen - die zwei Lader hier sind
    # dieselben, die auch coverage_gaps_for_month() einmal pro Monat benutzt.
    with hr_client.application.app_context():
        cursor = get_db().cursor()
        stunden = load_business_hours_by_weekday(cursor)
        ausnahmen = business_hours_exceptions_by_date(cursor, '2025-10-01', '2025-10-31')
        assert business_hours_for('2025-10-03', 4, stunden, ausnahmen) == (None, None, True)

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
    from app import (
        business_hours_exceptions_by_date, business_hours_for, get_db,
        load_business_hours_by_weekday,
    )

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
        stunden = load_business_hours_by_weekday(cursor)
        ausnahmen = business_hours_exceptions_by_date(cursor, '2026-09-01', '2026-09-30')
        assert business_hours_for('2026-09-02', 2, stunden, ausnahmen) == ('10:00', '14:00', False)


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


def test_nachtband_wird_unter_ganztaegiger_oeffnung_akzeptiert(hr_client):
    """Montag 22:00-06:00 und Dienstag 00:00-08:00 gehen beide durch - die im
    README als bekannte Grenze beschriebene Lage.

    Unter der Standard-Oeffnungszeit 00:00-00:00 (ganztags offen) ist ein
    Nachtband ueber die API speicherbar. Ohne diesen Test bleibt die
    README-Aussage eine Behauptung ueber einen Zustand, den die Route vorher
    mit 400 abgelehnt hat.

    Gegenprobe am Ende: unter einer echten Oeffnungszeit 08:00-18:00 bleibt
    dasselbe Nachtband abgelehnt - der Ring darf die Pruefung nicht generell
    aufweichen.
    """
    baender = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '22:00', 'end_time': '06:00', 'required_count': 2},
        {'weekday': 1, 'start_time': '00:00', 'end_time': '08:00', 'required_count': 1},
    ])

    assert baender.status_code == 200, baender.json
    gelesen = hr_client.get('/coverage-requirements').json
    assert {'weekday': 0, 'start_time': '22:00', 'end_time': '06:00', 'required_count': 2} in gelesen
    assert {'weekday': 1, 'start_time': '00:00', 'end_time': '08:00', 'required_count': 1} in gelesen

    geleert = hr_client.put('/coverage-requirements', json=[])
    assert geleert.status_code == 200, geleert.json
    oeffnungszeiten = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    oeffnungszeiten[0] = {'weekday': 0, 'open_time': '08:00', 'close_time': '18:00', 'closed': False}
    assert hr_client.put('/business-hours', json=oeffnungszeiten).status_code == 200

    abgelehnt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '22:00', 'end_time': '06:00', 'required_count': 2},
    ])
    assert abgelehnt.status_code == 400
    assert abgelehnt.json['message'] == (
        'Band 22:00–06:00 am Montag liegt außerhalb der Öffnungszeit (08:00–18:00)'
    )


def test_oeffnungszeit_die_ein_bestehendes_band_ungueltig_macht_ist_400(hr_client):
    """Die Gegenrichtung der Bandpruefung: /business-hours lehnt ab, was
    /coverage-requirements danach nicht mehr zuruecknehmen koennte.

    Ohne diese Pruefung war der gespeicherte Bestand nach dem Verengen einer
    Oeffnungszeit nicht mehr speicherbar, und weil die Bandroute die ganze
    Liste auf einmal prueft, sperrte ein einziges veraltetes Band den Editor
    fuer alle Wochentage.

    Zwei Gegenproben: nichts darf geschrieben worden sein (ein abgelehnter PUT
    laesst alle sieben Zeilen wie sie waren), und eine Verengung, in die das
    Band noch passt, geht weiterhin durch.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '18:00', 'required_count': 3},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    zu_eng = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    zu_eng[1] = {'weekday': 1, 'open_time': '09:00', 'close_time': '12:00', 'closed': False}

    antwort = hr_client.put('/business-hours', json=zu_eng)

    assert antwort.status_code == 400
    assert antwort.json['message'] == (
        'Die neue Öffnungszeit (09:00–12:00) am Dienstag passt nicht zum '
        'gespeicherten Bedarfsband 06:00–18:00. Bitte zuerst das Band anpassen.'
    )

    # Nichts geschrieben - auch nicht die sechs Wochentage ohne Konflikt.
    for zeile in hr_client.get('/business-hours').json:
        assert (zeile['open_time'], zeile['close_time']) == ('00:00', '00:00')
    assert hr_client.get('/coverage-requirements').json == [
        {'weekday': 1, 'start_time': '06:00', 'end_time': '18:00', 'required_count': 3},
    ]

    passend = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    passend[1] = {'weekday': 1, 'open_time': '06:00', 'close_time': '18:00', 'closed': False}
    assert hr_client.put('/business-hours', json=passend).status_code == 200


def test_wochentag_schliessen_mit_bestehendem_band_ist_400(hr_client):
    """Der zweite Zweig der Gegenpruefung: geschlossen schlaegt jede Bandpruefung.

    Getrennt vom Test darueber, weil die Meldung eine andere ist - eine
    Oeffnungszeit steht in ihr gar nicht mehr, es gibt keine.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '09:00', 'end_time': '10:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    geschlossen = [
        {'weekday': tag, 'open_time': '00:00', 'close_time': '00:00', 'closed': False}
        for tag in range(7)
    ]
    geschlossen[1] = {'weekday': 1, 'open_time': '00:00', 'close_time': '00:00', 'closed': True}

    antwort = hr_client.put('/business-hours', json=geschlossen)

    assert antwort.status_code == 400
    assert antwort.json['message'] == (
        'Am Dienstag ist das Bedarfsband 09:00–10:00 gespeichert; der Tag kann nicht '
        'auf geschlossen gesetzt werden. Bitte zuerst das Band entfernen.'
    )

    # Der Tag bleibt offen; ohne Band ginge dasselbe PUT durch.
    assert hr_client.get('/business-hours').json[1]['closed'] is False
    assert hr_client.put('/coverage-requirements', json=[]).status_code == 200
    assert hr_client.put('/business-hours', json=geschlossen).status_code == 200


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
    """Bedarf 2 am Dienstag 06:00-14:00, nur eine Person vorhanden -> eine Luecke.

    Seit Etappe 4 baut der Generator die Bloecke selbst aus dem Band, statt
    dass jemand sie von Hand anlegen muss: er erzeugt zwei, besetzt den einen
    mit Anna und laesst den anderen offen. Die Luecke ist dieselbe wie zuvor,
    sie entsteht nur einen Schritt frueher.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    })
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

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

    Ben arbeitet dienstags normalerweise nicht - seit Etappe 4 wuerde der
    Generator die Bloecke des Tages sonst selbst besetzen, und die Handkorrektur
    darunter haette nichts mehr zu zeigen. Genau so ist der Fall auch gemeint:
    HR setzt jemanden ausserhalb seiner Regelzeiten mit eigenen Uhrzeiten ein.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '10:00', 'required_count': 1},
        {'weekday': 1, 'start_time': '14:00', 'end_time': '16:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    ben = hr_client.post('/employees', json={'name': 'Ben', 'unavailable_weekdays': [1]}).json
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


def _schreibe_an_der_api_vorbei(hr_client, sql, parameter):
    """Setzt eine Zeile direkt in der Datenbank, ohne die Route zu benutzen.

    Kein Umweg um die Validierung zum Spass: genau so entstehen die Zustaende,
    die die zwei Tests unten pruefen. Migration 0007 leitet Baender aus den
    Schichtarten ab und schreibt sie direkt, und jede Datenbank, die vor der
    Gegenpruefung in replace_business_hours() bearbeitet wurde, kann eine
    Oeffnungszeit enthalten, die zu ihren Baendern nicht mehr passt. Ueber die
    Route ist beides seit dieser Fassung nicht mehr herstellbar - der
    Altbestand verschwindet dadurch aber nicht.
    """
    from app import get_db

    with hr_client.application.app_context():
        connection = get_db()
        connection.cursor().execute(sql, parameter)
        connection.commit()


def test_band_ausserhalb_der_oeffnungszeit_erzeugt_dort_keine_luecke(hr_client):
    """Altbestand wird auf das Oeffnungsfenster zugeschnitten, statt Personal
    fuer einen geschlossenen Betrieb zu fordern.

    Das Band 06:00-18:00 ist gespeichert, die Oeffnungszeit des Dienstags wird
    danach an der API vorbei auf 09:00-12:00 verengt. Gemeldet werden darf nur
    die Luecke innerhalb der Oeffnungszeit. Die Zeiten sind bewusst so gewaehlt,
    dass beide Lesarten verschiedene Ergebnisse liefern - ein Zuschnitt, der
    zufaellig dasselbe ergibt, wuerde nichts zeigen.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '18:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    # Eine Schichtart, damit ueberhaupt ein Plan erzeugt werden kann; besetzt
    # wird nichts, die Luecke ist der volle Bedarf.
    hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    })
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    _schreibe_an_der_api_vorbei(
        hr_client,
        'UPDATE business_hours SET open_time = ?, close_time = ? WHERE weekday = ?',
        ('09:00', '12:00', 1),
    )

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    luecken_am_ersten = [g for g in antwort.json['coverage_gaps'] if g['date'] == '2026-09-01']
    assert luecken_am_ersten == [
        {'date': '2026-09-01', 'start_time': '09:00', 'end_time': '12:00', 'missing': 1},
    ]


def test_wochentag_ueber_business_hours_geschlossen_hat_keine_luecke(hr_client):
    """Geschlossen laut Wochentagsregel, ohne jede Ausnahme fuer das Datum.

    Der andere Zweig von _closed_on() als in
    test_geschlossener_ausnahmetag_hat_keine_luecke: dort entscheidet die
    Ausnahme, hier die Wochentagszeile - und zwar fuer alle fuenf Dienstage des
    Monats, nicht nur fuer einen. Ueber die Route ist dieser Zustand nicht mehr
    herstellbar (das Schliessen eines Tages mit Baendern wird abgelehnt), als
    Altbestand aber sehr wohl.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    })
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Ohne die naechste Zeile meldet der Plan an jedem der fuenf Dienstage eine
    # Luecke - das ist die Gegenprobe, die diesen Test von einem trivial gruenen
    # unterscheidet.
    vorher = hr_client.get('/schedules/2026/9').json['coverage_gaps']
    assert [g['date'] for g in vorher] == [
        '2026-09-01', '2026-09-08', '2026-09-15', '2026-09-22', '2026-09-29',
    ]

    _schreibe_an_der_api_vorbei(
        hr_client, 'UPDATE business_hours SET closed = 1 WHERE weekday = ?', (1,),
    )

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    assert antwort.json['coverage_gaps'] == []
    assert hr_client.get('/business-hours/exceptions').json == []


def test_offene_ausnahme_schneidet_die_luecken_ihres_datums_zu(hr_client):
    """Eine Sonderoeffnung mit eigenen Zeiten wirkt auf die gemeldeten Luecken.

    Bis hierher wurde von einer Ausnahme nur closed gelesen; ihre Zeiten waren
    gespeichert, im Editor sichtbar und ohne jede Wirkung. Der 01.09. ist nur
    von 10:00 bis 11:00 offen, der Bedarf des Dienstags laeuft von 06:00 bis
    14:00 - gemeldet werden darf nur die eine Stunde.

    Der 08.09. ist derselbe Wochentag ohne Ausnahme und bleibt bei der vollen
    Luecke: ohne diese Haelfte waere der Test auch gruen, wenn die Ausnahme
    einfach alle Luecken des Monats verkleinern wuerde.
    """
    gesetzt = hr_client.put('/coverage-requirements', json=[
        {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 1},
    ])
    assert gesetzt.status_code == 200, gesetzt.json

    hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    })
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    ausnahme = hr_client.post('/business-hours/exceptions', json={
        'date': '2026-09-01', 'open_time': '10:00', 'close_time': '11:00', 'closed': False,
        'label': 'Sonderoeffnung',
    })
    assert ausnahme.status_code == 201, ausnahme.json

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    luecken = antwort.json['coverage_gaps']
    assert [g for g in luecken if g['date'] == '2026-09-01'] == [
        {'date': '2026-09-01', 'start_time': '10:00', 'end_time': '11:00', 'missing': 1},
    ]
    assert [g for g in luecken if g['date'] == '2026-09-08'] == [
        {'date': '2026-09-08', 'start_time': '06:00', 'end_time': '14:00', 'missing': 1},
    ]


# ---------- Etappe 4: der Generator plant aus den Bedarfsbaendern ----------


def _montage(jahr, monat):
    tage = calendar.monthrange(jahr, monat)[1]
    return [date(jahr, monat, tag) for tag in range(1, tage + 1)
            if date(jahr, monat, tag).weekday() == 0]


def test_generator_folgt_den_baendern_und_nicht_mehr_dem_schichtbedarf(hr_client):
    """Der Beweis der Umstellung.

    shift_requirements steht ueberall auf 0 - der alte Pfad wuerde nichts
    erzeugen. coverage_requirements verlangt montags zwei Personen, und genau
    das muss herauskommen.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00',
        'requirements': [0] * 7,
    })
    for name in ('Anna', 'Ben'):
        hr_client.post('/employees', json={'name': name})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 2},
    ])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    assert antwort.status_code == 201, antwort.json
    zuweisungen = antwort.json['assignments']
    assert len(zuweisungen) == 2 * len(_montage(2026, 9))
    assert all(date.fromisoformat(z['date']).weekday() == 0 for z in zuweisungen)


def test_generator_schreibt_die_tatsaechlichen_zeiten(hr_client):
    """Bis Etappe 4 blieben start_time und end_time auf dem Erzeugen-Pfad leer.

    Die Spalten gibt es seit Etappe 2, gefuellt hat sie nur die Handkorrektur.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00',
        'requirements': [0] * 7,
    })
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1},
    ])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    zuweisung = antwort.json['assignments'][0]
    assert zuweisung['start_time'] == '08:00'
    assert zuweisung['end_time'] == '16:00'


def test_ohne_baender_entsteht_kein_plan(hr_client):
    """Gegenprobe: ohne gepflegten Bedarf gibt es nichts zu planen.

    Frueher haette derselbe Aufbau ueber shift_requirements Plaetze erzeugt.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00',
        'requirements': [3] * 7,
    })
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.put('/coverage-requirements', json=[])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['assignments'] == []


def test_generator_schneidet_auf_das_arbeitszeitfenster_zu(hr_client):
    """Stufe 1 und Stufe 2 zusammen, ueber die echte HTTP-Schicht.

    Zwei Plaetze 06:00-14:00, eine uneingeschraenkte Person und eine mit
    Fenster 08:00-14:00. Ohne Zuschnitt bliebe der zweite Platz unbesetzt;
    mit Zuschnitt arbeiten beide.
    """
    hr_client.post('/shift-types', json={
        'name': 'Frueh', 'start_time': '06:00', 'end_time': '14:00',
        'requirements': [0] * 7,
    })
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/employees', json={
        'name': 'Ben',
        'availability_mode': 'windows',
        'availability': [{'weekday': 0, 'start_time': '08:00', 'end_time': '14:00',
                          'valid_from': None, 'valid_until': None}],
    })
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
    ])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    assert antwort.status_code == 201, antwort.json
    erster_montag = _montage(2026, 9)[0].isoformat()
    des_tages = [z for z in antwort.json['assignments'] if z['date'] == erster_montag]
    assert sorted((z['start_time'], z['end_time']) for z in des_tages) == [
        ('06:00', '14:00'), ('08:00', '14:00'),
    ]
    assert all(z['employee_id'] is not None for z in des_tages)


def test_geschlossener_feiertag_bekommt_keine_bloecke(hr_client):
    """Die Oeffnungszeiten rahmen jetzt auch den Generator, nicht nur die
    Lueckenmeldung.

    Ueber eine Datums-Ausnahme, nicht ueber den Wochentag: seit Etappe 3 lehnt
    /business-hours es ab, einen Wochentag zu schliessen, fuer den ein
    Bedarfsband gepflegt ist. Ein geschlossener Tag kann damit nur noch so
    entstehen - und der Test ist dadurch schaerfer, weil die uebrigen Montage
    ihre Bloecke behalten und belegen, dass nicht einfach alles wegfaellt.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00',
        'requirements': [0] * 7,
    })
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1},
    ])
    erster_montag = _montage(2026, 9)[0].isoformat()
    ausnahme = hr_client.post('/business-hours/exceptions', json={
        'date': erster_montag, 'closed': True, 'label': 'Feiertag',
    })
    assert ausnahme.status_code == 201, ausnahme.json

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    assert antwort.status_code == 201, antwort.json
    daten = {z['date'] for z in antwort.json['assignments']}
    assert erster_montag not in daten
    assert daten == {tag.isoformat() for tag in _montage(2026, 9)[1:]}
