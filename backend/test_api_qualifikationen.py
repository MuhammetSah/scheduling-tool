"""Nachweise: was eine Schicht verlangt, und wer ihn hat.

Der letzte Punkt der Roadmap. Die interessante Haelfte ist nicht die
Zuordnung, sondern das ABLAUFDATUM: ein Ersthelferschein laeuft nach zwei
Jahren ab (DGUV Vorschrift 1 Paragraph 26 verlangt die Auffrischung), ein
Staplerschein ebenso. Ein Nachweis ohne Ablauf ist einer, den der Dienstplan
noch Jahre nach seinem Ende weiter beachtet.

Hart im Generator, Warnung bei der Handkorrektur - dieselbe Aufteilung, die
das ganze Werkzeug schon hat. Und ausdruecklich KEINE Sperre beim Tausch:
ob ein Nachweis rechtlich verlangt ist (Ersthelfer nach DGUV Vorschrift 1) oder
eine Hausregel ("kennt die Kaffeemaschine"), kann das Tool nicht wissen, und
eine Sperre darauf zu gruenden hiesse, es zu behaupten.
"""


def _nachweis(hr_client, name='Ersthelfer'):
    antwort = hr_client.post('/qualifications', json={'name': name})
    assert antwort.status_code in (200, 201), antwort.json
    return antwort.json


def _anna(hr_client, **abweichend):
    daten = {'name': 'Anna', 'email': 'anna@example.com'}
    daten.update(abweichend)
    return hr_client.post('/employees', json=daten).json


def _schichtart(hr_client, verlangt=(), name='Nacht'):
    art = hr_client.post('/shift-types', json={
        'name': name, 'start_time': '22:00', 'end_time': '06:00'}).json
    if verlangt:
        antwort = hr_client.put('/shift-types/%d/qualifications' % art['id'],
                                json={'qualification_ids': list(verlangt)})
        assert antwort.status_code == 200, antwort.json
    return art


def _gib(hr_client, employee, nachweis, valid_until=None):
    antwort = hr_client.put('/employees/%d/qualifications' % employee['id'], json={
        'qualifications': [{'qualification_id': nachweis['id'], 'valid_until': valid_until}]})
    assert antwort.status_code == 200, antwort.json
    return antwort.json


def _erzeuge(hr_client, art, jahr=2026, monat=11):
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '22:00', 'end_time': '06:00', 'required_count': 1}
        for wd in range(7)])
    hr_client.post('/schedules/generate', json={'year': jahr, 'month': monat})
    return hr_client.get('/schedules/%d/%d' % (jahr, monat)).json


# ---------- Der Katalog ----------


def test_ein_nachweis_laesst_sich_anlegen_und_lesen(hr_client):
    _nachweis(hr_client)

    assert [q['name'] for q in hr_client.get('/qualifications').json] == ['Ersthelfer']


def test_derselbe_name_zweimal_wird_abgelehnt(hr_client):
    """Zwei Nachweise, die dasselbe meinen, teilen die Belegschaft in zwei
    Haelften, von denen jede den falschen traegt."""
    _nachweis(hr_client)

    assert hr_client.post('/qualifications', json={'name': 'Ersthelfer'}).status_code == 409


def test_ein_geloeschter_nachweis_verschwindet_ueberall(hr_client):
    """ON DELETE CASCADE: was es nicht mehr gibt, kann niemand halten und
    keine Schicht verlangen."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis)
    art = _schichtart(hr_client, [nachweis['id']])

    hr_client.delete('/qualifications/%d' % nachweis['id'])

    assert hr_client.get('/employees/%d' % anna['id']).json['qualifications'] == []
    assert hr_client.get('/shift-types').json[0]['required_qualifications'] == []


# ---------- Der Generator: hart ----------


def test_ohne_nachweis_wird_niemand_eingeplant(hr_client):
    """Der Kern. Wie bei allowed_shift_types eine harte Bedingung: ein Plan,
    der nachgearbeitet werden muss, ist keine Hilfe."""
    nachweis = _nachweis(hr_client)
    _anna(hr_client)
    art = _schichtart(hr_client, [nachweis['id']])

    plan = _erzeuge(hr_client, art)

    assert plan['assignments'], 'es gibt keine Bloecke - der Aufbau stimmt nicht'
    assert all(z['employee_id'] is None for z in plan['assignments'])


def test_mit_nachweis_wird_eingeplant(hr_client):
    """Gegenprobe, und die wichtigste: ohne sie waere ein Generator, der
    niemanden einplant, ebenfalls gruen."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis)
    art = _schichtart(hr_client, [nachweis['id']])

    plan = _erzeuge(hr_client, art)

    assert any(z['employee_id'] == anna['id'] for z in plan['assignments'])


