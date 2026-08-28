"""Eingaben, die die Pruefung passieren und danach nichts tun.

Seit Python 3.11 akzeptiert date.fromisoformat() auch das Basisformat
'20260901'. Wer es nur zur Pruefung aufruft und danach die rohe Zeichenkette
speichert, legt eine Zeile an, die jeden spaeteren Vergleich verliert: das Tool
vergleicht Datumsangaben durchgehend als Zeichenketten, und '2026-09-15' liegt
vor '20260901'.

Das Ergebnis ist immer dasselbe und immer stumm - die Zeile steht da, sieht
richtig aus und wirkt nie.
"""

from datetime import date


BASIS = '20260901'
ISO = '2026-09-01'


def _anna(hr_client):
    return hr_client.post('/employees', json={
        'name': 'Anna', 'email': 'anna@example.com'}).json


# ---------- Datumsnormalisierung ----------


def test_ein_gesperrter_tag_wird_normalisiert(hr_client):
    """Sonst sperrt er nichts: der Generator vergleicht gegen ISO-Daten."""
    anna = _anna(hr_client)

    hr_client.put(f'/employees/{anna["id"]}', json={
        'name': 'Anna', 'unavailable_dates': [{'date': BASIS, 'reason': 'Umzug'}]})

    gelesen = hr_client.get(f'/employees/{anna["id"]}').json
    assert [d['date'] for d in gelesen['unavailable_dates']] == [ISO]


def test_eine_abwesenheit_wird_normalisiert(hr_client):
    """Eine Krankmeldung, die nicht wirkt, ist schlimmer als keine."""
    anna = _anna(hr_client)

    antwort = hr_client.post(f'/employees/{anna["id"]}/absences',
                             json={'date': BASIS, 'type': 'sick'})
    assert antwort.status_code in (200, 201), antwort.json

    gelesen = hr_client.get(f'/employees/{anna["id"]}/absences',
                            query_string={'year': 2026, 'month': 9}).json
    assert [a['date'] for a in gelesen] == [ISO]


def test_eine_oeffnungszeit_ausnahme_wird_normalisiert(hr_client):
    """Sonst bleibt der Betrieb an dem Tag offen, den jemand geschlossen hat."""
    antwort = hr_client.post('/business-hours/exceptions',
                             json={'date': BASIS, 'closed': True})
    assert antwort.status_code in (200, 201), antwort.json

    gelesen = hr_client.get('/business-hours/exceptions').json
    assert [e['date'] for e in gelesen] == [ISO]


def test_abweichende_schichtzeiten_werden_normalisiert(hr_client):
    """Sonst gilt die Ausnahme fuer ein Datum, das es im Plan nicht gibt.

    fetch_schedule() schluesselt die Ausnahmen nach (Datum, Schichtart) und
    setzt daran time_overridden. Mit '20260901' in der Tabelle trifft der
    Schluessel nie - die Ausnahme steht da und wirkt an keinem Tag.
    """
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}
        for wd in range(7)])
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': BASIS, 'shift_type_id': art['id'],
        'start_time': '10:00', 'end_time': '18:00'})
    assert antwort.status_code == 200, antwort.json

    plan = hr_client.get('/schedules/2026/9').json
    markiert = [z['date'] for z in plan['assignments'] if z['time_overridden']]
    assert markiert and set(markiert) == {ISO}


