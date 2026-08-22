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


# ---------- constraint_warnings() und add_slot() kommen ohne Schichtart aus (Task 4) ----------
#
# shift_type_id ist in constraint_warnings() und add_slot() nicht nur ein Zeit-Ersatzteil
# (das loest Task 2/assignment_hours() schon), sondern wird an zwei weiteren Stellen als
# echter Fremdschluessel benutzt: die Schichtart-Restriktionspruefung und die
# slot_index-Vergabe beim Anlegen eines Platzes. Beide Stellen gingen bislang von
# "nie NULL" aus. Alle vier Tests fahren komplett ueber die HTTP-Routen, weil
# add_slot() ab dieser Aufgabe shift_type_id: null selbst entgegennimmt.

def test_freier_block_loest_keine_schichtart_warnung_aus(hr_client):
    """Ein Mitarbeiter mit eingeschraenkten Schichtarten darf auf einen Block ohne Vorlage.

    Diskriminierung: derselbe Mitarbeiter bekommt im selben Test auf einer
    NICHT erlaubten Schichtart sehr wohl die Warnung. Ohne diesen Gegenpart
    wuerde der Test auch dann gruen sein, wenn die Pruefung komplett fehlte.
    """
    erlaubt = hr_client.post('/shift-types', json={
        'name': 'Erlaubt', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    verboten = hr_client.post('/shift-types', json={
        'name': 'Verboten', 'start_time': '14:00', 'end_time': '22:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={
        'name': 'Mitarbeiter',
        'allowed_shift_types': [erlaubt['id']],
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Block ohne Vorlage, weit entfernt vom zweiten Datum unten, damit weder
    # die Ruhezeit- noch die "schon an diesem Tag zugeteilt"-Pruefung dazwischenfunkt.
    platz_frei = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
        'start_time': '10:00', 'end_time': '14:00',
    }).json
    # Seit Task 5 schreibt jeder PUT die Zeiten mit - ein Block ohne Vorlage
    # braucht sie deshalb bei jedem Aufruf erneut, sonst haette er nach dem
    # PUT gar keine Zeit mehr, von der er erben koennte.
    antwort_frei = hr_client.put(f'/assignments/{platz_frei["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '10:00', 'end_time': '14:00',
    })
    assert antwort_frei.status_code == 200, antwort_frei.json
    assert antwort_frei.json['warnings'] == []

    platz_verboten = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-08', 'shift_type_id': verboten['id'],
    }).json
    antwort_verboten = hr_client.put(f'/assignments/{platz_verboten["id"]}',
                                      json={'employee_id': mitarbeiter['id']})
    assert antwort_verboten.status_code == 200, antwort_verboten.json
    assert antwort_verboten.json['warnings'] == [
        'Mitarbeiter ist normalerweise auf andere Schichtarten beschränkt']


