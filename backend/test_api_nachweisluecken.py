"""Warum eine Deckungsluecke offen bleibt - und was ein Mitarbeiterkonto davon
nicht zu sehen bekommt.

Anlass war ein Durchgang mit acht Leuten, drei Schichtarten und einem
Ersthelfer-Nachweis am Fruehdienst: 44 unbesetzte Schichten, zweiundzwanzigmal
dieselbe Zeile "2 Personen fehlen", sechs sichtbar freie Leute daneben und
nirgends ein Wort darueber, dass genau eine Person auf der Liste den verlangten
Nachweis hat. Wer das liest, haelt den Generator fuer kaputt.

Die Luecke selbst kann das nicht sagen: coverage_gaps() rechnet mit Baendern
und gedeckten Intervallen, sonst nichts. qualification_shortfalls() rechnet
danebenher und meldet ausschliesslich das Beweisbare - an einem Tag, an dem
eine Schichtart mehr Plaetze hat als es Leute gibt, die sie ueberhaupt
uebernehmen duerfen, bleibt der Ueberhang zwangslaeufig offen.
"""


def _nachweis(hr_client, name='Ersthelfer'):
    return hr_client.post('/qualifications', json={'name': name}).json


def _person(hr_client, name, **abweichend):
    daten = {'name': name, 'email': f'{name.lower()}@example.com'}
    daten.update(abweichend)
    antwort = hr_client.post('/employees', json=daten)
    assert antwort.status_code == 201, antwort.json
    return antwort.json


def _art(hr_client, name, von, bis, verlangt=()):
    art = hr_client.post('/shift-types', json={
        'name': name, 'start_time': von, 'end_time': bis}).json
    if verlangt:
        hr_client.put('/shift-types/%d/qualifications' % art['id'],
                      json={'qualification_ids': list(verlangt)})
    return art


def _gib(hr_client, person, nachweis, valid_until=None):
    hr_client.put('/employees/%d/qualifications' % person['id'], json={
        'qualifications': [{'qualification_id': nachweis['id'],
                            'valid_until': valid_until}]})


def _bedarf(hr_client, von, bis, anzahl):
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': von, 'end_time': bis, 'required_count': anzahl}
        for wd in range(5)])


def _plan(hr_client, jahr=2026, monat=9):
    hr_client.post('/schedules/generate', json={'year': jahr, 'month': monat})
    return hr_client.get('/schedules/%d/%d' % (jahr, monat)).json


def _drei_leute_ein_ersthelfer(hr_client):
    """Der Fall aus dem Durchgang, klein gemacht: drei Plaetze, ein Nachweis."""
    nachweis = _nachweis(hr_client)
    art = _art(hr_client, 'Frühdienst', '06:00', '14:00', [nachweis['id']])
    anna = _person(hr_client, 'Anna')
    _gib(hr_client, anna, nachweis)
    _person(hr_client, 'Bernd')
    _person(hr_client, 'Clara')
    _bedarf(hr_client, '06:00', '14:00', 3)
    return nachweis, art


# ---------- Was gemeldet wird ----------


def test_zu_wenige_nachweise_werden_beim_namen_genannt(hr_client):
    """Die Zahlen, die den Rest der Seite erklaeren."""
    _nachweis_obj, art = _drei_leute_ein_ersthelfer(hr_client)

    plan = _plan(hr_client)

    assert plan['unfilled_count'] > 0
    luecken = plan['qualification_shortfalls']
    assert len(luecken) == 1
    eintrag = luecken[0]
    assert eintrag['shift_type_id'] == art['id']
    assert eintrag['shift_type_name'] == 'Frühdienst'
    assert eintrag['qualifications'] == ['Ersthelfer']
    assert eintrag['slots'] == 3
    assert eintrag['eligible'] == 1
    assert eintrag['active_employees'] == 3
    # September 2026 hat 22 Werktage - jeder einzelne trifft es.
    assert eintrag['dates_affected'] == 22


def test_genug_nachweise_werden_nicht_gemeldet(hr_client):
    """Die Gegenprobe. Sonst waere die Meldung nur ein Dauerzustand.

    Der Bedarf bleibt bei drei, aber jetzt haben alle drei den Nachweis: was
    offen bleibt, liegt dann an Arbeitszeit oder Ruhezeit, und dazu hat diese
    Meldung nichts zu sagen.
    """
    nachweis = _nachweis(hr_client)
    _art(hr_client, 'Frühdienst', '06:00', '14:00', [nachweis['id']])
    for name in ('Anna', 'Bernd', 'Clara'):
        _gib(hr_client, _person(hr_client, name), nachweis)
    _bedarf(hr_client, '06:00', '14:00', 3)

    assert _plan(hr_client)['qualification_shortfalls'] == []


def test_eine_schichtart_ohne_verlangten_nachweis_bleibt_stumm(hr_client):
    """Unbesetzt ist nicht dasselbe wie unbesetzbar.

    Vier Plaetze und drei Leute: jeden Tag bleibt einer offen, aber kein
    Nachweis ist im Spiel. "0 von 3 haben den Nachweis" waere hier eine
    Erklaerung fuer etwas, das ganz woanders herkommt.
    """
    _art(hr_client, 'Frühdienst', '06:00', '14:00')
    for name in ('Anna', 'Bernd', 'Clara'):
        _person(hr_client, name)
    _bedarf(hr_client, '06:00', '14:00', 4)

    plan = _plan(hr_client)

    assert plan['unfilled_count'] > 0
    assert plan['qualification_shortfalls'] == []