def test_ein_datum_ohne_sinn_bleibt_abgelehnt(hr_client):
    """Gegenprobe: normalisieren heisst nicht durchwinken."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}', json={
        'name': 'Anna', 'unavailable_dates': [{'date': '2026-02-30'}]})

    assert antwort.status_code == 400


# ---------- Grenzen, die fehlen ----------


def test_mehr_als_zehn_stunden_am_tag_werden_abgelehnt(hr_client):
    """Paragraph 3 ArbZG: acht Stunden, auf hoechstens zehn verlaengerbar.

    Ohne Obergrenze nimmt das Feld 12 an, und der Planer baut trotzdem keinen
    Block ueber zehn Stunden (MAX_BLOCK_MINUTES) - die Zahl steht dann da und
    bedeutet nichts.
    """
    antwort = hr_client.post('/employees', json={
        'name': 'Berta', 'email': 'berta@example.com', 'max_daily_hours': 12})

    assert antwort.status_code == 400
    assert '10' in antwort.json['message']


def test_genau_zehn_stunden_gehen(hr_client):
    """Gegenprobe: die Grenze selbst ist erlaubt."""
    antwort = hr_client.post('/employees', json={
        'name': 'Clara', 'email': 'clara@example.com', 'max_daily_hours': 10})

    assert antwort.status_code in (200, 201), antwort.json


def test_null_stunden_am_tag_werden_abgelehnt(hr_client):
    """Wer null Stunden am Tag arbeiten darf, kann nie eingeplant werden -
    das ist keine Arbeitszeitgrenze, das ist eine Deaktivierung."""
    antwort = hr_client.post('/employees', json={
        'name': 'Dora', 'email': 'dora@example.com', 'max_daily_hours': 0})

    assert antwort.status_code == 400


def test_ein_gesperrter_wochentag_ist_kein_wahrheitswert(hr_client):
    """Beim Nachpruefen gefunden: dieselbe Klasse, andere Stelle.

    unavailable_weekdays ging ueber parse_int_list() und blieb bei int()
    stehen. true sperrte den Dienstag.
    """
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}', json={
        'name': 'Anna', 'unavailable_weekdays': [True]})

    assert antwort.status_code == 400


def test_eine_erlaubte_schichtart_ist_kein_wahrheitswert(hr_client):
    """Und noch eine: allowed_shift_types nimmt dieselbe Liste. true waere
    die Schichtart mit der Nummer 1 - welche das ist, entscheidet der Zufall
    der Anlagereihenfolge."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}', json={
        'name': 'Anna', 'allowed_shift_types': [True]})

    assert antwort.status_code == 400


def test_eine_stundenzahl_ist_kein_wahrheitswert(hr_client):
    """float(True) ist 1.0. Eine Tagesgrenze von einer Stunde, weil jemand
    true geschickt hat - innerhalb der erlaubten Spanne und damit stumm."""
    antwort = hr_client.post('/employees', json={
        'name': 'Emma', 'email': 'emma@example.com', 'max_daily_hours': True})

    assert antwort.status_code == 400


def test_eine_wochenstundenzahl_auch_nicht(hr_client):
    """Gegenprobe ueber ein zweites Feld desselben Parsers: die Behebung
    gehoert in parse_optional_hours(), nicht in eine der Aufrufstellen."""
    antwort = hr_client.post('/employees', json={
        'name': 'Frida', 'email': 'frida@example.com', 'weekly_hours': True})

    assert antwort.status_code == 400


def test_eine_echte_stundenzahl_geht_weiterhin(hr_client):
    """Gegenprobe: 1 ist als Zahl in Ordnung, nur als Wahrheitswert nicht."""
    antwort = hr_client.post('/employees', json={
        'name': 'Greta', 'email': 'greta@example.com', 'max_daily_hours': 1})

    assert antwort.status_code in (200, 201), antwort.json


def test_ein_wahrheitswert_ist_kein_wochentag(hr_client):
    """int(True) ist 1. Ein Fenster fuer Dienstag, weil jemand true schickt."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json={
        'availability_mode': 'windows',
        'availability': [{'weekday': True, 'start_time': '08:00', 'end_time': '16:00'}]})

    assert antwort.status_code == 400


def test_ein_gebrochener_wochentag_wird_nicht_abgeschnitten(hr_client):
    """int(3.9) ist 3. Ein Fenster fuer Donnerstag, weil jemand 3.9 schickt."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json={
        'availability_mode': 'windows',
        'availability': [{'weekday': 3.9, 'start_time': '08:00', 'end_time': '16:00'}]})

    assert antwort.status_code == 400


def test_eine_liste_statt_eines_objekts_ist_ein_klientenfehler(hr_client):
    """Beim Schreiben der Tests selbst gestolpert: die Route ruft .get() auf
    dem geparsten Rumpf auf, und eine Liste hat kein .get.

    Das ergab einen 500er - also die Meldung "der Server ist kaputt" fuer
    etwas, das der Aufrufer falsch gemacht hat. Wer eine API gegen dieses Tool
    schreibt, sucht den Fehler dann an der falschen Stelle.
    """
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json=[
        {'weekday': 1, 'start_time': '08:00', 'end_time': '16:00'}])

    assert antwort.status_code == 400


# ---------- Dieselbe Eingabe, dieselbe Antwort ----------


def test_gleiche_zeiten_werden_auch_beim_tagesabweichenden_ueberschreiben_abgelehnt(hr_client):
    """Fuer die Zuweisung war das schon behoben, fuer die Tagesausnahme nicht.

    Gleicher Beginn und gleiches Ende ist keine Schicht der Laenge null:
    shift_duration_minutes() liest end <= start als "laeuft ueber Mitternacht"
    und macht daraus stillschweigend 1440 Minuten. Aus einer offensichtlich
    unsinnigen Eingabe wird ein Vierundzwanzigstundendienst.
    """
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': '10:00', 'end_time': '10:00'})

    assert antwort.status_code == 400


