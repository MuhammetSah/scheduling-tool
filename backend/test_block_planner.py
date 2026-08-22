"""Stufe 1 der Planung: aus Bedarf und Vorlagen werden Bloecke.

Reine Rechentests ohne Datenbank und ohne Flask, wie test_coverage_model.py
nebenan. Geprueft wird, welche Bloecke ein Tag bekommt - nicht, wer sie
arbeitet; das entscheidet der Suchkern in scheduler.py.
"""

from collections import Counter

from block_planner import cover_demand
from coverage_model import coverage_curve


def band(start_time, end_time, required_count):
    return {'start_time': start_time, 'end_time': end_time, 'required_count': required_count}


def vorlage(shift_type_id, start_time, end_time):
    return {'id': shift_type_id, 'start_time': start_time, 'end_time': end_time}


def zeiten(bloecke):
    return sorted((b['start_time'], b['end_time']) for b in bloecke)


def test_vorlage_deckt_ihr_eigenes_band_genau():
    """Der Normalfall: eine Vorlage, ein daraus abgeleitetes Band."""
    bloecke = cover_demand([band('06:00', '14:00', 3)], [vorlage(1, '06:00', '14:00')])

    assert len(bloecke) == 3
    assert all(b['shift_type_id'] == 1 for b in bloecke)
    assert all((b['start_time'], b['end_time']) == ('06:00', '14:00') for b in bloecke)


def test_gestaffelter_bedarf_wird_von_einer_vorlage_und_einem_rest_gedeckt():
    """Baender tragen absolute Besetzungsstaerke, nicht additive.

    06:00-08:00 mit 2 und 08:00-14:00 mit 3 heisst: ab 08:00 sollen INSGESAMT
    drei Leute da sein, nicht 2+3. Zwei tragen die ganze Vorlage, der dritte
    kommt um 08:00 dazu.
    """
    bloecke = cover_demand(
        [band('06:00', '08:00', 2), band('08:00', '14:00', 3)],
        [vorlage(1, '06:00', '14:00')],
    )

    assert zeiten(bloecke) == [('06:00', '14:00'), ('06:00', '14:00'), ('08:00', '14:00')]
    voll = [b for b in bloecke if b['start_time'] == '06:00']
    assert all(b['shift_type_id'] == 1 for b in voll)


def test_bedarf_ohne_passende_vorlage_wird_vorlagenloser_block():
    bloecke = cover_demand([band('10:00', '16:00', 1)], [vorlage(1, '06:00', '14:00')])

    assert bloecke == [{'shift_type_id': None, 'start_time': '10:00', 'end_time': '16:00'}]


def test_vorlage_ueber_den_bedarf_hinaus_wird_nicht_benutzt():
    """Eine Vorlage, die laenger laeuft als das Band, wuerde ueberbesetzen.

    Band 08:00-14:00, Vorlage 06:00-14:00: die beiden Stunden davor hat
    niemand bestellt. Statt die Vorlage zu nehmen, entsteht ein Block genau
    ueber dem Bedarf. Zu wenig zu planen ist die harmlose Richtung - zu viel
    kostet Geld und stuende in keinem Bedarfsband.
    """
    bloecke = cover_demand([band('08:00', '14:00', 2)], [vorlage(1, '06:00', '14:00')])

    assert zeiten(bloecke) == [('08:00', '14:00'), ('08:00', '14:00')]
    assert all(b['shift_type_id'] is None for b in bloecke)


def test_nachtband_ueber_mitternacht():
    bloecke = cover_demand([band('22:00', '06:00', 1)], [vorlage(1, '22:00', '06:00')])

    assert bloecke == [{'shift_type_id': 1, 'start_time': '22:00', 'end_time': '06:00'}]


def test_ohne_baender_keine_bloecke():
    assert cover_demand([], [vorlage(1, '06:00', '14:00')]) == []


def test_ohne_vorlagen_entstehen_bloecke_aus_dem_bedarf_allein():
    bloecke = cover_demand([band('08:00', '16:00', 2)], [])

    assert zeiten(bloecke) == [('08:00', '16:00'), ('08:00', '16:00')]
    assert all(b['shift_type_id'] is None for b in bloecke)


