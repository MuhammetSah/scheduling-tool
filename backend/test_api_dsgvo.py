"""DSGVO: Auskunft, Loeschung, Aufbewahrung.

Zwei Festlegungen kommen vom Betreiber: sechs Monate Aufbewahrung, und beim
Loeschen wird anonymisiert.

Die Frist gilt ausdruecklich NICHT fuer Zuweisungen - Paragraph 16 Abs. 2 ArbZG
verlangt, Arbeitszeitnachweise mindestens zwei Jahre aufzubewahren. Genau
darauf zielt die wichtigste Gegenprobe hier.
"""

from datetime import date, timedelta


def _mitarbeiter_mit_schichten(hr_client):
    anna = hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com',
        'availability_mode': 'windows',
        'availability': [{'weekday': 0, 'start_time': '08:00', 'end_time': '16:00',
                          'valid_from': None, 'valid_until': None}],
    }).json
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}])
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})
    return anna


def _zuweisungen_von(hr_client, employee_id):
    plan = hr_client.get('/schedules/2026/3').json
    return [z for z in plan['assignments'] if z['employee_id'] == employee_id]


# ---------- Loeschen heisst anonymisieren ----------


def test_loeschen_entfernt_die_person_aus_der_liste(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)

    antwort = hr_client.delete(f'/employees/{anna["id"]}')

    assert antwort.status_code == 200, antwort.json
    assert hr_client.get('/employees').json == []


def test_die_vergangenen_schichten_bleiben_der_zeile_zugeordnet(hr_client):
    """Der Kern der Entscheidung.

    ON DELETE SET NULL wuerde sie auf "unbesetzt" setzen - die Vergangenheit
    saehe unterbesetzt aus, Deckungsluecken erschienen rueckwirkend, und die
    Arbeitszeitaufzeichnung nach Paragraph 16 Abs. 2 ArbZG verloere die
    Zuordnung, die sie ausmacht.
    """
    anna = _mitarbeiter_mit_schichten(hr_client)
    vorher = len(_zuweisungen_von(hr_client, anna['id']))
    assert vorher > 0

    hr_client.delete(f'/employees/{anna["id"]}')

    assert len(_zuweisungen_von(hr_client, anna['id'])) == vorher


def test_die_schichten_werden_nicht_unbesetzt(hr_client):
    """Die Gegenprobe: ohne sie waere ein Verhalten ebenfalls gruen, das die
    Zeile stehen laesst und die Zuweisungen trotzdem loesloest."""
    anna = _mitarbeiter_mit_schichten(hr_client)

    hr_client.delete(f'/employees/{anna["id"]}')

    plan = hr_client.get('/schedules/2026/3').json
    assert plan['unfilled_count'] == 0
    assert not any(z['employee_id'] is None for z in plan['assignments'])


def test_der_name_ist_ersetzt_und_die_email_weg(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)

    hr_client.delete(f'/employees/{anna["id"]}')

    gelesen = hr_client.get(f'/employees/{anna["id"]}').json
    assert gelesen['name'] == f'Gelöschter Mitarbeiter #{anna["id"]}'
    assert gelesen['email'] is None
    assert gelesen['active'] is False


def test_das_persoenliche_daneben_ist_geloescht(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)
    hr_client.post(f'/employees/{anna["id"]}/absences',
                   json={'date': date.today().isoformat(), 'type': 'sick'})

    hr_client.delete(f'/employees/{anna["id"]}')

    gelesen = hr_client.get(f'/employees/{anna["id"]}').json
    assert gelesen['availability'] == []
    assert hr_client.get(f'/employees/{anna["id"]}/absences').json == []


def test_der_abwesenheitsgrund_wird_auch_in_der_zuweisung_anonymisiert(hr_client):
    """Derselbe doppelte Speicherort wie beim Raeumen - hier beim Loeschen.

    Der Grund steht in employee_absences UND denormalisiert in der Zuweisung,
    die er freigemacht hat. Nur die Tabelle zu leeren liesse die
    Gesundheitsangabe samt Personenbezug im Dienstplan stehen, bis Monate
    spaeter die Aufbewahrungsfrist greift.
    """
    from app import get_db

    anna = _mitarbeiter_mit_schichten(hr_client)
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 9, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time, absence_type, absent_employee_id) '
            "VALUES (?, '2026-09-15', NULL, 0, NULL, '08:00', '16:00', 'sick', ?)",
            (schedule_id, anna['id']))
        connection.commit()

    hr_client.delete(f'/employees/{anna["id"]}')

    with hr_client.application.app_context():
        cursor = get_db().cursor()
        cursor.execute(
            'SELECT COUNT(*) AS anzahl FROM shift_assignments '
            'WHERE absent_employee_id = ? OR (absence_type IS NOT NULL '
            "AND date = '2026-09-15')", (anna['id'],))
        assert cursor.fetchone()['anzahl'] == 0


