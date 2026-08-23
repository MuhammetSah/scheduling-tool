"""Der gefuehrte Schichttausch, und wo das Gesetz ihm widerspricht.

Ein Tausch ist der einzige Vorgang im Tool, der die Belastung von ZWEI
Menschen gleichzeitig aendert. Beide Seiten muessen geprueft werden, und zwar
in dem Zustand, den der Tausch herstellen wuerde - nicht im heutigen.

Die tragende Entscheidung dieser Etappe: ein von Mitarbeitern beantragter
Tausch wird ABGELEHNT, wenn er zwingendes Arbeitszeitrecht braeche. Die
Handkorrektur der Personalabteilung warnt weiterhin nur.

Der Grund steht in Paragraph 22 Abs. 1 ArbZG: ein Verstoss ist eine
Ordnungswidrigkeit des ARBEITGEBERS. Paragraph 3 und Paragraph 5 lassen sich
nicht durch Einzelabrede abbedingen - nur nach Paragraph 7 durch Tarifvertrag,
den dieses Tool nicht abbildet. Zwei Kolleginnen, die einen rechtswidrigen
Tausch unter sich verabreden und der Personalabteilung die vollendete Tatsache
vorlegen, verschoeben eine Haftung, die das Gesetz beim Arbeitgeber verortet.
"""


def _betrieb(hr_client, **abweichend):
    """Zwei Mitarbeiter und eine Schichtart."""
    daten = {'min_rest_hours': 11}
    daten.update(abweichend)
    anna = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com', **daten}).json
    berta = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com', **daten}).json
    hr_client.post('/shift-types', json={
        'name': 'Frueh', 'start_time': '06:00', 'end_time': '14:00'})
    return anna, berta


def _plan_mit(hr_client, zuweisungen, status='published'):
    """Ein Septemberplan mit genau diesen Bloecken.

    Direkt in die Datenbank: der Generator entscheidet selbst, wer wo steht,
    und diese Tests brauchen eine bekannte Ausgangslage.
    """
    from app import get_db

    ids = []
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO schedules (year, month, status, published_at) '
            'VALUES (2026, 9, ?, CURRENT_TIMESTAMP)', (status,))
        schedule_id = cursor.lastrowid
        for index, (employee_id, tag, start, ende) in enumerate(zuweisungen):
            cursor.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
                'employee_id, start_time, end_time) VALUES (?, ?, NULL, ?, ?, ?, ?)',
                (schedule_id, tag, index, employee_id, start, ende))
            ids.append(cursor.lastrowid)
        connection.commit()
    return ids


def _konto(hr_client, employee, username):
    return hr_client.post('/register', json={
        'username': username, 'role': 'employee', 'employee_id': employee['id']}).json


def _als(hr_client, konto):
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']


def _als_hr(hr_client):
    hr_client.post('/logout')
    hr_client.post('/login', json={'username': 'hr', 'password': 'passwort-123'})


# ---------- Der harmlose Tausch ----------


def test_ein_unbedenklicher_tausch_laeuft_durch(hr_client):
    """Gegenprobe zuerst, und die wichtigste: das Ganze muss funktionieren.

    Ohne sie waere eine Umsetzung, die jeden Tausch ablehnt, ebenfalls gruen.
    """
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    assert antrag.get('id'), antrag

    _als(hr_client, berta_konto)
    assert hr_client.put('/swap-requests/%d/status' % antrag['id'],
                         json={'status': 'accepted',
                               'my_assignment_id': b}).status_code == 200

    _als_hr(hr_client)
    assert hr_client.put('/swap-requests/%d/status' % antrag['id'],
                         json={'status': 'approved'}).status_code == 200

    plan = hr_client.get('/schedules/2026/9').json
    nach_tag = {z['date']: z['employee_id'] for z in plan['assignments']}
    assert nach_tag['2026-09-07'] == berta['id']
    assert nach_tag['2026-09-14'] == anna['id']


