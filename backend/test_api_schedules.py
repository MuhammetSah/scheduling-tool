"""Planerzeugung: Schutz vor stillem Datenverlust."""


def plan_vorbereiten(hr_client):
    """Ein Mitarbeiter, eine Schichtart, ein erzeugter Maerzplan."""
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Frueh',
        'start_time': '06:00',
        'end_time': '14:00',
        'requirements': [1, 1, 1, 1, 1, 0, 0],
    })
    # Seit Etappe 4 plant der Generator aus den Bedarfsbaendern, nicht mehr aus
    # den requirements der Schichtart. Die Zeile darueber bleibt trotzdem
    # stehen: sie beschreibt dasselbe Bild im alten Modell, und diese Tests
    # gehen ueber den Schutz vor stillem Datenverlust, nicht ueber die
    # Bedarfsquelle.
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wochentag, 'start_time': '06:00', 'end_time': '14:00',
         'required_count': 1}
        for wochentag in range(5)
    ])
    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})
    assert antwort.status_code == 201, antwort.json
    # Ohne mindestens eine echte Zuweisung wuerden die folgenden Tests aus
    # einem falschen Grund (leerer Plan statt Handkorrektur) durchlaufen bzw.
    # fehlschlagen - das hier stellt sicher, dass Anna tatsaechlich Schichten
    # bekommen hat.
    assert len(antwort.json['assignments']) > 0, antwort.json
    return antwort.json


def test_erzeugen_ohne_handkorrekturen_laeuft_durch(hr_client):
    plan_vorbereiten(hr_client)

    erneut = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})

    assert erneut.status_code == 201


def test_erzeugen_mit_handkorrekturen_fragt_nach(hr_client):
    plan = plan_vorbereiten(hr_client)
    erste = plan['assignments'][0]
    assert hr_client.put(f'/assignments/{erste["id"]}', json={'employee_id': None}).status_code == 200

    erneut = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3})

    assert erneut.status_code == 409
    assert erneut.json['manually_edited_count'] == 1


def test_bestaetigtes_erzeugen_ueberschreibt(hr_client):
    plan = plan_vorbereiten(hr_client)
    erste = plan['assignments'][0]
    hr_client.put(f'/assignments/{erste["id"]}', json={'employee_id': None})

    erneut = hr_client.post('/schedules/generate',
                            json={'year': 2026, 'month': 3, 'confirm': True})

    assert erneut.status_code == 201