def test_die_zuweisung_selbst_bleibt_dabei_stehen(hr_client):
    """Gegenprobe: die Vertretungsschicht zu loeschen waere Geschichtsklitterung
    - und ein Verstoss gegen Paragraph 16 Abs. 2 ArbZG."""
    from app import get_db

    anna = _mitarbeiter_mit_schichten(hr_client)
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 9, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time, absence_type, absent_employee_id) '
            "VALUES (?, '2026-09-15', NULL, 0, NULL, '08:00', '16:00', 'sick', ?)",
            (schedule_id, anna['id']))
        connection.commit()

    hr_client.delete(f'/employees/{anna["id"]}')

    with hr_client.application.app_context():
        cursor = get_db().cursor()
        cursor.execute(
            "SELECT COUNT(*) AS anzahl FROM shift_assignments WHERE date = '2026-09-15'")
        assert cursor.fetchone()['anzahl'] == 1


# ---------- Auskunft (Art. 15) ----------


def test_die_auskunft_enthaelt_stammdaten_und_schichten(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)

    daten = hr_client.get(f'/employees/{anna["id"]}/data-export').json

    assert daten['employee']['name'] == 'Anna'
    assert daten['assignments']
    assert 'absences' in daten and 'accounts' in daten and 'audit_log' in daten


def test_die_auskunft_enthaelt_keinen_passwort_hash(hr_client):
    """Das eine Feld, dessen Preisgabe die Auskunft selbst zum
    Sicherheitsproblem machte."""
    anna = _mitarbeiter_mit_schichten(hr_client)
    hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']})

    daten = hr_client.get(f'/employees/{anna["id"]}/data-export').json

    assert daten['accounts']
    assert all('hash' not in konto for konto in daten['accounts'])


def test_ein_mitarbeiter_bekommt_seine_eigene_auskunft(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.get(f'/employees/{anna["id"]}/data-export').status_code == 200


def test_eine_fremde_auskunft_ist_verboten(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)
    berta = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'berta', 'role': 'employee', 'employee_id': berta['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.get(f'/employees/{anna["id"]}/data-export').status_code == 403


# ---------- Aufbewahrung ----------


def _alte_abwesenheit(hr_client, employee_id, tage_zurueck):
    """Direkt in der Datenbank: die API laesst nur den laufenden Monat zu."""
    from app import get_db

    tag = (date.today() - timedelta(days=tage_zurueck)).isoformat()
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO employee_absences (employee_id, date, absence_type) VALUES (?, ?, ?)',
            (employee_id, tag, 'sick'))
        connection.commit()
    return tag


def test_alte_abwesenheiten_werden_geraeumt(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)
    _alte_abwesenheit(hr_client, anna['id'], 400)

    antwort = hr_client.post('/retention/purge')

    assert antwort.status_code == 200, antwort.json
    assert antwort.json['retention_months'] == 6
    assert antwort.json['removed']['absences'] == 1


def test_junge_abwesenheiten_bleiben(hr_client):
    """Gegenprobe: ohne sie waere ein Raeumen, das alles loescht, ebenfalls gruen.

    Abgefragt wird ausdruecklich der Monat der Abwesenheit - die Liste
    filtert danach, und 30 Tage zurueck liegen oft im Vormonat.
    """
    anna = _mitarbeiter_mit_schichten(hr_client)
    tag = date.fromisoformat(_alte_abwesenheit(hr_client, anna['id'], 30))

    hr_client.post('/retention/purge')

    verblieben = hr_client.get(
        f'/employees/{anna["id"]}/absences',
        query_string={'year': tag.year, 'month': tag.month}).json
    assert [a['date'] for a in verblieben] == [tag.isoformat()]


def test_der_abwesenheitsgrund_wird_auch_in_der_zuweisung_geraeumt(hr_client):
    """Der Punkt, den man uebersieht: der Grund steht doppelt.

    Nur employee_absences zu raeumen liesse die Gesundheitsangabe im
    Dienstplan stehen.
    """
    from app import get_db

    anna = _mitarbeiter_mit_schichten(hr_client)
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2024, 1, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time, absence_type, absent_employee_id) '
            "VALUES (?, '2024-01-15', NULL, 0, NULL, '08:00', '16:00', 'sick', ?)",
            (schedule_id, anna['id']))
        connection.commit()

    antwort = hr_client.post('/retention/purge')

    assert antwort.json['removed']['assignment_absence_marks'] == 1


def test_die_zuweisungen_selbst_bleiben_stehen(hr_client):
    """Paragraph 16 Abs. 2 ArbZG: Arbeitszeitnachweise mindestens zwei Jahre.

    Ein Raeumen, das den Plan mitnimmt, braeche eine Norm, um eine andere zu
    erfuellen.
    """
    anna = _mitarbeiter_mit_schichten(hr_client)
    vorher = len(_zuweisungen_von(hr_client, anna['id']))

    hr_client.post('/retention/purge')

    assert len(_zuweisungen_von(hr_client, anna['id'])) == vorher


def test_die_frist_laesst_sich_aendern(hr_client):
    hr_client.put('/settings', json={'retention_months': '12'})

    assert hr_client.post('/retention/purge').json['retention_months'] == 12


def test_das_raeumen_ist_hr_vorbehalten(hr_client):
    anna = _mitarbeiter_mit_schichten(hr_client)
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.post('/retention/purge').status_code == 403
