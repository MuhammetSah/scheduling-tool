"""Stufe 1 der Planung: aus Bedarf und Vorlagen werden Bloecke.

Reine Rechentests ohne Datenbank und ohne Flask, wie test_coverage_model.py
nebenan. Geprueft wird, welche Bloecke ein Tag bekommt - nicht, wer sie
arbeitet; das entscheidet der Suchkern in scheduler.py.
"""

from collections import Counter

from block_planner import cover_demand, plan_day
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


# ---------- Zuschnitt auf Arbeitszeitfenster ----------


def mitarbeiter(employee_id, fenster=None, max_daily_hours=10):
    """Ein Kandidat, wie plan_day() ihn erwartet.

    Ohne Fenster gilt 'anytime' - das Bestandsverhalten, keine
    Uhrzeit-Einschraenkung.
    """
    return {
        'id': employee_id,
        'availability_mode': 'windows' if fenster else 'anytime',
        'availability': fenster or [],
        'max_daily_hours': max_daily_hours,
        'unavailable_weekdays': set(),
        'unavailable_dates': set(),
        'allowed_shift_types': None,
    }


def fenster(weekday, start_time, end_time, valid_from=None, valid_until=None):
    return {
        'weekday': weekday, 'start_time': start_time, 'end_time': end_time,
        'valid_from': valid_from, 'valid_until': valid_until,
    }


DIENSTAG = 1
EIN_DIENSTAG = '2026-09-01'


def test_block_wird_auf_das_einzige_passende_fenster_gekuerzt():
    """Der Kern der Etappe.

    Drei Plaetze 06:00-14:00, zwei uneingeschraenkte Leute und eine Person mit
    Fenster 08:00-14:00. Ohne Zuschnitt bliebe der dritte Platz unbesetzt,
    obwohl sechs der acht Stunden zu decken waeren.
    """
    bloecke = plan_day(
        [band('06:00', '14:00', 3)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1), mitarbeiter(2),
         mitarbeiter(3, [fenster(DIENSTAG, '08:00', '14:00')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '14:00'), ('06:00', '14:00'), ('08:00', '14:00')]


def test_ohne_fenster_wird_nichts_gekuerzt():
    """Die Gegenprobe, die den Test darueber erst aussagekraeftig macht.

    Dieselben Baender, aber drei uneingeschraenkte Leute: es darf kein
    Zuschnitt entstehen. Ohne diesen Test waere eine Umsetzung gruen, die
    immer kuerzt.
    """
    bloecke = plan_day(
        [band('06:00', '14:00', 3)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1), mitarbeiter(2), mitarbeiter(3)],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '14:00')] * 3


