"""assignment_hours(): die Zeitaufloesung einer Zuweisung an einer Stelle.

Deckt Task 2 aus dem Etappenplan ab. Ueberwiegend Funktionstests der Vorrangregel
(eigene Zeiten > Datums-Override > Schichtart-Vorlage), direkt an assignment_hours()
gefuehrt - keine HTTP-Assertions, weil kein Aufrufer von constraint_warnings() in
dieser Aufgabe schon eigene Zeiten durchreicht (das kommt erst mit Task 5). Die
letzten beiden Tests rufen deshalb ebenfalls direkt in constraint_warnings() hinein,
statt ueber die HTTP-Route: sie sichern, dass die drei Stellen, die start_time/
end_time an assignment_hours() weiterreichen, das auch tatsaechlich tun - etwas,
das die Bestandssuite nicht pruefen kann, weil dort start_time in jeder Zeile NULL
ist. Task 3 bis 5 bauen echte HTTP-Tests obendrauf.
"""


def test_zuweisungszeiten_schlagen_den_datums_override(hr_client):
    """Die Vorrangregel, direkt an assignment_hours geprueft.

    Aufbau bewusst dreistufig, damit jede Stufe einzeln widerlegbar ist:
    Schichtart 06:00-14:00, Datums-Override 07:00-15:00, Zuweisungszeit
    10:00-16:00. Erwartet wird die Zuweisungszeit - waere die Reihenfolge
    falsch, kaeme eine der beiden anderen heraus, und beide sind verschieden.
    """
    from app import assignment_hours, get_db

    schicht = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '06:00', 'end_time': '14:00',
    }).json

    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Der Datums-Override kommt ueber dieselbe Route, die die Anwendung auch
    # benutzt - nicht per direktem SQL.
    override = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-17', 'shift_type_id': schicht['id'],
        'start_time': '07:00', 'end_time': '15:00',
    })
    assert override.status_code == 200, override.json

    with hr_client.application.app_context():
        cursor = get_db().cursor()
        zeile = {'schedule_id': plan['id'], 'date': '2026-09-17', 'shift_type_id': schicht['id'],
                 'start_time': '10:00', 'end_time': '16:00'}
        assert assignment_hours(cursor, zeile) == ('10:00', '16:00')

        zeile_ohne_eigene = dict(zeile, start_time=None, end_time=None)
        assert assignment_hours(cursor, zeile_ohne_eigene) == ('07:00', '15:00')


def test_block_ohne_vorlage_nutzt_seine_eigenen_zeiten(client):
    """Fuer shift_type_id IS NULL gibt es keine Erbstufe - die eigenen Zeiten sind alles."""
    from app import assignment_hours, get_db

    with client.application.app_context():
        cursor = get_db().cursor()
        zeile = {'schedule_id': 1, 'date': '2026-03-17', 'shift_type_id': None,
                 'start_time': '10:00', 'end_time': '16:00'}
        assert assignment_hours(cursor, zeile) == ('10:00', '16:00')


def test_block_ohne_vorlage_und_ohne_zeiten_liefert_keine_zeit(client):
    """(None, None) statt einer Ausnahme: der Aufrufer entscheidet, was das bedeutet.

    Diese Kombination kann die API nicht erzeugen (Task 5 lehnt sie ab), aber
    assignment_hours() darf an einer Altzeile nicht mit AttributeError sterben.
    """
    from app import assignment_hours, get_db

    with client.application.app_context():
        cursor = get_db().cursor()
        zeile = {'schedule_id': 1, 'date': '2026-03-17', 'shift_type_id': None,
                 'start_time': None, 'end_time': None}
        assert assignment_hours(cursor, zeile) == (None, None)


# ---------- constraint_warnings() reicht start_time/end_time tatsaechlich durch ----------
#
# Regressionsschutz fuer die drei Dict-Literale in constraint_warnings(), die
# start_time/end_time an assignment_hours() weiterreichen. Die Bestandssuite kann
# das nicht pruefen: dort ist start_time in jeder Zeile NULL, Stufe 1 der
# Vorrangregel feuert nie - fiele eines der drei Literale versehentlich auf None
# zurueck statt den Parameter zu benutzen, bliebe die gesamte Suite gruen, bis
# Task 5 die Aufrufer umstellt. 2026-09-01 ist ein Dienstag (Wochentag 1).

def test_constraint_warnings_warnt_wenn_die_vorgeschlagene_zeit_das_fenster_verlaesst(hr_client):
    """Anna darf laut Fenster dienstags nur 06:00-14:00 arbeiten. Die vorgeschlagene
    Zuweisungszeit 10:00-16:00 passt nicht hinein. Wuerde constraint_warnings()
    start_time/end_time nicht an assignment_hours() weiterreichen, saehe die
    Fensterpruefung ueberhaupt keine Zeit und wuerde ueberspringen - die Warnung
    bliebe aus. Erst zusammen mit dem Gegentest unten ist das diskriminierend:
    eine Warnung allein koennte auch aus einer anderen Pruefung stammen."""
    from app import constraint_warnings, get_db
    from flask import g

    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json

    with hr_client.application.app_context():
        g.lang = 'de'
        cursor = get_db().cursor()
        warnungen = constraint_warnings(
            cursor, anna['id'], '2026-09-01', schicht['id'], plan['id'],
            start_time='10:00', end_time='16:00')

    assert warnungen == ['Anna arbeitet dienstags normalerweise nur 06:00–14:00.']