def test_freier_block_zaehlt_in_die_wochenstunden(hr_client):
    """Er ist Arbeitszeit wie jede andere - der alte innere JOIN haette ihn verschluckt.

    Seit dieser Aufgabe reicht update_assignment() start_time/end_time an
    constraint_warnings() durch (vorher fehlte genau diese Verdrahtung), die
    Wochenstunden-Pruefung sieht die eigene Zeit des freien Blocks deshalb schon
    bei SEINER EIGENEN Zuweisung - er braucht dafuer keine dritte Zuweisung mehr,
    die ihn erst als bereits gespeicherte Nachbarzeile liest (das war der Weg vor
    dieser Aufgabe). Gegentest eingebaut: die erste Zuweisung bleibt absichtlich
    unter dem Wochenziel, solange der freie Block noch nicht zugewiesen ist -
    erst mit ihm kippt die Summe. Ohne diesen Vorher/Nachher-Vergleich koennte
    die Warnung auch aus der Kurzschicht allein stammen.
    """
    kurz = hr_client.post('/shift-types', json={
        'name': 'Kurz', 'start_time': '07:00', 'end_time': '08:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={
        'name': 'Mitarbeiter', 'weekly_hours': 8,
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Erste Kurzschicht (1 Std.) allein - weit unter dem Wochenziel von 8 Std.
    platz_b = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-02', 'shift_type_id': kurz['id'],
    }).json
    antwort_b = hr_client.put(f'/assignments/{platz_b["id"]}',
                               json={'employee_id': mitarbeiter['id']})
    assert antwort_b.status_code == 200, antwort_b.json
    assert antwort_b.json['warnings'] == []

    # Freier Block (9 Std.) an einem anderen Tag derselben Woche - seine eigene
    # Zeit muss mitgeschickt werden (kein Schichtart-Fallback fuer ihn) und
    # zaehlt sofort mit: 1 + 9 = 10 Std., schon ueber dem Ziel von 8.
    platz_a = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
        'start_time': '08:00', 'end_time': '17:00',
    }).json
    antwort_a = hr_client.put(f'/assignments/{platz_a["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '08:00', 'end_time': '17:00',
    })
    assert antwort_a.status_code == 200, antwort_a.json
    assert antwort_a.json['warnings'] == [
        'Mitarbeiter käme damit auf 10.0 Std. in dieser Woche - über dem Ziel von 8 Std./Woche']

    # Zweite Kurzschicht (1 Std.), dritter Tag derselben Woche: die Summe
    # steigt weiter auf 1 + 9 + 1 = 11 Std.
    platz_c = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-03', 'shift_type_id': kurz['id'],
    }).json
    antwort_c = hr_client.put(f'/assignments/{platz_c["id"]}',
                               json={'employee_id': mitarbeiter['id']})
    assert antwort_c.status_code == 200, antwort_c.json
    assert antwort_c.json['warnings'] == [
        'Mitarbeiter käme damit auf 11.0 Std. in dieser Woche - über dem Ziel von 8 Std./Woche']


def test_freier_block_zaehlt_in_die_ruhezeit(hr_client):
    """Ein Block 22:00-06:00 am Vortag muss die Ruhezeitwarnung ausloesen.

    Seit dieser Aufgabe reicht update_assignment() start_time/end_time an
    constraint_warnings() durch, deshalb muss die ERSTE Zuweisung (der
    Nachtblock ohne Vorlage) ihre eigene Zeit im PUT mitschicken - ohne
    Schichtart gibt es sonst nichts, von dem sie erben koennte. Der Nachtblock
    steht zu diesem Zeitpunkt noch allein, deshalb keine Warnung. Die ZWEITE
    Zuweisung (Fruehschicht mit Schichtart) liest den Nachtblock anschliessend
    als bereits gespeicherte Nachbarzeile direkt aus der Datenbank -
    assignment_hours() liest dort seine Spalten unabhaengig davon, ob die
    zweite Zuweisung selbst eigene Zeiten mitschickt.
    """
    fruehschicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '07:00', 'end_time': '15:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # Nachtblock ohne Vorlage, endet ueber Mitternacht am 2026-09-02 um 06:00.
    platz_nacht = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
        'start_time': '22:00', 'end_time': '06:00',
    }).json
    antwort_nacht = hr_client.put(f'/assignments/{platz_nacht["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '22:00', 'end_time': '06:00',
    })
    assert antwort_nacht.status_code == 200, antwort_nacht.json
    assert antwort_nacht.json['warnings'] == []

    # Fruehschicht (07:00-15:00) am naechsten Morgen - nur 1 Std. Ruhezeit seit
    # dem Ende des Nachtblocks um 06:00, statt der geforderten 11 (Standardwert,
    # kein min_rest_hours gesetzt).
    platz_morgen = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-02', 'shift_type_id': fruehschicht['id'],
    }).json
    antwort_morgen = hr_client.put(f'/assignments/{platz_morgen["id"]}',
                                    json={'employee_id': mitarbeiter['id']})
    assert antwort_morgen.status_code == 200, antwort_morgen.json
    assert antwort_morgen.json['warnings'] == [
        'Mitarbeiter hätte dann nur 1.0 Std. Ruhezeit statt der geforderten 11 Std.']