# ---------- Wo das Gesetz widerspricht ----------


def test_ein_tausch_der_die_ruhezeit_braeche_wird_abgelehnt(hr_client):
    """Paragraph 5 Abs. 1 ArbZG, und der Kern dieser Etappe.

    Berta arbeitet am 6. September bis 22:00. Wuerde sie Annas Fruehschicht
    am 7. ab 06:00 uebernehmen, blieben acht Stunden statt elf.
    """
    anna, berta = _betrieb(hr_client)
    a, b, _ = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
        (berta['id'], '2026-09-06', '14:00', '22:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': b})

    assert antwort.status_code == 409, antwort.json
    assert antwort.json['blockers'], antwort.json


def test_die_pruefung_sieht_auch_den_antragsteller(hr_client):
    """Ein Tausch aendert die Belastung von zwei Menschen.

    Nur die Gegenseite zu pruefen hiesse, die Haelfte der Faelle
    durchzulassen - hier ist es der Antragsteller selbst, dem die Ruhezeit
    fehlen wuerde.
    """
    anna, berta = _betrieb(hr_client)
    a, b, _ = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
        (anna['id'], '2026-09-13', '14:00', '22:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': b})

    assert antwort.status_code == 409, antwort.json


def test_eine_hausregel_haelt_den_antrag_nicht_auf(hr_client):
    """Die Gegenprobe zur Rechtsfrage, und der Grund fuer die Unterscheidung.

    Ein gesperrter Wochentag ist eine Absprache, kein Gesetz. Er wird gemeldet
    und der Personalabteilung vorgelegt - blockieren duerfte ihn nur, wer
    Absprache und Gesetz fuer dasselbe haelt.
    """
    anna, berta = _betrieb(hr_client)
    hr_client.put('/employees/%d' % berta['id'], json={
        'name': 'Berta', 'email': 'berta@example.com', 'unavailable_weekdays': [0]})
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),   # ein Montag
        (berta['id'], '2026-09-15', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': b})

    assert antwort.status_code == 200, antwort.json
    assert antwort.json['warnings'], 'die Absprache muss trotzdem sichtbar sein'


def test_die_personalabteilung_darf_weiterhin_von_hand_tauschen(hr_client):
    """Die zweite Haelfte der Entscheidung.

    Der Direkttausch der Personalabteilung warnt wie bisher, statt zu
    blockieren: sie traegt die Verantwortung und kann etwas wissen, das das
    Tool nicht weiss - einen Notfall nach Paragraph 14 etwa, oder einen
    Tarifvertrag nach Paragraph 7.
    """
    anna, berta = _betrieb(hr_client)
    a, b, _ = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
        (berta['id'], '2026-09-06', '14:00', '22:00'),
    ])

    antwort = hr_client.post('/assignments/swap', json={
        'assignment_id_a': a, 'assignment_id_b': b})

    assert antwort.status_code == 200, antwort.json
    assert any('Ruhezeit' in w for w in antwort.json['warnings']), antwort.json


# ---------- Wer darf was ----------


def test_ein_fremder_platz_ist_nicht_meiner(hr_client):
    """Der Antrag geht immer von der eigenen Schicht aus. Sonst liesse sich
    der Dienstplan zweier anderer Leute untereinander umsortieren."""
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    # Berta bietet Annas Schicht an.
    _als(hr_client, berta_konto)
    antwort = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': anna['id']})

    assert antwort.status_code == 403


def test_nur_der_tauschpartner_stimmt_zu(hr_client):
    """Sonst wuerde der Antragsteller im Namen des anderen zustimmen."""
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json

    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': b})

    assert antwort.status_code == 403


