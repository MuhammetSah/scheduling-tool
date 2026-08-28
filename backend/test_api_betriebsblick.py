"""Was das Werkzeug von sich aus sagt, statt es jemanden herausfinden zu lassen.

Drei Befunde aus einem Durchlauf als Personalabteilung und als Mitarbeiter,
die alle dieselbe Form haben: das Werkzeug tut das Richtige und schweigt
darueber, und das Schweigen ist der Fehler.

- Wer jemanden inaktiv setzt, sieht danach einen Plan, in dem die Person
  weiter eingeteilt ist.
- Wer niemandem Wochenstunden gibt, bekommt Wochen mit sechsundvierzig
  Stunden, ohne dass irgendwo etwas stand.
- Die Aufbewahrungsfrist lief nur beim Start oder auf Knopfdruck.
"""

from datetime import date, timedelta


def _mitarbeiter(hr_client, name='Anna', **felder):
    return hr_client.post('/employees', json={'name': name, **felder}).json


def _plan_mit_einer_schicht(hr_client, employee_id, tag):
    """Eine einzelne Zuweisung, an der Regeln haengen koennen.

    Ueber die API einen ganzen Monat zu erzeugen braeuchte Oeffnungszeiten,
    Bedarfsbaender und eine Schichtart; hier geht es nur darum, dass ueberhaupt
    eine Zuweisung in der Zukunft existiert.
    """
    import app as app_module
    with app_module.app.app_context():
        connection = app_module.get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (?, ?, 'published')",
            (tag.year, tag.month))
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, employee_id, slot_index, '
            'start_time, end_time) VALUES (?, ?, ?, 0, ?, ?)',
            (schedule_id, tag.isoformat(), employee_id, '08:00', '16:30'))
        connection.commit()


# ---------- inaktiv gesetzt und trotzdem im Plan ----------


def test_inaktiv_setzen_meldet_die_offenen_schichten(hr_client):
    anna = _mitarbeiter(hr_client)
    _plan_mit_einer_schicht(hr_client, anna['id'], date.today() + timedelta(days=3))

    antwort = hr_client.put(f'/employees/{anna["id"]}',
                            json={'name': 'Anna', 'active': False})

    assert antwort.status_code == 200
    assert antwort.json['active'] is False
    assert len(antwort.json['warnings']) == 1
    assert 'Anna' in antwort.json['warnings'][0]


def test_die_zuweisungen_bleiben_trotz_der_warnung_stehen(hr_client):
    """Warnen, nicht raeumen.

    Einen veroeffentlichten Plan hinter dem Ruecken aller zu leeren waere
    schlimmer als der stille Zustand vorher - und wuerde die
    Arbeitszeitaufzeichnung nach Paragraph 16 Abs. 2 ArbZG verkuerzen.
    """
    anna = _mitarbeiter(hr_client)
    morgen = date.today() + timedelta(days=1)
    _plan_mit_einer_schicht(hr_client, anna['id'], morgen)

    hr_client.put(f'/employees/{anna["id"]}', json={'name': 'Anna', 'active': False})

    plan = hr_client.get(f'/schedules/{morgen.year}/{morgen.month}').json
    assert [a['employee_id'] for a in plan['assignments']] == [anna['id']]


def test_ohne_offene_schichten_keine_warnung(hr_client):
    anna = _mitarbeiter(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}',
                            json={'name': 'Anna', 'active': False})

    assert antwort.json['warnings'] == []


def test_vergangene_schichten_zaehlen_nicht(hr_client):
    """Sie sind Aufzeichnung, keine Planung - ein Hinweis, gegen den sich
    nichts tun laesst, ist keiner."""
    anna = _mitarbeiter(hr_client)
    _plan_mit_einer_schicht(hr_client, anna['id'], date.today() - timedelta(days=10))

    antwort = hr_client.put(f'/employees/{anna["id"]}',
                            json={'name': 'Anna', 'active': False})

    assert antwort.json['warnings'] == []


def test_wer_aktiv_bleibt_bekommt_keine_warnung(hr_client):
    anna = _mitarbeiter(hr_client)
    _plan_mit_einer_schicht(hr_client, anna['id'], date.today() + timedelta(days=3))

    antwort = hr_client.put(f'/employees/{anna["id"]}',
                            json={'name': 'Anna Neu', 'active': True})

    assert antwort.json['warnings'] == []