def test_zweiter_freier_block_am_selben_tag_bekommt_den_naechsten_platz(hr_client):
    """add_slot mit shift_type_id NULL: 'WHERE shift_type_id = NULL' trifft nichts,
    der zweite Block bekaeme sonst wieder slot_index 0 und liefe in den
    UNIQUE-Index."""
    # /schedules/generate verlangt mindestens eine Schichtart, auch wenn der
    # Test selbst keine benutzt.
    hr_client.post('/shift-types', json={'name': 'Unbenutzt', 'start_time': '06:00', 'end_time': '14:00'})
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    erster = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
        'start_time': '10:00', 'end_time': '14:00',
    })
    assert erster.status_code == 201, erster.json

    zweiter = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
        'start_time': '14:00', 'end_time': '18:00',
    })
    assert zweiter.status_code == 201, zweiter.json
    assert zweiter.json['id'] != erster.json['id']

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zuweisungen = {a['id']: a for a in antwort.json['assignments']}

    assert zuweisungen[erster.json['id']]['slot_index'] == 0
    assert zuweisungen[zweiter.json['id']]['slot_index'] == 1


# ---------- Zeiten ueber die API setzen (Task 5) ----------
#
# Bis hierher konnte keine der drei Aufrufer-Stellen von constraint_warnings()
# eigene Zeiten durchreichen - Task 2 hatte die Parameter nur angelegt, Task 4
# musste sie deshalb noch per direktem SQL an der Pruefung vorbeischmuggeln.
# Diese Tests gehen ausschliesslich ueber PUT /assignments/<id> bzw.
# POST /schedules/<jahr>/<monat>/slots, weil genau das die Verdrahtung ist,
# die diese Aufgabe herstellt.

def test_zeiten_setzen_speichert_und_warnt_bei_bedarf(hr_client):
    """Die Zuweisung wird gespeichert (200) und die Warnung bezieht sich auf die NEUE Zeit.

    Aufbau: Anna hat ein Fenster 08:00-14:00 und steht auf der Frueh-schicht
    06:00-14:00, also bereits ausserhalb. Wird die Zuweisung auf 09:00-13:00
    gesetzt, muss die Warnung VERSCHWINDEN - das beweist, dass die Pruefung mit
    der neuen Zeit rechnet und nicht mit der der Schichtart.
    """
    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '08:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # 2026-09-01 ist ein Dienstag (Wochentag 1).
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    # Zugewiesen mit der Schichtart-Zeit (06:00-14:00) - die liegt ausserhalb
    # von Annas Fenster, also eine Warnung.
    vorher = hr_client.put(f'/assignments/{platz["id"]}', json={'employee_id': anna['id']})
    assert vorher.status_code == 200, vorher.json
    assert vorher.json['warnings'] == ['Anna arbeitet dienstags normalerweise nur 08:00–14:00.']

    # Dieselbe Zuweisung, jetzt mit eigener Zeit 09:00-13:00 - die passt
    # vollstaendig ins Fenster.
    nachher = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': anna['id'], 'start_time': '09:00', 'end_time': '13:00',
    })
    assert nachher.status_code == 200, nachher.json
    assert nachher.json['warnings'] == []

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zeile = {a['id']: a for a in antwort.json['assignments']}[platz['id']]
    assert (zeile['start_time'], zeile['end_time']) == ('09:00', '13:00')
    assert zeile['assignment_time_set'] is True


def test_halb_gefuelltes_zeitpaar_ist_400(hr_client):
    """start_time ohne end_time - kein stilles Halb-Interpretieren."""
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    erwartete_meldung = 'Start- und Endzeit müssen zusammen gesetzt oder zusammen leer sein.'

    nur_start = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '09:00',
    })
    assert nur_start.status_code == 400, nur_start.json
    assert nur_start.json['message'] == erwartete_meldung

    # Gegenrichtung: nur end_time, kein start_time - beide Haelften des Paars
    # muessen einzeln geprueft werden, sonst koennte eine Richtung durchrutschen.
    nur_ende = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'end_time': '13:00',
    })
    assert nur_ende.status_code == 400, nur_ende.json
    assert nur_ende.json['message'] == erwartete_meldung