def test_kurzes_band_wird_nicht_verworfen():
    """Die Mindestblocklaenge gilt fuer den Zuschnitt, nicht fuer den Bedarf.

    Ein Band von zwei Stunden hat jemand bewusst so gepflegt. Es unter Verweis
    auf MIN_BLOCK_MINUTES still fallen zu lassen, hiesse eine Eingabe
    anzunehmen und zu verwerfen.
    """
    bloecke = cover_demand([band('12:00', '14:00', 1)], [])

    assert zeiten(bloecke) == [('12:00', '14:00')]


def test_aus_vorlagen_abgeleitete_baender_ergeben_wieder_die_vorlagenbloecke():
    """Die Messlatte der ganzen Umstellung.

    Migration 0007 hat die Bedarfsbaender aus genau diesen Vorlagen
    abgeleitet. Auf unveraendertem Bestand muss cover_demand() daraus wieder
    exakt die Bloecke bauen, die build_slots() bisher gebaut hat - sonst
    aendert die Umstellung stillschweigend die Plaene.
    """
    vorlagen = [vorlage(1, '06:00', '14:00'), vorlage(2, '14:00', '22:00')]
    baender = coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 3},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 2},
    ])

    bloecke = cover_demand(baender, vorlagen)

    assert Counter(b['shift_type_id'] for b in bloecke) == {1: 3, 2: 2}


def test_ueberlappende_vorlagen_ergeben_die_erwartete_staffelung():
    """Zwei Vorlagen, die sich ueberschneiden - die abgeleitete Kurve hat drei
    Baender, und beide Vorlagen muessen darin wiedererkannt werden."""
    vorlagen = [vorlage(1, '06:00', '14:00'), vorlage(2, '10:00', '18:00')]
    baender = coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '10:00', 'end_time': '18:00', 'required_count': 1},
    ])

    bloecke = cover_demand(baender, vorlagen)

    assert Counter(b['shift_type_id'] for b in bloecke) == {1: 2, 2: 1}


def test_das_ergebnis_haengt_nicht_von_der_reihenfolge_der_vorlagen_ab():
    """Determinismus: derselbe Tag muss zweimal denselben Plan ergeben,
    sonst wandern Bloecke bei jedem Erzeugen ohne Grund umher."""
    baender = [band('06:00', '08:00', 2), band('08:00', '14:00', 3)]
    vorlagen = [vorlage(1, '06:00', '14:00'), vorlage(2, '08:00', '14:00')]

    vorwaerts = cover_demand(baender, vorlagen)
    rueckwaerts = cover_demand(baender, list(reversed(vorlagen)))

    assert zeiten(vorwaerts) == zeiten(rueckwaerts)
    assert Counter(b['shift_type_id'] for b in vorwaerts) == \
        Counter(b['shift_type_id'] for b in rueckwaerts)


def test_die_schulter_wird_nicht_als_eigener_rest_abgehaengt():
    """Regressionstest gegen eine naheliegende, aber schlechte Gewichtung.

    Bedarf 06:00-08:00 fuer zwei und 08:00-14:00 fuer drei, dazu beide
    Vorlagen. Wer die Vorlage nach "traegt am meisten Bedarf ab" (Anzahl mal
    Dauer) waehlt, nimmt zuerst 08:00-14:00 dreimal und laesst 06:00-08:00 als
    zwei Zwei-Stunden-Bloecke stehen: fuenf Leute statt drei, und zwei
    Bloecke, die niemand arbeiten will.

    Drei ist zugleich das Minimum - unter die hoechste Spitze der
    Bedarfskurve kommt keine Loesung.
    """
    bloecke = cover_demand(
        [band('06:00', '08:00', 2), band('08:00', '14:00', 3)],
        [vorlage(1, '06:00', '14:00'), vorlage(2, '08:00', '14:00')],
    )

    assert len(bloecke) == 3
    assert zeiten(bloecke) == [('06:00', '14:00'), ('06:00', '14:00'), ('08:00', '14:00')]
    assert Counter(b['shift_type_id'] for b in bloecke) == {1: 2, 2: 1}


def test_block_ohne_vorlage_bleibt_arbeitbar_lang():
    """Durchgehender Bedarf ueber 14 Stunden ohne passende Vorlage.

    Ein einziger Block darueber waere nach Paragraph 3 ArbZG von niemandem zu
    besetzen und wuerde als Ganzes zur Luecke. Er zerfaellt deshalb in
    Stuecke von hoechstens zehn Stunden.
    """
    bloecke = cover_demand([band('06:00', '20:00', 1)], [])

    assert len(bloecke) == 2
    assert zeiten(bloecke) == [('06:00', '16:00'), ('16:00', '20:00')]
