"""Eine Gesundheitsprüfung, die etwas prüft.

GET / meldet seit jeher {'status': 'ok'} - und fasst dabei die Datenbank nie
an. render.yaml verdrahtet healthCheckPath auf genau diese Route. Stirbt die
Datenbank, haelt Render den Dienst also fuer gesund und schickt ihm weiter
Anfragen, die samt und sonders mit 500 enden.

Am 07.09.2026 ist das der wahrscheinlichste Fehler: DATABASE_URL zeigt auf
nichts, die Anwendung startet, und alles sieht gut aus.

Oeffentlich, ohne Anmeldung: eine Gesundheitspruefung hinter einer Anmeldung
kann niemand als Gesundheitspruefung benutzen.
"""


def test_die_pruefung_ist_ohne_anmeldung_erreichbar(client):
    """Sonst kann Render sie nicht benutzen."""
    assert client.get('/health').status_code == 200


def test_sie_nennt_den_stand_der_migrationen(client):
    """Das Umstellungsblatt fragt danach: welcher Stand liegt an?"""
    antwort = client.get('/health').json

    assert antwort['status'] == 'ok'
    assert antwort['database'] == 'ok'
    assert antwort['migrations']['latest'].startswith('00')
    assert antwort['migrations']['applied'] > 0


def test_eine_unerreichbare_datenbank_meldet_503(client, monkeypatch):
    """Der Kern. Ohne das meldet die Pruefung Erfolg, waehrend nichts geht.

    Nachgestellt, indem die Abfrage scheitert - der Grund ist gleichgueltig,
    die Antwort darauf nicht.
    """
    import app as anwendung

    def kaputt():
        raise RuntimeError('keine Verbindung')

    monkeypatch.setattr(anwendung, 'get_db', kaputt)

    antwort = client.get('/health')

    assert antwort.status_code == 503
    assert antwort.json['database'] == 'unreachable'
    assert antwort.json['status'] != 'ok'


def test_sie_verraet_keine_betriebsdaten(client):
    """Oeffentlich heisst sparsam: der Migrationsstand ist eine Aussage ueber
    den Code, keine ueber die Belegschaft."""
    antwort = client.get('/health').json

    assert set(antwort) == {'status', 'database', 'migrations'}
    assert set(antwort['migrations']) == {'applied', 'latest'}


def test_die_wurzel_behauptet_keine_gesundheit_mehr(client):
    """Sie bleibt die Begruessung der API und sagt nicht mehr 'ok' - genau
    diese Zusage hat sie nie einloesen koennen."""
    antwort = client.get('/').json

    assert 'status' not in antwort
    assert antwort['health'] == '/health'