def test_zeiten_zuruecksetzen_faellt_auf_die_schichtart_zurueck(hr_client):
    """Beide Felder explizit null -> die Zuweisung erbt wieder."""
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    gesetzt = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '10:00', 'end_time': '16:00',
    })
    assert gesetzt.status_code == 200, gesetzt.json

    # Zwischenstand pruefen, damit "zurueckgesetzt" unten wirklich einen Wechsel
    # zeigt und nicht nur zwei Male dieselbe (nie individuell gesetzte) Zeit liest.
    zwischenstand = hr_client.get('/schedules/2026/9')
    zwischenzeile = {a['id']: a for a in zwischenstand.json['assignments']}[platz['id']]
    assert (zwischenzeile['start_time'], zwischenzeile['end_time']) == ('10:00', '16:00')
    assert zwischenzeile['assignment_time_set'] is True

    zurueckgesetzt = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': None, 'end_time': None,
    })
    assert zurueckgesetzt.status_code == 200, zurueckgesetzt.json

    antwort = hr_client.get('/schedules/2026/9')
    assert antwort.status_code == 200, antwort.json
    zeile = {a['id']: a for a in antwort.json['assignments']}[platz['id']]
    assert (zeile['start_time'], zeile['end_time']) == ('06:00', '14:00')
    assert zeile['assignment_time_set'] is False


def test_block_ohne_vorlage_ohne_zeiten_ist_400(hr_client):
    """Er hat nichts, von dem er erben koennte."""
    erwartete_meldung = (
        'Ein Block ohne Schichtart braucht eigene Zeiten — er hat keine '
        'Vorlage, von der er sie erben könnte.')

    # /schedules/generate verlangt mindestens eine Schichtart, auch wenn der
    # Test selbst keine benutzt.
    hr_client.post('/shift-types', json={'name': 'Unbenutzt', 'start_time': '06:00', 'end_time': '14:00'})
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # add_slot() lehnt ihn schon beim Anlegen ab.
    kein_platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None,
    })
    assert kein_platz.status_code == 400, kein_platz.json
    assert kein_platz.json['message'] == erwartete_meldung

    # update_assignment() lehnt ihn genauso ab, wenn ein bereits bestehender
    # vorlagenloser Block per PUT seine Zeiten verlieren wuerde.
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': None, 'start_time': '10:00', 'end_time': '14:00',
    }).json
    kein_update = hr_client.put(f'/assignments/{platz["id"]}', json={'employee_id': mitarbeiter['id']})
    assert kein_update.status_code == 400, kein_update.json
    assert kein_update.json['message'] == erwartete_meldung


def test_ungueltiges_zeitformat_ist_400(hr_client):
    """'25:00' und 'abends' - beide mit der uebersetzten Meldung, nicht nur mit dem Status."""
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    ungueltige_stunde = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '25:00', 'end_time': '14:00',
    })
    assert ungueltige_stunde.status_code == 400, ungueltige_stunde.json
    assert ungueltige_stunde.json['message'] == 'Ungültige Uhrzeit "25:00". Erwartet wird HH:MM.'

    kein_zeitformat = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': 'abends', 'end_time': '14:00',
    })
    assert kein_zeitformat.status_code == 400, kein_zeitformat.json
    assert kein_zeitformat.json['message'] == 'Ungültige Uhrzeit "abends". Erwartet wird HH:MM.'


def test_gleiche_start_und_endzeit_ist_400(hr_client):
    """start_time == end_time waere sonst eine stille 24-Stunden-Schicht.

    shift_duration_minutes() behandelt end <= start als Schicht ueber
    Mitternacht (1440 Minuten) statt als leere Spanne - vor dieser Aufgabe war
    dieser Pfad ueber die API nicht erreichbar, weil Zuweisungen gar keine
    eigenen Zeiten setzen konnten. Geprueft wird die Meldung, nicht nur der
    Status.
    """
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    mitarbeiter = hr_client.post('/employees', json={'name': 'Mitarbeiter'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    gleiche_zeit = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': mitarbeiter['id'], 'start_time': '09:00', 'end_time': '09:00',
    })
    assert gleiche_zeit.status_code == 400, gleiche_zeit.json
    assert gleiche_zeit.json['message'] == 'Start- und Endzeit einer Zuweisung dürfen nicht gleich sein.'


# ---------- Regressionsschutz: swap_assignments() und replacement_suggestions() ----------
#
# Beide reichen seit dieser Aufgabe die Zeiten IHRER jeweiligen Zuweisung an
# constraint_warnings() durch (app.py). Ohne die beiden Tests unten koennte
# jemand die start_time=/end_time=-Argumente an einer der beiden Stellen
# wieder herausstreichen, ohne dass die Suite das bemerkt.