def test_eine_nachtschicht_geht_dort_weiterhin(hr_client):
    """Gegenprobe: end < start ist ausdruecklich erlaubt - das ist die
    Nachtschicht, nicht der Fehler."""
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': '22:00', 'end_time': '06:00'})

    assert antwort.status_code == 200, antwort.json


def test_eine_halbe_zeitangabe_nennt_das_fehlende_paar(hr_client):
    """Nur ein Ende ohne Beginn ergab "Format falsch" - die Zeit stimmt aber,
    es fehlt die andere Haelfte. Eine Meldung, die auf die falsche Stelle
    zeigt, kostet mehr Zeit als gar keine."""
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'], 'start_time': '10:00'})

    assert antwort.status_code == 400
    assert 'Format' not in antwort.json['message']


# ---------- Dasselbe Fenster zweimal ----------


def test_dasselbe_fenster_zweimal_wird_abgelehnt(hr_client):
    """Es stand zweimal in der Warnung und zweimal in der Liste.

    Der Generator kommt damit zurecht - ein Platz passt, wenn er in
    IRGENDEIN Fenster passt -, aber die Oberflaechen zeigen es doppelt, und
    niemand kann sehen, ob das Absicht war.
    """
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json={
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00'},
            {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00'},
        ]})

    assert antwort.status_code == 400


def test_zwei_fenster_am_selben_tag_bleiben_erlaubt(hr_client):
    """Gegenprobe, und die wichtigere Haelfte: der geteilte Dienst braucht
    genau das. Auch Ueberlappungen bleiben erlaubt - sie zusammenzufassen
    hiesse, eine Eingabe stillschweigend umzuschreiben."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json={
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '12:00'},
            {'weekday': 0, 'start_time': '10:00', 'end_time': '18:00'},
        ]})

    assert antwort.status_code == 200, antwort.json
    assert len(hr_client.get(f'/employees/{anna["id"]}').json['availability']) == 2


def test_dasselbe_fenster_mit_verschiedenen_grenzen_bleibt_erlaubt(hr_client):
    """Gegenprobe: gleiche Zeiten, verschiedene Gueltigkeit sind zwei
    verschiedene Aussagen - "bis Maerz so, ab April wieder"."""
    anna = _anna(hr_client)

    antwort = hr_client.put(f'/employees/{anna["id"]}/availability', json={
        'availability_mode': 'windows',
        'availability': [
            {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00',
             'valid_until': '2026-03-31'},
            {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00',
             'valid_from': '2026-04-01'},
        ]})

    assert antwort.status_code == 200, antwort.json


def test_leere_zeiten_setzen_die_ausnahme_zurueck(hr_client):
    """Beim Nachpruefen gefunden, und der Fehler kam aus derselben Aenderung.

    Das Formular schickt leere Felder als "" und nicht als null. Vorher fiel
    das auf die Formatpruefung und ergab eine 400; nach dem Umbau auf
    parse_assignment_times() - das "" zu None macht - fiel es hinter die
    Ruecksetz-Pruefung in ein INSERT mit NULL-Zeiten, und die Spalte ist NOT
    NULL. Also ein 500er, wo vorher wenigstens eine verstaendliche 400 stand.
    Geparst wird jetzt vor der Ruecksetz-Pruefung.
    """
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})
    hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': '10:00', 'end_time': '18:00'})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': '', 'end_time': ''})

    assert antwort.status_code == 200, antwort.json
    plan = hr_client.get('/schedules/2026/9').json
    assert not any(z['time_overridden'] for z in plan['assignments'])


def test_null_zeiten_setzen_die_ausnahme_weiterhin_zurueck(hr_client):
    """Gegenprobe: der bisherige Weg bleibt der bisherige Weg."""
    art = hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'}).json
    hr_client.post('/schedules/generate', json={'year': 2026, 'month': 9})
    hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': '10:00', 'end_time': '18:00'})

    antwort = hr_client.put('/schedules/2026/9/shift-times', json={
        'date': '2026-09-07', 'shift_type_id': art['id'],
        'start_time': None, 'end_time': None})

    assert antwort.status_code == 200, antwort.json
    plan = hr_client.get('/schedules/2026/9').json
    assert not any(z['time_overridden'] for z in plan['assignments'])
