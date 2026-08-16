"""Arbeitszeitfenster ueber die API: lesen, schreiben, End-to-End im Planer.

Deckt Task 3 aus dem Etappenplan ab. Reine Serialisierungs-/Validierungstests
gegen die HTTP-Schicht, plus ein End-to-End-Test, der beweist, dass die drei
Teilaufgaben der Etappe tatsaechlich zusammenspielen (Schema, Planer,
API-Anbindung).
"""
from datetime import date


def test_anlegen_ohne_neue_felder_ist_bestandsverhalten(hr_client):
    antwort = hr_client.post('/employees', json={'name': 'Anna'})

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['availability_mode'] == 'anytime'
    assert antwort.json['availability'] == []


def test_anlegen_mit_fenstern_kommt_sortiert_zurueck(hr_client):
    antwort = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 2, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
            {'weekday': 0, 'start_time': '14:00', 'end_time': '18:00', 'valid_from': None, 'valid_until': None},
            {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
        ],
    })

    assert antwort.status_code == 201, antwort.json
    assert antwort.json['availability_mode'] == 'windows'
    fenster = antwort.json['availability']
    # Sortiert nach Wochentag, dann Startzeit - nicht nach Einfuegereihenfolge.
    assert [(f['weekday'], f['start_time']) for f in fenster] == [
        (0, '08:00'), (0, '14:00'), (2, '08:00'),
    ]


def test_get_employee_liefert_dieselben_fenster_wie_das_anlegen(hr_client):
    angelegt = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json

    antwort = hr_client.get(f'/employees/{angelegt["id"]}')

    assert antwort.status_code == 200
    assert antwort.json['availability'] == angelegt['availability']


def test_put_ersetzt_die_fensterliste_vollstaendig(hr_client):
    angelegt = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
            {'weekday': 1, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json

    antwort = hr_client.put(f'/employees/{angelegt["id"]}', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 3, 'start_time': '09:00', 'end_time': '10:00', 'valid_from': None, 'valid_until': None},
        ],
    })

    assert antwort.status_code == 200, antwort.json
    assert [(f['weekday'], f['start_time'], f['end_time']) for f in antwort.json['availability']] == [
        (3, '09:00', '10:00'),
    ]


def test_put_ohne_availability_leert_die_fensterliste(hr_client):
    """Weggelassen wird wie weggeloescht behandelt - genau wie bei den uebrigen
    Constraint-Listen (unavailable_weekdays, unavailable_dates,
    allowed_shift_types); replace_employee_constraints() macht dafuer keinen
    Unterschied zwischen den Feldern."""
    angelegt = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json

    antwort = hr_client.put(f'/employees/{angelegt["id"]}', json={'name': 'Anna', 'availability_mode': 'windows'})

    assert antwort.status_code == 200, antwort.json
    assert antwort.json['availability'] == []


def test_ungueltiger_modus_ist_400_mit_uebersetzter_meldung(hr_client):
    antwort = hr_client.post('/employees', json={'name': 'Anna', 'availability_mode': 'manchmal'})

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Unbekannter Verfügbarkeitsmodus. Erlaubt sind "anytime" und "windows".'

    antwort_en = hr_client.post('/employees', json={'name': 'Anna', 'availability_mode': 'manchmal'},
                                 headers={'X-Lang': 'en'})
    assert antwort_en.json['message'] == 'Unknown availability mode. Allowed values are "anytime" and "windows".'


def test_wochentag_ausserhalb_0_bis_6_ist_400(hr_client):
    antwort = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [{'weekday': 7, 'start_time': '08:00', 'end_time': '12:00'}],
    })

    assert antwort.status_code == 400


def test_ungueltige_uhrzeiten_sind_400(hr_client):
    for ungueltige_zeit in ('25:00', '8:00', 'abc'):
        antwort = hr_client.post('/employees', json={
            'name': 'Anna',
            'availability_mode': 'windows',
            'availability': [{'weekday': 0, 'start_time': ungueltige_zeit, 'end_time': '12:00'}],
        })
        assert antwort.status_code == 400, (ungueltige_zeit, antwort.json)

        antwort = hr_client.post('/employees', json={
            'name': 'Anna',
            'availability_mode': 'windows',
            'availability': [{'weekday': 0, 'start_time': '08:00', 'end_time': ungueltige_zeit}],
        })
        assert antwort.status_code == 400, (ungueltige_zeit, antwort.json)