def test_constraint_warnings_warnt_nicht_wenn_die_vorgeschlagene_zeit_ins_fenster_passt(hr_client):
    """Gegentest zum vorigen: dieselbe Zuweisung, aber mit einer vorgeschlagenen
    Zeit, die vollstaendig ins Fenster passt - keine Warnung. Nur das Paar zeigt,
    dass start_time/end_time tatsaechlich durchwirken, statt dass der vorige Test
    zufaellig aus einer anderen Pruefung heraus warnte."""
    from app import constraint_warnings, get_db
    from flask import g

    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json

    with hr_client.application.app_context():
        g.lang = 'de'
        cursor = get_db().cursor()
        warnungen = constraint_warnings(
            cursor, anna['id'], '2026-09-01', schicht['id'], plan['id'],
            start_time='06:00', end_time='12:00')

    assert warnungen == []


# ---------- fetch_schedule() liefert die tatsaechlichen Zeiten (Task 3) ----------
#
# Anders als oben: hier geht es um die HTTP-Antwort von GET /schedules/<jahr>/<monat>,
# nicht um assignment_hours() direkt - fetch_schedule() loest die drei Vorrangstufen
# in der eigenen Schleife auf, weil es die Overrides vorab in einen Dict laedt statt
# pro Zeile nachzufragen (siehe Kommentar in app.py). Eigene Zeiten auf einer
# Zuweisung kann die API noch nicht setzen (kommt erst mit Task 4/5), deshalb setzen
# die Tests unten sa.start_time/sa.end_time per direktem SQL - eine bewusste
# Zwischenloesung, keine Bequemlichkeit.