def test_ein_abgelaufener_nachweis_zaehlt_nicht_mit(hr_client):
    """Dieselbe Lesart wie holds_qualification_on(): gueltig bis einschliesslich.

    Anna haelt den Schein, er endet aber vor dem Monat. Sie steht damit auf
    derselben Seite wie jemand ohne Schein - und die Meldung muss das genauso
    zaehlen, sonst nennt sie eine Zahl, nach der der Generator nicht plant.
    """
    nachweis = _nachweis(hr_client)
    _art(hr_client, 'Frühdienst', '06:00', '14:00', [nachweis['id']])
    _gib(hr_client, _person(hr_client, 'Anna'), nachweis, valid_until='2026-08-31')
    _person(hr_client, 'Bernd')
    _bedarf(hr_client, '06:00', '14:00', 2)

    eintrag = _plan(hr_client)['qualification_shortfalls'][0]

    assert eintrag['eligible'] == 0


def test_wer_die_schichtart_gar_nicht_uebernehmen_darf_zaehlt_nicht_mit(hr_client):
    """Der Fall, der die Meldung ohne diese Regel unbrauchbar machen wuerde.

    Dilek hat den Ersthelferschein, ist aber auf den Kurzdienst festgelegt.
    "2 von 2 haben den Nachweis" waere formal wahr und in der Sache falsch:
    fuer den Fruehdienst steht genau eine Person zur Verfuegung.
    """
    nachweis = _nachweis(hr_client)
    kurz = _art(hr_client, 'Kurzdienst', '09:00', '13:00')
    _art(hr_client, 'Frühdienst', '06:00', '14:00', [nachweis['id']])
    _gib(hr_client, _person(hr_client, 'Anna'), nachweis)
    _gib(hr_client, _person(hr_client, 'Dilek', allowed_shift_types=[kurz['id']]), nachweis)
    _bedarf(hr_client, '06:00', '14:00', 2)

    eintrag = _plan(hr_client)['qualification_shortfalls'][0]

    assert eintrag['eligible'] == 1
    assert eintrag['active_employees'] == 2


def test_eine_inaktive_person_zaehlt_nicht_mit(hr_client):
    """Wer nicht eingeplant wird, kann keine Luecke schliessen."""
    nachweis = _nachweis(hr_client)
    _art(hr_client, 'Frühdienst', '06:00', '14:00', [nachweis['id']])
    _gib(hr_client, _person(hr_client, 'Anna'), nachweis)
    _gib(hr_client, _person(hr_client, 'Bernd', active=False), nachweis)
    _bedarf(hr_client, '06:00', '14:00', 2)

    eintrag = _plan(hr_client)['qualification_shortfalls'][0]

    assert eintrag['eligible'] == 1
    assert eintrag['active_employees'] == 1


# ---------- Was ein Mitarbeiterkonto davon sieht ----------


def _als_mitarbeiter(hr_client, employee_id, username='anna'):
    konto = hr_client.post('/register', json={
        'username': username, 'role': 'employee', 'employee_id': employee_id}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']
    return hr_client


def test_ein_mitarbeiter_bekommt_die_nachweisluecken_nicht(hr_client):
    """Welche Schicht der Betrieb nicht besetzt bekommt, ist die Sicht der
    Personalabteilung - dieselbe Linie wie bei coverage_gaps."""
    _drei_leute_ein_ersthelfer(hr_client)
    _plan(hr_client)
    hr_client.put('/schedules/2026/9/status', json={'status': 'published'})
    anna = next(p for p in hr_client.get('/employees').json if p['name'] == 'Anna')

    plan = _als_mitarbeiter(hr_client, anna['id']).get('/schedules/2026/9').json

    assert plan['scope'] == 'own'
    assert 'qualification_shortfalls' not in plan


def test_ein_mitarbeiter_bekommt_den_arbeitszeitvergleich_nicht(hr_client):
    """average_hours nennt Kolleginnen mit Namen und Stundenzahl.

    Die Route sagt in ihrem eigenen Kommentar zu, den Arbeitszeitvergleich
    nicht mitzuschicken - "which is a management view" -, und die Ansicht im
    Browser rechnet seit jeher damit, dass das Feld hier fehlt. Nur der Server
    hat es trotzdem mitgeschickt. In den meisten Monaten ist die Liste leer,
    deshalb ist es nie aufgefallen; in einem Monat mit jemandem ueber der
    Grenze haette jedes Mitarbeiterkonto dessen Namen und Stunden bekommen.
    """
    _drei_leute_ein_ersthelfer(hr_client)
    _plan(hr_client)
    hr_client.put('/schedules/2026/9/status', json={'status': 'published'})
    anna = next(p for p in hr_client.get('/employees').json if p['name'] == 'Anna')

    plan = _als_mitarbeiter(hr_client, anna['id']).get('/schedules/2026/9').json

    assert 'average_hours' not in plan


def test_die_personalabteilung_bekommt_beides_weiterhin(hr_client):
    """Die Gegenprobe zu den zwei Tests darueber."""
    _drei_leute_ein_ersthelfer(hr_client)

    plan = _plan(hr_client)

    assert plan['average_hours'] == []
    assert plan['qualification_shortfalls'] != []
