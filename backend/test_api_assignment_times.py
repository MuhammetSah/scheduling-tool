"""assignment_hours(): die Zeitaufloesung einer Zuweisung an einer Stelle.

Deckt Task 2 aus dem Etappenplan ab. Reiner Funktionstest der Vorrangregel
(eigene Zeiten > Datums-Override > Schichtart-Vorlage) - keine HTTP-Assertions,
weil die API diese Funktion in dieser Aufgabe noch gar nicht benutzt
(constraint_warnings() bekommt sie erst hier, aber mit start_time=end_time=None
von allen drei Aufrufern, also unveraendertes Verhalten). Task 3 bis 5 bauen
HTTP-Tests obendrauf.
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