def test_tausch_reicht_die_zeiten_des_platzes_durch(hr_client):
    """Nach dem Tausch bezieht sich die Warnung auf die Zeiten des PLATZES, nicht der Person.

    Aufbau: Anna hat ein Fenster 06:00-14:00, das sich mit der Schichtart-Zeit
    deckt. Platz A traegt eine individuelle Zeit 10:00-16:00, die aus dem
    Fenster faellt; Platz B hat keine eigene Zeit und laeuft auf der
    Schichtart-Zeit 06:00-14:00, die ins Fenster passt. Vor dem Tausch steht
    Ben auf A, Anna auf B - keine Warnung. Nach dem Tausch steht Anna auf A:
    wanderten die Zeiten mit der Person statt mit dem Platz, saehe Anna
    weiterhin die fensterkonforme Zeit und bliebe warnungsfrei. Bleiben sie
    dagegen am Platz (wie spezifiziert), sieht sie 10:00-16:00 und die Warnung
    erscheint. Der abschliessende GET bestaetigt zusaetzlich, dass die
    gespeicherten Zeiten selbst am Platz haengen, nicht an der Person.
    """
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    ben = hr_client.post('/employees', json={'name': 'Ben'}).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # 2026-09-01 ist ein Dienstag (Wochentag 1).
    platz_a = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json
    platz_b = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    # Ben auf A, mit individueller Zeit ausserhalb von Annas Fenster.
    zu_a = hr_client.put(f'/assignments/{platz_a["id"]}', json={
        'employee_id': ben['id'], 'start_time': '10:00', 'end_time': '16:00',
    })
    assert zu_a.status_code == 200, zu_a.json
    assert zu_a.json['warnings'] == []

    # Anna auf B, ohne eigene Zeit - laeuft auf der Schichtart-Zeit, die genau
    # in ihr Fenster passt.
    zu_b = hr_client.put(f'/assignments/{platz_b["id"]}', json={'employee_id': anna['id']})
    assert zu_b.status_code == 200, zu_b.json
    assert zu_b.json['warnings'] == []

    tausch = hr_client.post('/assignments/swap', json={
        'assignment_id_a': platz_a['id'], 'assignment_id_b': platz_b['id'],
    })
    assert tausch.status_code == 200, tausch.json
    assert tausch.json['warnings'] == [
        'Anna arbeitet dienstags normalerweise nur 06:00–14:00.']

    # Die Zeiten selbst bleiben am Platz, nicht an der Person.
    antwort = hr_client.get('/schedules/2026/9')
    zuweisungen = {a['id']: a for a in antwort.json['assignments']}
    assert (zuweisungen[platz_a['id']]['start_time'], zuweisungen[platz_a['id']]['end_time']) == ('10:00', '16:00')
    assert zuweisungen[platz_a['id']]['employee_id'] == anna['id']
    assert (zuweisungen[platz_b['id']]['start_time'], zuweisungen[platz_b['id']]['end_time']) == ('06:00', '14:00')
    assert zuweisungen[platz_b['id']]['employee_id'] == ben['id']