def test_zugeschnittener_block_behaelt_seine_vorlage():
    """Name und Farbe der Schichtart bleiben - gekuerzt ist nicht namenlos."""
    bloecke = plan_day(
        [band('06:00', '14:00', 2)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1), mitarbeiter(2, [fenster(DIENSTAG, '08:00', '14:00')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert all(b['shift_type_id'] == 1 for b in bloecke)


def test_zuschnitt_unter_mindestlaenge_entsteht_nicht():
    """Ein Fenster von 13:00-14:00 ergaebe einen Einstundenblock.

    Der bleibt aus; der Bedarf wird stattdessen als Deckungsluecke gemeldet.
    Sonst entstuenden Schnipsel, die niemand arbeiten will.
    """
    bloecke = plan_day(
        [band('06:00', '14:00', 2)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1), mitarbeiter(2, [fenster(DIENSTAG, '13:00', '14:00')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '14:00')] * 2


def test_abgelaufenes_fenster_loest_keinen_zuschnitt_aus():
    bloecke = plan_day(
        [band('06:00', '14:00', 1)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1, [fenster(DIENSTAG, '08:00', '14:00', valid_until='2026-08-01')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '14:00')]


def test_fenster_an_einem_anderen_wochentag_loest_keinen_zuschnitt_aus():
    bloecke = plan_day(
        [band('06:00', '14:00', 1)],
        [vorlage(1, '06:00', '14:00')],
        [mitarbeiter(1, [fenster(DIENSTAG + 1, '08:00', '14:00')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '14:00')]


def test_langer_rest_bleibt_als_eigener_block_stehen():
    """Wird ein Block gekuerzt, faellt der ungedeckte Teil nicht einfach weg.

    Bedarf 06:00-16:00 fuer eine Person, deren einziges Fenster 06:00-12:00
    ist: der Block wird auf das Fenster gekuerzt, und die vier Stunden danach
    bleiben als eigener Block bestehen - lang genug, dass jemand anderes sie
    uebernehmen koennte, und andernfalls als Luecke sichtbar.

    Die zehn Stunden sind bewusst gewaehlt: mehr, und MAX_BLOCK_MINUTES teilte
    den Ausgangsblock schon vor dem Zuschnitt, womit der Test zwei Dinge auf
    einmal pruefte.
    """
    bloecke = plan_day(
        [band('06:00', '16:00', 1)],
        [],
        [mitarbeiter(1, [fenster(DIENSTAG, '06:00', '12:00')])],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('06:00', '12:00'), ('12:00', '16:00')]


def test_geteilter_dienst_wird_nicht_wegen_der_tagesgrenze_zugeschnitten():
    """max_daily_hours bindet schon in Stufe 1.

    Eine Person mit zwei Fenstern und einer Tagesgrenze von 6 Stunden kann
    nicht beide Vier-Stunden-Bloecke tragen. Stufe 1 darf daraus trotzdem
    keinen Zuschnitt machen - die Bloecke sind bereits fensterkonform, es
    fehlt schlicht eine zweite Person.
    """
    bloecke = plan_day(
        [band('08:00', '12:00', 1), band('16:00', '20:00', 1)],
        [vorlage(1, '08:00', '12:00'), vorlage(2, '16:00', '20:00')],
        [mitarbeiter(1, [fenster(DIENSTAG, '08:00', '12:00'),
                         fenster(DIENSTAG, '16:00', '20:00')], max_daily_hours=6)],
        EIN_DIENSTAG, DIENSTAG,
    )

    assert zeiten(bloecke) == [('08:00', '12:00'), ('16:00', '20:00')]


def test_plan_day_ist_deterministisch():
    def lauf(kandidaten):
        return zeiten(plan_day(
            [band('06:00', '14:00', 3)],
            [vorlage(1, '06:00', '14:00')],
            kandidaten, EIN_DIENSTAG, DIENSTAG,
        ))

    kandidaten = [mitarbeiter(1), mitarbeiter(2),
                  mitarbeiter(3, [fenster(DIENSTAG, '08:00', '14:00')])]

    assert lauf(kandidaten) == lauf(list(reversed(kandidaten)))


def test_ohne_kandidaten_bleiben_die_bloecke_wie_sie_sind():
    """Kein Kandidat heisst nicht: kein Block. Die Bloecke stehen und werden
    als Luecke gemeldet."""
    bloecke = plan_day([band('06:00', '14:00', 2)], [vorlage(1, '06:00', '14:00')],
                       [], EIN_DIENSTAG, DIENSTAG)

    assert zeiten(bloecke) == [('06:00', '14:00')] * 2


def test_vorlage_ohne_zeiten_wird_uebergangen():
    """generate_schedule() sagt "HH:MM or None" fuer Schichtarten zu.

    Ueber die Anwendung kommt so eine Vorlage nie an - die Spalten sind
    NOT NULL -, aber ein Aufrufer, der sich an die zugesagte Schnittstelle
    haelt, darf keinen Absturz bekommen. Fuer die Blockplanung ist eine
    Vorlage ohne Zeiten schlicht keine.
    """
    bloecke = cover_demand(
        [band('08:00', '16:00', 1)],
        [{'id': 1, 'start_time': None, 'end_time': None},
         vorlage(2, '08:00', '16:00')],
    )

    assert bloecke == [{'shift_type_id': 2, 'start_time': '08:00', 'end_time': '16:00'}]