def test_die_zustimmung_allein_tauscht_noch_nichts(hr_client):
    """Der dritte Schritt ist keine Foermelei.

    Das Arbeitszeitgesetz richtet sich an den Arbeitgeber, und die
    Aufzeichnungspflicht aus Paragraph 16 Abs. 2 trifft ebenfalls ihn.
    """
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    hr_client.put('/swap-requests/%d/status' % antrag['id'],
                  json={'status': 'accepted', 'my_assignment_id': b})

    _als_hr(hr_client)
    plan = hr_client.get('/schedules/2026/9').json
    nach_tag = {z['date']: z['employee_id'] for z in plan['assignments']}
    assert nach_tag['2026-09-07'] == anna['id'], 'getauscht wurde ohne Genehmigung'


def test_ein_mitarbeiter_genehmigt_nicht_selbst(hr_client):
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    hr_client.put('/swap-requests/%d/status' % antrag['id'],
                  json={'status': 'accepted', 'my_assignment_id': b})

    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'approved'})

    assert antwort.status_code == 403


def test_die_personalabteilung_genehmigt_nicht_vor_der_zustimmung(hr_client):
    """Ohne die Zustimmung des Partners waere es kein Tausch, sondern eine
    Umsetzung - und die hat ihren eigenen, ehrlicheren Weg."""
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json

    _als_hr(hr_client)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'approved'})

    assert antwort.status_code == 409


# ---------- Der Zustand aendert sich zwischen Antrag und Genehmigung ----------


def test_die_pruefung_laeuft_bei_der_genehmigung_erneut(hr_client):
    """Zwischen Antrag und Genehmigung liegen Tage.

    Wer nur beim Antrag prueft, genehmigt spaeter einen Tausch, der inzwischen
    rechtswidrig geworden ist - und die Pruefung von damals steht als Beleg
    dafuer in der Akte, dass alles geprueft worden sei.
    """
    from app import get_db

    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    hr_client.put('/swap-requests/%d/status' % antrag['id'],
                  json={'status': 'accepted', 'my_assignment_id': b})

    # Erst jetzt bekommt Berta eine Spaetschicht am Vorabend des 7.
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute('SELECT id FROM schedules WHERE year = 2026 AND month = 9')
        schedule_id = cursor.fetchone()['id']
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-09-06', NULL, 9, ?, '14:00', '22:00')",
            (schedule_id, berta['id']))
        connection.commit()

    _als_hr(hr_client)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'approved'})

    assert antwort.status_code == 409, antwort.json
    assert antwort.json['blockers'], antwort.json


def test_der_abgelehnte_antrag_hat_nichts_getauscht(hr_client):
    """Gegenprobe: eine Ablehnung, die trotzdem tauscht, waere das
    Schlimmste von beidem."""
    from app import get_db

    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    hr_client.put('/swap-requests/%d/status' % antrag['id'],
                  json={'status': 'accepted', 'my_assignment_id': b})

    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute('SELECT id FROM schedules WHERE year = 2026 AND month = 9')
        schedule_id = cursor.fetchone()['id']
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-09-06', NULL, 9, ?, '14:00', '22:00')",
            (schedule_id, berta['id']))
        connection.commit()

    _als_hr(hr_client)
    hr_client.put('/swap-requests/%d/status' % antrag['id'], json={'status': 'approved'})

    plan = hr_client.get('/schedules/2026/9').json
    nach_tag = {}
    for z in plan['assignments']:
        nach_tag.setdefault(z['date'], []).append(z['employee_id'])
    assert anna['id'] in nach_tag['2026-09-07']


# ---------- Nur veroeffentlichte Plaene ----------


def test_ein_entwurf_laesst_sich_nicht_tauschen(hr_client):
    """Ein Entwurf ist fuer Mitarbeiter nicht vorhanden (Etappe 5f).

    Ein Tauschantrag darauf waere die Hintertuer durch die Wand daneben: er
    verriete, dass es einen Plan gibt, und woraus er besteht.
    """
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ], status='draft')
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antwort = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    assert antwort.status_code == 404


# ---------- Die eigene Liste ----------


