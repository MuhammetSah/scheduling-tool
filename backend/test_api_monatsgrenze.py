"""Was der Generator am Monatswechsel nicht sah.

Der Sechs-Tage-Lauf und das Sonntagsbudget kommen seit Etappe 5b ueber
scheduling_history() aus der Datenbank und sehen die Grenze. Die Ruhezeit nach
Paragraph 5 Abs. 1 ArbZG und die Wochenstunden sahen sie nicht: beide leben
ausschliesslich im Suchzustand eines Laufs, und der beginnt am Ersten leer.

Die Folge ist ein Plan, der fuer sich genommen jede Regel einhaelt und an
genau einer Stelle im Jahr - dem Monatswechsel - eine bricht.
"""

from datetime import date


def _nachtdienst_am_monatsende(hr_client, employee_id):
    """Einen Block am 31.08. von Hand in den Augustplan setzen.

    Ueber die Datenbank statt ueber die API: die Handkorrektur haengt an
    Deckungsbaendern, und der Test will nur den einen Block.
    """
    from app import get_db

    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 8, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-08-31', NULL, 0, ?, '22:00', '06:00')",
            (schedule_id, employee_id))
        connection.commit()


def _aufbau(hr_client, **abweichend):
    daten = {'name': 'Anna', 'email': 'anna@example.com', 'min_rest_hours': 11}
    daten.update(abweichend)
    anna = hr_client.post('/employees', json=daten).json
    hr_client.post('/shift-types', json={
        'name': 'Frueh', 'start_time': '06:00', 'end_time': '14:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '06:00', 'end_time': '14:00', 'required_count': 1}
        for wd in range(7)])
    return anna


def test_die_ruhezeit_gilt_auch_ueber_den_monatswechsel(hr_client):
    """Der Kern.

    Ein Nachtdienst bis 06:00 am 31.08. und ein Fruehdienst ab 06:00 am 01.09.
    ergeben null Stunden Ruhe. Paragraph 5 Abs. 1 ArbZG verlangt elf.
    """
    anna = _aufbau(hr_client)
    _nachtdienst_am_monatsende(hr_client, anna['id'])

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert erster, 'am 1. September gibt es keinen Block - der Aufbau stimmt nicht'
    assert all(z['employee_id'] != anna['id'] for z in erster), (
        'Anna wurde am 1. September eingeplant, obwohl sie bis 06:00 desselben '
        'Tages im Augustplan arbeitet'
    )


def test_ohne_nachtdienst_wird_sie_am_ersten_eingeplant(hr_client):
    """Gegenprobe, und die wichtigere Haelfte.

    Ohne sie waere ein Generator, der am Ersten grundsaetzlich niemanden
    einplant, ebenfalls gruen.
    """
    anna = _aufbau(hr_client)

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert any(z['employee_id'] == anna['id'] for z in erster)


def test_ein_frueher_nachtdienst_stoert_den_ersten_nicht(hr_client):
    """Gegenprobe: nur der unmittelbare Nachbartag zaehlt.

    Ein Block am 29.08. laesst bis zum 1. September mehr als genug Ruhe. Wer
    den ganzen Vormonat einbezoege, sperrte den Ersten grundlos.
    """
    from app import get_db

    anna = _aufbau(hr_client)
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 8, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-08-29', NULL, 0, ?, '22:00', '06:00')",
            (schedule_id, anna['id']))
        connection.commit()

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert any(z['employee_id'] == anna['id'] for z in erster)


def test_ohne_ruhezeitvorgabe_bleibt_alles_wie_bisher(hr_client):
    """Gegenprobe: die Pruefung bleibt an min_rest_hours gebunden.

    Wer keine Ruhezeit verlangt, wird von der neuen Sicht ueber die Grenze
    nicht ploetzlich gesperrt - sonst waere aus einem einstellbaren Wert
    stillschweigend eine feste Regel geworden.

    Ausgedrueckt als 0 und nicht als None: die Spalte hat 11 als Vorgabe, und
    ein gesendetes null landet dort. Beim Schreiben dieses Tests zuerst mit
    None versucht, was ihn zu einer zweiten Ausgabe des Haupttests machte -
    gruen vor der Behebung, rot danach, und beides aus dem falschen Grund.
    """
    anna = _aufbau(hr_client, min_rest_hours=0)
    _nachtdienst_am_monatsende(hr_client, anna['id'])

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert any(z['employee_id'] == anna['id'] for z in erster)


# ---------- Die Woche, die ueber die Grenze laeuft ----------


