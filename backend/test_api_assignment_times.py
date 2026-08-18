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