def test_jeder_sieht_seine_eigenen_antraege(hr_client):
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    assert len(hr_client.get('/swap-requests').json) == 1
    _als(hr_client, berta_konto)
    assert len(hr_client.get('/swap-requests').json) == 1


def test_ein_unbeteiligter_sieht_den_antrag_nicht(hr_client):
    """Gegenprobe: wer wann mit wem tauschen will, geht Dritte nichts an."""
    anna, berta = _betrieb(hr_client)
    clara = hr_client.post('/employees', json={
        'name': 'Clara', 'email': 'clara@example.com'}).json
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')
    clara_konto = _konto(hr_client, clara, 'clara')

    _als(hr_client, anna_konto)
    hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    _als(hr_client, clara_konto)
    assert hr_client.get('/swap-requests').json == []


def test_die_personalabteilung_sieht_alle(hr_client):
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    _als_hr(hr_client)
    assert len(hr_client.get('/swap-requests').json) == 1


def test_ein_antragsteller_kann_zuruecknehmen(hr_client):
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json

    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'withdrawn'})

    assert antwort.status_code == 200, antwort.json
    assert hr_client.get('/swap-requests').json[0]['status'] == 'withdrawn'


def test_ein_erledigter_antrag_aendert_seinen_stand_nicht_mehr(hr_client):
    """Sonst liesse sich ein genehmigter Tausch nachtraeglich in einen
    abgelehnten umschreiben - und der Plan spraeche dann gegen die Akte."""
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    hr_client.put('/swap-requests/%d/status' % antrag['id'],
                  json={'status': 'accepted', 'my_assignment_id': b})
    _als_hr(hr_client)
    hr_client.put('/swap-requests/%d/status' % antrag['id'], json={'status': 'approved'})

    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'rejected'})

    assert antwort.status_code == 409


# ---------- Warum erst getauscht und dann geprueft wird ----------