def test_ersatzsuche_reicht_die_eigene_zeit_der_zuweisung_durch(hr_client):
    """Ein Kandidat, der nur wegen der individuellen Zeit passt oder nicht passt.

    Der freie Platz hat eine Schichtart (Fruehschicht 06:00-14:00), aber eine
    individuelle Zeit 10:00-16:00. Ellas Fenster deckt genau die
    Schichtart-Zeit ab (06:00-14:00), nicht aber die individuelle Zeit - sie
    endet zwei Stunden zu frueh. Faraahs Fenster deckt dagegen genau die
    individuelle Zeit ab. Wuerde replacement_suggestions() die Schichtart-Zeit
    statt der individuellen Zeit an constraint_warnings() reichen, kaeme genau
    das umgekehrte Ergebnis heraus: Ella eignungsfaehig, Faraah nicht.
    """
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    ella = hr_client.post('/employees', json={
        'name': 'Ella',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    faraah = hr_client.post('/employees', json={
        'name': 'Faraah',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '10:00', 'end_time': '16:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # 2026-09-01 ist ein Dienstag (Wochentag 1). Individuelle Zeit weicht
    # bewusst von der Schichtart ab.
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
        'start_time': '10:00', 'end_time': '16:00',
    }).json

    antwort = hr_client.get(f'/assignments/{platz["id"]}/replacement-suggestions')
    assert antwort.status_code == 200, antwort.json
    kandidaten_ids = {c['employee_id'] for c in antwort.json}
    assert ella['id'] not in kandidaten_ids
    assert faraah['id'] in kandidaten_ids


# ---------- Regressionsschutz: update_assignment() reicht eigene Zeiten an die
# ---------- Fensterpruefung durch (Abschluss-Review, Befund 1) ----------
#
# Die beiden Tests oben unter "constraint_warnings() reicht start_time/end_time
# tatsaechlich durch" rufen constraint_warnings() direkt auf, nicht ueber die
# HTTP-Route (das war zum Zeitpunkt jener Tests noch nicht moeglich - siehe
# Kommentar am Dateianfang). test_zeiten_setzen_speichert_und_warnt_bei_bedarf
# geht zwar ueber PUT /assignments/<id>, zeigt dort aber nur, dass sich die
# Warnung AENDERT, wenn die eigene Zeit wechselt - nicht gezielt, dass sie
# erscheint, wenn die eigene Zeit das Fenster verletzt, waehrend die
# Schichtart-Zeit es nicht taete. Genau diese Kombination - PUT mit eigener
# Zeit UND einer dadurch verletzten Fenster-Verfuegbarkeit - war bislang an
# keiner Stelle ueber die tatsaechlich benutzte Route geprueft, obwohl PUT
# /assignments/<id> der meistbenutzte Schreibpfad ist (jede manuelle
# Umbesetzung laeuft darueber). Tausch und Ersatzsuche sind mit den beiden
# Tests direkt oberhalb bereits so abgesichert.

def test_put_reicht_die_eigene_zeit_der_zuweisung_an_die_fensterpruefung_durch(hr_client):
    """PUT /assignments/<id> mit eigener Zeit, die das Fenster verletzt - und
    der Gegenfall, in dem sie hineinpasst.

    Aufbau: Anna arbeitet dienstags laut Fenster nur 06:00-14:00 - genau die
    Zeit der Schichtart. Die individuelle Zeit 10:00-16:00 verletzt dieses
    Fenster, die Schichtart-Zeit selbst wuerde es nicht. Wuerde
    update_assignment() beim Aufruf von constraint_warnings() faelschlich die
    Schichtart-Zeit statt der individuellen durchreichen, saehe die
    Fensterpruefung 06:00-14:00 (passt) statt 10:00-16:00 (passt nicht), und
    die Warnung bliebe aus - der Test wuerde umfallen. Der Gegenfall (dieselbe
    Zuweisung, individuelle Zeit diesmal innerhalb des Fensters) zeigt, dass
    keine Warnung entsteht, wenn keine entstehen soll; ein Aufbau, in dem
    beide Zeiten das Fenster verletzen wuerden, koennte die beiden Faelle
    nicht unterscheiden.
    """
    schicht = hr_client.post('/shift-types', json={
        'name': 'Fruehschicht', 'start_time': '06:00', 'end_time': '14:00',
    }).json
    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '06:00', 'end_time': '14:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    plan = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9}).json
    assert 'id' in plan, plan

    # 2026-09-01 ist ein Dienstag (Wochentag 1).
    platz = hr_client.post('/schedules/2026/9/slots', json={
        'date': '2026-09-01', 'shift_type_id': schicht['id'],
    }).json

    verletzt_das_fenster = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': anna['id'], 'start_time': '10:00', 'end_time': '16:00',
    })
    assert verletzt_das_fenster.status_code == 200, verletzt_das_fenster.json
    assert verletzt_das_fenster.json['warnings'] == [
        'Anna arbeitet dienstags normalerweise nur 06:00–14:00.']

    # Gegenfall: dieselbe Zuweisung, dieselbe Person, individuelle Zeit
    # diesmal innerhalb des Fensters - keine Warnung.
    passt_ins_fenster = hr_client.put(f'/assignments/{platz["id"]}', json={
        'employee_id': anna['id'], 'start_time': '06:00', 'end_time': '14:00',
    })
    assert passt_ins_fenster.status_code == 200, passt_ins_fenster.json
    assert passt_ins_fenster.json['warnings'] == []