def test_eine_schicht_ohne_anforderung_nimmt_jeden(hr_client):
    """Gegenprobe: ein leerer Katalog darf niemanden aussperren."""
    _nachweis(hr_client)
    anna = _anna(hr_client)
    art = _schichtart(hr_client)

    plan = _erzeuge(hr_client, art)

    assert any(z['employee_id'] == anna['id'] for z in plan['assignments'])


def test_zwei_verlangte_nachweise_brauchen_beide(hr_client):
    """Alle, nicht irgendeiner: die Anforderung beschreibt die Arbeit."""
    erst = _nachweis(hr_client, 'Ersthelfer')
    zweit = _nachweis(hr_client, 'Medikamentengabe')
    anna = _anna(hr_client)
    _gib(hr_client, anna, erst)
    art = _schichtart(hr_client, [erst['id'], zweit['id']])

    plan = _erzeuge(hr_client, art)

    assert all(z['employee_id'] is None for z in plan['assignments'])


# ---------- Das Ablaufdatum ----------


def test_ein_abgelaufener_nachweis_zaehlt_nicht(hr_client):
    """Die eigentliche Haelfte dieser Etappe.

    Ein Nachweis, der am 31.10. endet, traegt keine Schicht im November.
    """
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='2026-10-31')
    art = _schichtart(hr_client, [nachweis['id']])

    plan = _erzeuge(hr_client, art)

    assert all(z['employee_id'] is None for z in plan['assignments'])


def test_ein_nachweis_ohne_ablauf_zaehlt_immer(hr_client):
    """Gegenprobe: NULL heisst "laeuft nicht ab", nicht "abgelaufen"."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until=None)
    art = _schichtart(hr_client, [nachweis['id']])

    plan = _erzeuge(hr_client, art)

    assert any(z['employee_id'] == anna['id'] for z in plan['assignments'])


def test_der_ablauf_gilt_taggenau_und_einschliesslich(hr_client):
    """Ein Nachweis bis zum 15.11. traegt den 15. noch und den 16. nicht mehr.

    Dieselbe einschliessende Grenze wie bei valid_until der
    Arbeitszeitfenster - zwei benachbarte Regeln, die "bis" verschieden
    auslegen, sind eine Falle.
    """
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='2026-11-15')
    art = _schichtart(hr_client, [nachweis['id']])

    plan = _erzeuge(hr_client, art)

    besetzt = {z['date'] for z in plan['assignments'] if z['employee_id'] == anna['id']}
    assert '2026-11-15' in besetzt
    assert '2026-11-16' not in besetzt


def test_ein_ablaufdatum_wird_normalisiert(hr_client):
    """Fallstrick 19: geprueft UND normalisiert.

    '20261115' passiert date.fromisoformat() und verliert danach jeden
    Zeichenkettenvergleich - der Nachweis liefe nie ab.
    """
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='20261115')

    gelesen = hr_client.get('/employees/%d' % anna['id']).json['qualifications']
    assert gelesen[0]['valid_until'] == '2026-11-15'


def test_ein_unsinniges_ablaufdatum_wird_abgelehnt(hr_client):
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)

    antwort = hr_client.put('/employees/%d/qualifications' % anna['id'], json={
        'qualifications': [{'qualification_id': nachweis['id'],
                            'valid_until': '2026-02-30'}]})

    assert antwort.status_code == 400


# ---------- Die Handkorrektur: Warnung ----------


def test_die_handkorrektur_meldet_den_fehlenden_nachweis(hr_client):
    """Warnung statt Sperre, wie ueberall auf diesem Pfad."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    berta = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com'}).json
    _gib(hr_client, berta, nachweis)
    art = _schichtart(hr_client, [nachweis['id']])
    plan = _erzeuge(hr_client, art)
    platz = plan['assignments'][0]

    antwort = hr_client.put('/assignments/%d' % platz['id'], json={
        'employee_id': anna['id'],
        'start_time': platz['start_time'], 'end_time': platz['end_time']})

    assert antwort.status_code == 200, antwort.json
    assert any('Ersthelfer' in w for w in antwort.json['warnings']), antwort.json