def test_ein_tausch_der_die_ruhezeit_erst_herstellt_wird_nicht_abgelehnt(hr_client):
    """Der Fall, der die Reihenfolge entscheidet.

    Anna hat die Nacht vom 7. auf den 8. (22:00-06:00), Berta den Fruehdienst
    am 8. Nach dem Tausch haelt Berta die Nacht und Anna den Fruehdienst -
    beide sauber, jeder nur eine Schicht.

    Wer VOR dem Tausch prueft, sieht Berta mit der Nacht vom 7. UND ihrem noch
    nicht abgegebenen Fruehdienst am 8.: null Stunden Ruhe, Antrag abgelehnt.
    Ein Tausch, den das Gesetz nicht verbietet, scheitert dann an der
    Reihenfolge der Pruefung.

    Deshalb fuehrt perform_swap() den Tausch aus und liest danach - und die
    Aufrufer, die nur gefragt haben, rollen zurueck.
    """
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '22:00', '06:00'),
        (berta['id'], '2026-09-08', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json
    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': b})

    assert antwort.status_code == 200, antwort.json


def test_die_probe_hinterlaesst_keinen_getauschten_plan(hr_client):
    """Gegenprobe zur Reihenfolge: perform_swap() schreibt wirklich, und der
    Antragsweg muss das wirklich zuruecknehmen.

    Ohne das Zuruecknehmen waere der Tausch schon mit dem Antrag vollzogen -
    ohne Zustimmung, ohne Genehmigung, und niemandem faellt es auf, weil der
    Antrag danach brav als "offen" in der Liste steht.
    """
    anna, berta = _betrieb(hr_client)
    a, b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    _als_hr(hr_client)
    plan = hr_client.get('/schedules/2026/9').json
    nach_tag = {z['date']: z['employee_id'] for z in plan['assignments']}
    assert nach_tag['2026-09-07'] == anna['id']
    assert nach_tag['2026-09-14'] == berta['id']


# ---------- Die Kollegenliste, und wie klein sie bleibt ----------


def test_ein_mitarbeiter_bekommt_die_namensliste(hr_client):
    """Ohne sie kann niemand einen Tauschpartner nennen."""
    anna, berta = _betrieb(hr_client)
    anna_konto = _konto(hr_client, anna, 'anna')

    _als(hr_client, anna_konto)
    namen = hr_client.get('/colleagues').json

    assert sorted(k['name'] for k in namen) == ['Anna', 'Berta']


def test_die_namensliste_verraet_keine_schichten(hr_client):
    """Gegenprobe, und der Grund fuer diese Route.

    Der Antrag nennt eine Person statt einer fremden Schicht, damit die
    Datensparsamkeit aus Etappe 5f stehen bleibt. Eine Liste, die nebenbei
    Dienste ausplaudert, nimmt genau das zurueck.
    """
    anna, berta = _betrieb(hr_client)
    _plan_mit(hr_client, [(berta['id'], '2026-09-14', '06:00', '14:00')])
    anna_konto = _konto(hr_client, anna, 'anna')

    _als(hr_client, anna_konto)
    namen = hr_client.get('/colleagues').json

    assert all(set(k) == {'id', 'name'} for k in namen), namen


def test_ein_anonymisierter_datensatz_steht_nicht_in_der_liste(hr_client):
    """Ein Grabstein ist kein Kollege (siehe Etappe 5i)."""
    anna, berta = _betrieb(hr_client)
    anna_konto = _konto(hr_client, anna, 'anna')
    hr_client.delete('/employees/%d' % berta['id'])

    _als(hr_client, anna_konto)
    namen = hr_client.get('/colleagues').json

    assert [k['name'] for k in namen] == ['Anna']


# ---------- Die Zustimmung braucht eine eigene Schicht ----------


def test_zustimmen_ohne_gegenschicht_geht_nicht(hr_client):
    """Zustimmen heisst benennen, was man dafuer hergibt."""
    anna, berta = _betrieb(hr_client)
    a, _b = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json

    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted'})

    assert antwort.status_code == 400


def test_die_gegenschicht_muss_dem_partner_gehoeren(hr_client):
    """Sonst verschenkte der Partner die Schicht eines Dritten."""
    anna, berta = _betrieb(hr_client)
    clara = hr_client.post('/employees', json={
        'name': 'Clara', 'email': 'clara@example.com'}).json
    a, _b, c = _plan_mit(hr_client, [
        (anna['id'], '2026-09-07', '06:00', '14:00'),
        (berta['id'], '2026-09-14', '06:00', '14:00'),
        (clara['id'], '2026-09-21', '06:00', '14:00'),
    ])
    anna_konto = _konto(hr_client, anna, 'anna')
    berta_konto = _konto(hr_client, berta, 'berta')

    _als(hr_client, anna_konto)
    antrag = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']}).json

    _als(hr_client, berta_konto)
    antwort = hr_client.put('/swap-requests/%d/status' % antrag['id'],
                            json={'status': 'accepted', 'my_assignment_id': c})

    assert antwort.status_code == 403


def test_ein_antrag_auf_eine_person_ohne_schicht_bleibt_offen(hr_client):
    """Gegenprobe zur Reihenfolge: der Antrag selbst prueft nichts Rechtliches,
    weil erst eine der beiden Schichten feststeht. Er darf deshalb auch nicht
    an einer scheitern, die es noch gar nicht gibt."""
    anna, berta = _betrieb(hr_client)
    a, = _plan_mit(hr_client, [(anna['id'], '2026-09-07', '06:00', '14:00')])
    anna_konto = _konto(hr_client, anna, 'anna')

    _als(hr_client, anna_konto)
    antwort = hr_client.post('/swap-requests', json={
        'my_assignment_id': a, 'partner_employee_id': berta['id']})

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['status'] == 'pending'
    assert antwort.json['partner']['shift'] is None