def _bloecke_im_vormonat(hr_client, employee_id, tage, start='08:00', ende='16:00'):
    """Mehrere Achtstundenbloecke Ende August in den gespeicherten Plan."""
    from app import get_db

    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 8, 'published')")
        schedule_id = cursor.lastrowid
        for tag in tage:
            cursor.execute(
                'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
                'employee_id, start_time, end_time) VALUES (?, ?, NULL, 0, ?, ?, ?)',
                (schedule_id, tag, employee_id, start, ende))
        connection.commit()


def test_die_wochenstunden_zaehlen_ueber_den_monatswechsel(hr_client):
    """Der 1. September 2026 ist ein Dienstag.

    Die Kalenderwoche beginnt also am Montag, dem 31. August, und liegt zu
    einem Siebtel im Vormonat. Wer dort schon acht Stunden gearbeitet hat und
    zehn Wochenstunden vereinbart hat, darf im September nicht noch einmal
    acht bekommen - ein leerer Zaehler am Ersten schenkt ihm die ganze Woche
    ein zweites Mal.
    """
    anna = _aufbau(hr_client, weekly_hours=10, min_rest_hours=0)
    _bloecke_im_vormonat(hr_client, anna['id'], ['2026-08-31'])

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    in_der_woche = [z for z in plan['assignments']
                    if z['date'] in ('2026-09-01', '2026-09-02', '2026-09-03',
                                     '2026-09-04', '2026-09-05', '2026-09-06')
                    and z['employee_id'] == anna['id']]
    assert in_der_woche == [], (
        f'Anna bekam {len(in_der_woche)} Bloecke in der Woche, in der sie am '
        '31.08. bereits acht ihrer zehn Stunden gearbeitet hat'
    )


def test_in_der_woche_darauf_arbeitet_sie_wieder(hr_client):
    """Gegenprobe, und die wichtigere Haelfte: gesperrt ist die eine Woche,
    nicht der Mitarbeiter."""
    anna = _aufbau(hr_client, weekly_hours=10, min_rest_hours=0)
    _bloecke_im_vormonat(hr_client, anna['id'], ['2026-08-31'])

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    danach = [z for z in plan['assignments']
              if z['date'] >= '2026-09-07' and z['employee_id'] == anna['id']]
    assert danach, 'Anna arbeitet im ganzen September nicht mehr'


def test_ohne_wochenziel_aendert_sich_nichts(hr_client):
    """Gegenprobe: weekly_hours ist optional und bleibt es."""
    anna = _aufbau(hr_client, min_rest_hours=0)
    _bloecke_im_vormonat(hr_client, anna['id'], ['2026-08-31'])

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert any(z['employee_id'] == anna['id'] for z in erster)


# ---------- Zeiten, die nicht in der Zuweisung stehen ----------


def test_auch_eine_schicht_ohne_eigene_zeiten_begrenzt_die_ruhezeit(hr_client):
    """Beim Nachpruefen dieser Etappe gefunden.

    Eine gespeicherte Zuweisung muss ihre Zeiten nicht selbst tragen: sie kann
    sie aus der Schichtart beziehen oder aus einer Tagesausnahme. Wer nur die
    Spalten start_time/end_time liest, sieht eine solche Nachtschicht gar
    nicht - und plant den Ersten frei, als gaebe es sie nicht.

    assignment_hours() loest genau diese drei Ebenen auf und stand die ganze
    Zeit daneben.
    """
    from app import get_db

    anna = _aufbau(hr_client)
    nacht = hr_client.post('/shift-types', json={
        'name': 'Nacht', 'start_time': '22:00', 'end_time': '06:00'}).json

    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 8, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-08-31', ?, 0, ?, NULL, NULL)",
            (schedule_id, nacht['id'], anna['id']))
        connection.commit()

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert erster, 'am 1. September gibt es keinen Block - der Aufbau stimmt nicht'
    assert all(z['employee_id'] != anna['id'] for z in erster), (
        'Anna wurde am 1. September eingeplant, obwohl ihre Nachtschicht am 31.08. '
        'ihre Zeiten aus der Schichtart bezieht'
    )


def test_eine_schicht_ganz_ohne_ableitbare_zeiten_sperrt_nichts(hr_client):
    """Gegenprobe: ohne Vorlage und ohne eigene Zeiten gibt es keine
    Minutenachse. Daraus eine Sperre zu machen hiesse zu raten."""
    from app import get_db

    anna = _aufbau(hr_client)
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO schedules (year, month, status) VALUES (2026, 8, 'published')")
        schedule_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
            'employee_id, start_time, end_time) '
            "VALUES (?, '2026-08-31', NULL, 0, ?, NULL, NULL)",
            (schedule_id, anna['id']))
        connection.commit()

    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    plan = hr_client.get('/schedules/2026/9').json
    erster = [z for z in plan['assignments'] if z['date'] == '2026-09-01']
    assert any(z['employee_id'] == anna['id'] for z in erster)
