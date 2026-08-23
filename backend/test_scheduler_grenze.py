"""Die Obergrenze der Suche, und dass sie sich meldet statt abzustuerzen.

Gefunden beim Messen, nicht beim Lesen: der Benchmark der Skalierung lief in
einen RecursionError. backtrack() in scheduler.py rekursiert einmal je Platz,
also ist die Rekursionstiefe die Anzahl der Bloecke eines Monats. Bei Pythons
Standardgrenze von 1000 laufen 930 Bloecke durch und 992 nicht mehr.

Das entspricht einem Betrieb mit rund dreissig Bloecken am Tag - eine grosse
Station, kein Gedankenspiel. Und es scheiterte mit einem 500er
"Unerwarteter Serverfehler", also der Meldung, die am wenigsten sagt.

Nicht behoben wird hier die Rekursion selbst. Sie in eine Schleife mit
eigenem Stapel umzuschreiben ist ein Eingriff in das heikelste Stueck des
Projekts - Branch-and-Bound samt Ruecknahme von sechs Zustandsstrukturen -,
und die 23 Bestandstests decken davon nur die Schichtzahlen ab. Was hier
passiert, ist die ehrliche Zwischenstufe: die Grenze wird benannt, bevor man
gegen sie laeuft.
"""

import pytest

from scheduler import PlanTooLarge, generate_schedule, max_plannable_slots


def _bloecke(anzahl):
    """Plaetze in der Form, die generate_schedule() erwartet."""
    return [
        {
            'date': '2026-08-%02d' % (i % 28 + 1),
            'weekday': i % 7,
            'week_start': '2026-08-03',
            'shift_type_id': 1,
            'slot_index': i,
            'is_weekend': i % 7 >= 5,
            'start_time': '08:00',
            'end_time': '16:00',
            'duration_minutes': 480,
        }
        for i in range(anzahl)
    ]


def _leute(anzahl):
    return [
        {'id': i, 'max_shifts_per_month': None, 'unavailable_weekdays': set(),
         'unavailable_dates': set(), 'allowed_shift_types': None}
        for i in range(1, anzahl + 1)
    ]


def test_zu_viele_bloecke_melden_sich(hr_client=None):
    """Der Kern: eine benannte Ausnahme statt eines RecursionError."""
    zu_viele = max_plannable_slots() + 50

    with pytest.raises(PlanTooLarge):
        generate_schedule(2026, 8, _leute(5), [], slots=_bloecke(zu_viele))


def test_die_ausnahme_nennt_beide_zahlen(hr_client=None):
    """Eine Grenze ohne Zahlen ist eine Beschwerde.

    Die gemeldete Grenze ist KLEINER als die, die dieser Test von sich aus
    liest - und das ist richtig so: generate_schedule() steht ein paar Rahmen
    tiefer im Stapel, und genau das rechnet max_plannable_slots() mit. Beim
    Schreiben zuerst auf Gleichheit geprueft, was die Zahl zu einer Konstante
    erklaert haette, die sie nicht ist.
    """
    zu_viele = max_plannable_slots() + 50

    with pytest.raises(PlanTooLarge) as fehler:
        generate_schedule(2026, 8, _leute(5), [], slots=_bloecke(zu_viele))

    assert fehler.value.slots == zu_viele
    assert 0 < fehler.value.limit <= max_plannable_slots()


def test_knapp_darunter_laeuft_durch(hr_client=None):
    """Gegenprobe, und die wichtigste: eine Grenze, die zu frueh greift,
    nimmt dem Werkzeug Faelle weg, die es koennte."""
    ergebnis = generate_schedule(
        2026, 8, _leute(40), [], slots=_bloecke(max_plannable_slots() - 20))

    assert ergebnis['assignments']


def test_die_grenze_haengt_an_der_rekursionsgrenze(hr_client=None):
    """Keine erfundene Zahl: sie leitet sich aus dem ab, was der Stapel noch
    hergibt. Wer sys.setrecursionlimit() hochsetzt, bekommt mehr - und wer
    tiefer im Aufrufstapel steht (Flask, Gunicorn), bekommt weniger."""
    import sys

    vorher = max_plannable_slots()
    alt = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(alt + 500)
        assert max_plannable_slots() == vorher + 500
    finally:
        sys.setrecursionlimit(alt)