# ---------- Wochenstunden, die niemand gesetzt hat ----------


def test_fehlende_wochenstunden_stehen_als_hinweis(hr_client):
    _mitarbeiter(hr_client, 'Anna')
    _mitarbeiter(hr_client, 'Bernd', weekly_hours=30)

    hinweise = {h['key']: h for h in hr_client.get('/setup-status').json['notes']}

    assert 'weekly_hours' in hinweise
    assert '1' in hinweise['weekly_hours']['text']
    assert hinweise['weekly_hours']['route'] == '/employees'


def test_mit_wochenstunden_ueberall_kein_hinweis(hr_client):
    _mitarbeiter(hr_client, 'Anna', weekly_hours=30)
    _mitarbeiter(hr_client, 'Bernd', weekly_hours=20)

    schluessel = {h['key'] for h in hr_client.get('/setup-status').json['notes']}

    assert 'weekly_hours' not in schluessel


def test_der_hinweis_haelt_den_plan_nicht_auf(hr_client):
    """`notes` ist die andere Sorte: wissenswert, verhindert nichts."""
    _mitarbeiter(hr_client, 'Anna')
    hr_client.post('/shift-types', json={
        'name': 'Frueh', 'start_time': '08:00', 'end_time': '16:30'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': tag, 'start_time': '08:00', 'end_time': '16:30', 'required_count': 1}
        for tag in range(7)])

    stand = hr_client.get('/setup-status').json

    assert stand['ready'] is True
    assert any(h['key'] == 'weekly_hours' for h in stand['notes'])


# ---------- Aufbewahrungsfrist, die von selbst laeuft ----------


def test_die_erste_anfrage_des_tages_raeumt_auf(hr_client):
    """Vorher lief die Frist nur beim Start oder auf Knopfdruck - und der
    Keepalive-Auftrag haelt den Dienst wochenlang wach."""
    import app as app_module

    alt = (date.today() - timedelta(days=400)).isoformat()
    with app_module.app.app_context():
        connection = app_module.get_db()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO employees (name, active) VALUES ('Anna', 1)")
        employee_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO employee_absences (employee_id, date, absence_type) "
            "VALUES (?, ?, 'sick')", (employee_id, alt))
        cursor.execute("DELETE FROM settings WHERE name = ?",
                       (app_module.PURGE_MARKER_SETTING,))
        connection.commit()
    app_module._purge_checked_on = None

    hr_client.get('/shift-types')

    with app_module.app.app_context():
        cursor = app_module.get_db().cursor()
        cursor.execute('SELECT COUNT(*) AS n FROM employee_absences')
        assert cursor.fetchone()['n'] == 0


def test_der_zweite_aufruf_am_selben_tag_raeumt_nicht_erneut(hr_client):
    """Einmal am Tag, danach ohne eine einzige Abfrage."""
    import app as app_module

    app_module._purge_checked_on = None
    hr_client.get('/shift-types')
    assert app_module._purge_checked_on == app_module.timeutil.today_local().isoformat()

    with app_module.app.app_context():
        cursor = app_module.get_db().cursor()
        cursor.execute('SELECT value FROM settings WHERE name = ?',
                       (app_module.PURGE_MARKER_SETTING,))
        assert cursor.fetchone()['value'] == app_module.timeutil.today_local().isoformat()


def test_die_merkzeile_ist_keine_einstellung(hr_client):
    """Sie steht in derselben Tabelle, aber niemand trifft sie."""
    app_module_settings = hr_client.get('/settings').json

    assert 'last_retention_purge' not in app_module_settings
    assert hr_client.put('/settings', json={'last_retention_purge': '2020-01-01'}
                         ).status_code == 400


# ---------- der Nachweiskatalog ist nicht fuer alle ----------


def test_der_nachweiskatalog_ist_hr_vorbehalten(hr_client):
    anna = _mitarbeiter(hr_client)
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id'],
        'email': 'anna@example.com'}).json

    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.get('/qualifications').status_code == 403