def test_plan_zeigt_die_individuelle_zeit_statt_der_schichtart(hr_client):
    """Ben steht mit seinen eigenen Zeiten im Plan, seine Kollegin mit denen der Schichtart."""
    from app import get_db

    ben = hr_client.post('/employees', json={'name': 'Ben'}).json
    kollegin = hr_client.post('/employees', json={'name': 'Kollegin'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Zwei Plaetze fuer dieselbe Schichtart am selben Datum, ueber dieselben
    # Routen, die die Anwendung auch benutzt - nicht per direktem SQL.
    platz_kollegin = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    platz_ben = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    assert hr_client.put(f'/assignments/{platz_kollegin["id"]}',
                          json={'employee_id': kollegin['id']}).status_code == 200
    assert hr_client.put(f'/assignments/{platz_ben["id"]}',
                          json={'employee_id': ben['id']}).status_code == 200

    # Bens eigene Zeit weicht bewusst von der Schichtart ab (06:00-14:00),
    # damit die beiden Faelle nicht zufaellig gleich aussehen.
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE shift_assignments SET start_time = ?, end_time = ? WHERE id = ?',
            ('10:00', '16:00', platz_ben['id']),
        )
        connection.commit()

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zuweisungen = {a['id']: a for a in antwort.json['assignments']}

    ben_zeile = zuweisungen[platz_ben['id']]
    assert (ben_zeile['start_time'], ben_zeile['end_time']) == ('10:00', '16:00')
    assert ben_zeile['assignment_time_set'] is True
    assert ben_zeile['time_overridden'] is False
    assert (ben_zeile['default_start_time'], ben_zeile['default_end_time']) == ('06:00', '14:00')

    kollegin_zeile = zuweisungen[platz_kollegin['id']]
    assert (kollegin_zeile['start_time'], kollegin_zeile['end_time']) == ('06:00', '14:00')
    assert kollegin_zeile['assignment_time_set'] is False
    assert kollegin_zeile['time_overridden'] is False


def test_block_ohne_vorlage_erscheint_im_plan(hr_client):
    """Vor dieser Aenderung fiel er durch den inneren JOIN heraus - lautlos.

    Aufbau: ein regulaerer Platz und ein freier Block am selben Datum. Geprueft
    wird, dass BEIDE zurueckkommen; ohne den LEFT JOIN kaeme nur der regulaere,
    und ein Test, der nur den freien Block zaehlt, koennte das nicht von
    "gar nichts geladen" unterscheiden.
    """
    from app import get_db

    kollegin = hr_client.post('/employees', json={'name': 'Kollegin'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    platz_regulaer = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    assert hr_client.put(f'/assignments/{platz_regulaer["id"]}',
                          json={'employee_id': kollegin['id']}).status_code == 200

    # add_slot kennt shift_type_id IS NULL noch nicht (kommt erst mit Task 4/5)
    # - der freie Block wird deshalb per direktem SQL angelegt, bewusst als
    # Zwischenloesung fuer diesen Test.
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO shift_assignments '
            '(schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited, start_time, end_time) '
            'VALUES (?, ?, NULL, 0, NULL, 1, ?, ?)',
            (plan['id'], '2026-09-01', '20:00', '23:00'),
        )
        freier_block_id = cursor.lastrowid
        connection.commit()

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    ids = {a['id'] for a in antwort.json['assignments']}

    assert platz_regulaer['id'] in ids
    assert freier_block_id in ids


def test_freier_block_hat_keinen_schichtartnamen_aber_eine_zeit(hr_client):
    """shift_type_name ist None, start_time/end_time sind gefuellt."""
    from app import get_db

    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO shift_assignments '
            '(schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited, start_time, end_time) '
            'VALUES (?, ?, NULL, 0, NULL, 1, ?, ?)',
            (plan['id'], '2026-09-02', '20:00', '23:00'),
        )
        freier_block_id = cursor.lastrowid
        connection.commit()

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zuweisungen = {a['id']: a for a in antwort.json['assignments']}

    block = zuweisungen[freier_block_id]
    assert block['shift_type_name'] is None
    assert (block['start_time'], block['end_time']) == ('20:00', '23:00')


def test_plan_zeigt_den_datums_override_ueber_http(hr_client):
    """Stufe 2 im HTTP-Pfad von fetch_schedule(): ohne eigene Zeit gewinnt der
    Datums-Override gegen die Schichtart-Vorlage - geprueft gegen die Antwort
    von GET /schedules/..., nicht gegen assignment_hours() direkt. Kein Test
    im Projekt ruft diese Route bisher nach einem gesetzten Override auf.

    Vier Assertions zusammen sind der Punkt: sie unterscheiden Stufe 2 von
    Stufe 3 UND halten fest, dass assignment_time_set/time_overridden nicht
    vertauscht wurden. Eine Assertion allein auf start_time koennte auch dann
    gruen sein, wenn die beiden Flags vertauscht waeren.
    """
    kollegin = hr_client.post('/employees', json={'name': 'Kollegin'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    assert hr_client.put(f'/assignments/{platz["id"]}',
                          json={'employee_id': kollegin['id']}).status_code == 200

    # Der Datums-Override kommt ueber dieselbe Route, die die Anwendung auch
    # benutzt - nicht per direktem SQL.
    override = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
        'start_time': '07:00', 'end_time': '15:00',
    })
    assert override.status_code == 200, override.json

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zeile = {a['id']: a for a in antwort.json['assignments']}[platz['id']]

    assert (zeile['start_time'], zeile['end_time']) == ('07:00', '15:00')
    assert zeile['time_overridden'] is True
    assert zeile['assignment_time_set'] is False
    assert (zeile['default_start_time'], zeile['default_end_time']) == ('06:00', '14:00')


def test_eigene_zeit_schlaegt_den_datums_override_im_plan(hr_client):
    """Stufe 1 gegen Stufe 2 im selben HTTP-Pfad: Bens eigene Zeit gewinnt auch
    dann, wenn fuer Datum und Schichtart zusaetzlich ein Override existiert.

    Baut auf demselben Aufbau wie oben auf, mit einem zweiten Platz fuer Ben:
    ohne diesen Test koennte fetch_schedule() faelschlich zuerst den Override
    pruefen und nur zufaellig richtig aussehen, weil im Test oben keine eigene
    Zeit gesetzt ist - dieser hier widerlegt genau diese Verwechslung, indem
    beide Staerken gleichzeitig auf demselben Datum stehen.
    """
    from app import get_db

    ben = hr_client.post('/employees', json={'name': 'Ben'}).json
    kollegin = hr_client.post('/employees', json={'name': 'Kollegin'}).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    platz_kollegin = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    platz_ben = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    assert hr_client.put(f'/assignments/{platz_kollegin["id"]}',
                          json={'employee_id': kollegin['id']}).status_code == 200
    assert hr_client.put(f'/assignments/{platz_ben["id"]}',
                          json={'employee_id': ben['id']}).status_code == 200

    override = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
        'start_time': '07:00', 'end_time': '15:00',
    })
    assert override.status_code == 200, override.json

    # Bens eigene Zeit weicht bewusst sowohl vom Override als auch von der
    # Schichtart ab, damit keine der drei Stufen zufaellig gleich aussieht.
    # Direktes SQL, weil die API einer Zuweisung noch keine eigenen Zeiten
    # geben kann (kommt erst mit Task 4/5) - dieselbe Zwischenloesung wie in
    # den Tests oben.
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE shift_assignments SET start_time = ?, end_time = ? WHERE id = ?',
            ('10:00', '16:00', platz_ben['id']),
        )
        connection.commit()

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zuweisungen = {a['id']: a for a in antwort.json['assignments']}

    ben_zeile = zuweisungen[platz_ben['id']]
    assert (ben_zeile['start_time'], ben_zeile['end_time']) == ('10:00', '16:00')
    assert ben_zeile['assignment_time_set'] is True
    assert ben_zeile['time_overridden'] is True

    kollegin_zeile = zuweisungen[platz_kollegin['id']]
    assert (kollegin_zeile['start_time'], kollegin_zeile['end_time']) == ('07:00', '15:00')
    assert kollegin_zeile['assignment_time_set'] is False
    assert kollegin_zeile['time_overridden'] is True
