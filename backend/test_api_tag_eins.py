"""Der erste Tag auf einer leeren Datenbank.

Am 07.09.2026 laeuft die Instanz ab und wird neu aufgezogen. Dass die
Migrationen auf einer leeren Datenbank durchlaufen, faehrt der
backend-postgres-Job bei jedem Lauf. Ungeprueft war, ob das Werkzeug
demjenigen, der davor sitzt, auch SAGT, was noch fehlt.

Die Reihenfolge am Tag eins: Konto anlegen, Schichtart, Bedarf, Plan. Die
ersten beiden Schritte melden sich von selbst, wenn man sie ueberspringt.
Der dritte tat es nicht - "Plan erzeugen" antwortete mit 201, lieferte null
Bloecke, meldete null Luecken und sagte kein Wort. Aus Sicht des Betreibers:
gedrueckt, "in Ordnung" bekommen, nichts da.
"""


def test_ohne_schichtart_sagt_es_das_werkzeug(hr_client):
    """Gegenprobe zuerst: dieser Schritt meldete sich schon immer."""
    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 400
    assert 'Schichtart' in antwort.json['message']


def test_ohne_bedarf_sagt_es_das_werkzeug_auch(hr_client):
    """Der Kern.

    Mit Schichtart und ohne Bedarfsband gab es einen leeren Plan mit 201 und
    ohne Meldung - dieselbe Klasse von Fehler, die dieses Projekt sonst
    ueberall benennt: etwas meldet Erfolg und tut nichts.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 201, antwort.json
    assert 'Bedarf' in antwort.json.get('notice', '')


def test_mit_bedarf_wird_erzeugt(hr_client):
    """Gegenprobe, und die wichtigste: eine Umsetzung, die immer ablehnt,
    waere sonst ebenfalls gruen."""
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}
        for wd in range(7)])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 201, antwort.json
    assert hr_client.get('/schedules/2026/11').json['assignments']


def test_gepflegte_baender_ohne_bedarf_bleiben_erlaubt(hr_client):
    """Die feine Unterscheidung, und sie ist erreichbar.

    Geprueft wird, ob es UEBERHAUPT Bedarfsbaender gibt - nicht, ob am Ende
    Bloecke herauskommen. Ein Band mit Anzahl 0 ist eine gepflegte Aussage
    ("hier wird gerade niemand gebraucht") und ergibt keinen einzigen Block.
    Wer darauf eine Belehrung bekaeme, wuerde fuer Sorgfalt bestraft.

    Der naheliegendere Fall - Baender gepflegt, Betrieb den ganzen Monat
    geschlossen - laesst sich gar nicht herstellen: seit Etappe 3 lehnt
    reject_hours_conflicting_with_bands() das Schliessen eines Tages ab, an
    dem ein Band gespeichert ist. Ausprobiert, nicht angenommen.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': 0, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 0}])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 201, antwort.json
    assert 'notice' not in antwort.json
    assert hr_client.get('/schedules/2026/11').json['assignments'] == []


# ---------- Die Obergrenze der Suche ----------


def test_ein_zu_grosser_monat_sagt_es_statt_abzustuerzen(hr_client, monkeypatch):
    """Gefunden beim Messen (siehe test_scheduler_grenze.py).

    backtrack() rekursiert je Platz; oberhalb der Rekursionsgrenze scheiterte
    das Erzeugen mit einem 500er "Unerwarteter Serverfehler" - der Meldung,
    die am wenigsten sagt.

    Die Grenze wird hier heruntergesetzt statt einen Monat mit tausend
    Bloecken zu bauen: geprueft wird der Weg von der Ausnahme zur Meldung,
    nicht die Zahl selbst.
    """
    import scheduler

    monkeypatch.setattr(scheduler, 'max_plannable_slots', lambda: 3)
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 2}
        for wd in range(7)])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 400, antwort.json
    assert 'zu gro' in antwort.json['message']


def test_ein_normaler_monat_bleibt_unberuehrt(hr_client):
    """Gegenprobe: eine Grenze, die immer greift, waere sonst ebenfalls
    gruen."""
    hr_client.post('/employees', json={'name': 'Anna'})
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.put('/coverage-requirements', json=[
        {'weekday': wd, 'start_time': '08:00', 'end_time': '16:00', 'required_count': 1}
        for wd in range(7)])

    antwort = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 11})

    assert antwort.status_code == 201, antwort.json