def test_valid_until_vor_valid_from_ist_400(hr_client):
    antwort = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [{
            'weekday': 0, 'start_time': '08:00', 'end_time': '12:00',
            'valid_from': '2026-09-01', 'valid_until': '2026-08-01',
        }],
    })

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Das Gültigkeitsende darf nicht vor dem Gültigkeitsbeginn liegen.'


def test_start_gleich_ende_ist_400(hr_client):
    antwort = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [{'weekday': 0, 'start_time': '22:00', 'end_time': '22:00'}],
    })

    assert antwort.status_code == 400
    assert antwort.json['message'] == 'Start- und Endzeit eines Fensters dürfen nicht gleich sein.'


def test_nicht_hr_konto_bekommt_403(hr_client):
    employee = hr_client.post('/employees', json={'name': 'Anna', 'email': 'anna@example.com'}).json
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': employee['id'],
    }).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    antwort = hr_client.put(f'/employees/{employee["id"]}', json={
        'name': 'Anna', 'availability_mode': 'windows',
        'availability': [{'weekday': 0, 'start_time': '08:00', 'end_time': '12:00'}],
    })

    assert antwort.status_code == 403


def test_ungueltiges_anlegen_speichert_keine_fenster_teilweise(hr_client):
    """Der zweite Eintrag ist ungueltig - es darf danach ueberhaupt keine
    Zeile in der Datenbank stehen, nicht nur die des ersten Eintrags fehlen."""
    antwort = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00'},
            {'weekday': 9, 'start_time': '08:00', 'end_time': '12:00'},
        ],
    })

    assert antwort.status_code == 400
    # Da das Anlegen insgesamt fehlgeschlagen ist, gibt es den Mitarbeiter gar
    # nicht - ueber die Liste laesst sich also pruefen, dass kein Datensatz
    # (auch kein Mitarbeiter ohne Fenster) uebrig geblieben ist.
    assert hr_client.get('/employees').json == []


# ---------- End-to-End: Schema -> Planer -> API greifen ineinander ----------

def test_planer_haelt_sich_end_to_end_an_die_ueber_die_api_gesetzten_fenster(hr_client):
    """Das ist der erste Test der Etappe, der beweist, dass alle drei Teilaufgaben
    tatsaechlich zusammenspielen: ein per API angelegtes Fenster muss den
    generierten Plan beeinflussen, nicht nur in serialize_employee() sichtbar sein.

    Anna darf laut ihrem Fenster nur dienstags 08:00-16:00 arbeiten. Bert hat
    keine Einschraenkung. Die Schichtart verlangt jeden Tag der Woche eine
    Besetzung mit genau diesen Stunden. Wuerde load_employees_for_scheduling()
    die Felder nicht mitliefern (Bestandszustand vor dieser Etappe), waere Anna
    an jedem Wochentag einsetzbar - dieser Test wuerde dann fehlschlagen, sobald
    sie an einem Nicht-Dienstag auftaucht.
    """
    anna = hr_client.post('/employees', json={
        'name': 'Anna',
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 1, 'start_time': '08:00', 'end_time': '16:00', 'valid_from': None, 'valid_until': None},
        ],
    }).json
    hr_client.post('/employees', json={'name': 'Bert'})

    hr_client.post('/shift-types', json={
        'name': 'Tag',
        'start_time': '08:00',
        'end_time': '16:00',
        'requirements': [1, 1, 1, 1, 1, 1, 1],
    })

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})
    assert antwort.status_code == 201, antwort.json

    anna_termine = [a for a in antwort.json['assignments'] if a['employee_id'] == anna['id']]
    # Beweist, dass der Test nicht vakuos gruen ist: Anna muss tatsaechlich
    # eingeplant worden sein, sonst wuerde die folgende Schleife nichts pruefen.
    assert anna_termine, antwort.json['assignments']
    for termin in anna_termine:
        assert date.fromisoformat(termin['date']).weekday() == 1, termin