def test_die_handkorrektur_meldet_den_abgelaufenen_nachweis_eigens(hr_client):
    """"Anna hat den Nachweis nicht" und "Annas Nachweis ist abgelaufen" sind
    zwei verschiedene Nachrichten - die zweite sagt, was zu tun ist."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='2026-10-31')
    art = _schichtart(hr_client, [nachweis['id']])
    plan = _erzeuge(hr_client, art)
    platz = plan['assignments'][0]

    antwort = hr_client.put('/assignments/%d' % platz['id'], json={
        'employee_id': anna['id'],
        'start_time': platz['start_time'], 'end_time': platz['end_time']})

    assert any('abgelaufen' in w for w in antwort.json['warnings']), antwort.json


def test_mit_gueltigem_nachweis_meldet_die_handkorrektur_nichts(hr_client):
    """Gegenprobe: eine Umsetzung, die immer meldet, waere sonst gruen."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis)
    art = _schichtart(hr_client, [nachweis['id']])
    plan = _erzeuge(hr_client, art)
    platz = plan['assignments'][0]

    antwort = hr_client.put('/assignments/%d' % platz['id'], json={
        'employee_id': anna['id'],
        'start_time': platz['start_time'], 'end_time': platz['end_time']})

    assert not any('Ersthelfer' in w for w in antwort.json['warnings']), antwort.json


# ---------- Wer darf was ----------


def test_ein_mitarbeiter_darf_den_katalog_nicht_aendern(hr_client):
    anna = _anna(hr_client)
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    assert hr_client.post('/qualifications', json={'name': 'X'}).status_code == 403


def test_ein_mitarbeiter_sieht_seine_eigenen_nachweise(hr_client):
    """Sie stehen in der Auskunft nach Art. 15 und gehoeren ihm."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='2027-01-01')
    konto = hr_client.post('/register', json={
        'username': 'anna', 'role': 'employee', 'employee_id': anna['id']}).json
    with hr_client.session_transaction() as sitzung:
        sitzung['user_id'] = konto['id']

    daten = hr_client.get('/employees/%d/data-export' % anna['id']).json

    assert [q['name'] for q in daten['qualifications']] == ['Ersthelfer']


# ---------- Beim Nachpruefen gefunden ----------


def test_ein_nicht_listenwert_loescht_nichts(hr_client):
    """`{"qualifications": false}` lief ueber `or []` in ein leeres Ersetzen -
    also loeschte ein Tippfehler still alle Nachweise der Person.

    Dieselbe Klasse wie in Etappe 6a: eine Eingabe, die die Pruefung passiert
    und danach etwas anderes tut, als sie aussieht.
    """
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis)

    antwort = hr_client.put('/employees/%d/qualifications' % anna['id'],
                            json={'qualifications': False})

    assert antwort.status_code == 400, antwort.json
    assert hr_client.get('/employees/%d' % anna['id']).json['qualifications']


def test_eine_leere_liste_loescht_weiterhin(hr_client):
    """Gegenprobe: das Ersetzen mit nichts ist eine Aussage und bleibt sie."""
    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis)

    antwort = hr_client.put('/employees/%d/qualifications' % anna['id'],
                            json={'qualifications': []})

    assert antwort.status_code == 200, antwort.json
    assert hr_client.get('/employees/%d' % anna['id']).json['qualifications'] == []


def test_eine_zeichenkette_ist_keine_kennungsliste(hr_client):
    """parse_int_list('12') laeuft ueber die Zeichen und ergibt [1, 2] -
    zwei Nachweise, die niemand genannt hat."""
    _nachweis(hr_client)
    art = _schichtart(hr_client)

    antwort = hr_client.put('/shift-types/%d/qualifications' % art['id'],
                            json={'qualification_ids': '12'})

    assert antwort.status_code == 400, antwort.json


def test_die_bestaetigung_ist_uebersetzt(hr_client):
    """t() faellt bei einem unbekannten Schluessel auf den Schluessel selbst
    zurueck - die Meldung stuende dann als "shift_type_updated" da."""
    art = _schichtart(hr_client)

    antwort = hr_client.put('/shift-types/%d/qualifications' % art['id'],
                            json={'qualification_ids': []})

    assert antwort.json['message'] != 'shift_type_updated'


def test_das_anonymisieren_nimmt_die_nachweise_mit(hr_client):
    """Ein Nachweis ist eine persoenliche Angabe.

    Etappe 5i raeumt beim Loeschen Fenster, gesperrte Tage, Abwesenheiten und
    erlaubte Schichtarten weg - die Nachweise kamen spaeter dazu und standen
    nicht auf der Liste. Ein Grabstein mit Ersthelferschein ist genau das, was
    die Anonymisierung verhindern soll.
    """
    from app import get_db

    nachweis = _nachweis(hr_client)
    anna = _anna(hr_client)
    _gib(hr_client, anna, nachweis, valid_until='2027-01-01')

    hr_client.delete('/employees/%d' % anna['id'])

    with hr_client.application.app_context():
        cursor = get_db().cursor()
        cursor.execute('SELECT COUNT(*) AS n FROM employee_qualifications '
                       'WHERE employee_id = ?', (anna['id'],))
        assert cursor.fetchone()['n'] == 0
