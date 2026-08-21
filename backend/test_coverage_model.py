"""Bedarfskurve als reine Funktion.

coverage_curve(), bands_overlap(), first_overlapping_pair() und band_within()
sind reine Funktionen ohne Datenbank und ohne Flask - reine Aufrufe, keine
Fixtures noetig.
"""

from coverage_model import band_within, bands_overlap, coverage_curve, first_overlapping_pair


def test_zwei_anschliessende_schichten_ergeben_zwei_baender():
    """Der Normalfall: Frueh 06:00-14:00 mit 2, Spaet 14:00-22:00 mit 3."""
    assert coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 3},
    ]) == [
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 3},
    ]


def test_ueberlappende_schichten_werden_summiert():
    """Frueh 06:00-14:00 mit 2 und Zwischendienst 10:00-18:00 mit 1.

    Erwartet drei Baender: 06-10 zwei, 10-14 drei, 14-18 eins. Das ist der Test,
    der belegt, dass die Kurve summiert statt nebeneinanderzustellen.
    """
    assert coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '10:00', 'end_time': '18:00', 'required_count': 1},
    ]) == [
        {'start_time': '06:00', 'end_time': '10:00', 'required_count': 2},
        {'start_time': '10:00', 'end_time': '14:00', 'required_count': 3},
        {'start_time': '14:00', 'end_time': '18:00', 'required_count': 1},
    ]


def test_gleiche_summe_wird_zu_einem_band_zusammengefasst():
    """Zwei anschliessende Schichten mit gleichem Bedarf ergeben EIN Band, nicht zwei.

    Ohne Zusammenfassung waere die Ausgabe zwar nicht falsch, aber die
    Ueberlappungspruefung spaeter arbeitet auf dieser Form - und ein Editor, der
    zwei Baender zeigt, wo eines gemeint ist, verwirrt.
    """
    assert coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 2},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 2},
    ]) == [
        {'start_time': '06:00', 'end_time': '22:00', 'required_count': 2},
    ]


def test_nachtschicht_erzeugt_ein_band_ueber_mitternacht():
    """22:00-06:00 mit 2 ergibt genau ein Band 22:00-06:00, nicht zwei Stuecke."""
    assert coverage_curve([
        {'start_time': '22:00', 'end_time': '06:00', 'required_count': 2},
    ]) == [
        {'start_time': '22:00', 'end_time': '06:00', 'required_count': 2},
    ]


def test_bedarf_null_erzeugt_kein_band():
    """Eine Schichtart, die an diesem Wochentag niemanden braucht, taucht nicht auf."""
    assert coverage_curve([
        {'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
        {'start_time': '12:00', 'end_time': '16:00', 'required_count': 0},
    ]) == [
        {'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
    ]


def test_leere_eingabe_ergibt_leere_kurve():
    assert coverage_curve([]) == []


def test_bands_overlap_erkennt_echte_ueberschneidung():
    """08:00-12:00 und 11:00-15:00 ueberlappen. Gegenprobe: 08:00-12:00 und
    12:00-16:00 beruehren sich nur und ueberlappen NICHT - die Grenze ist
    halboffen [start, end)."""
    assert bands_overlap([
        {'start_time': '08:00', 'end_time': '12:00'},
        {'start_time': '11:00', 'end_time': '15:00'},
    ]) is True

    assert bands_overlap([
        {'start_time': '08:00', 'end_time': '12:00'},
        {'start_time': '12:00', 'end_time': '16:00'},
    ]) is False


def test_bands_overlap_erkennt_ueberschneidung_ueber_mitternacht():
    """22:00-06:00 und 05:00-08:00 ueberlappen auf der Minutenachse."""
    assert bands_overlap([
        {'start_time': '22:00', 'end_time': '06:00'},
        {'start_time': '05:00', 'end_time': '08:00'},
    ]) is True


def test_first_overlapping_pair_liefert_das_kollidierende_paar():
    """Drei Baender, von denen sich zwei ueberschneiden - genau dieses Paar kommt zurueck.

    Das erste Band (08-12) ueberlappt keines der beiden anderen und darf nicht
    Teil des gemeldeten Paares sein - sonst waere der Test auch gruen, wenn
    einfach die ersten zwei Eintraege der Liste zurueckgegeben wuerden.
    """
    frueh = {'start_time': '08:00', 'end_time': '10:00'}
    mittag = {'start_time': '11:00', 'end_time': '15:00'}
    spaet = {'start_time': '13:00', 'end_time': '17:00'}

    paar = first_overlapping_pair([frueh, mittag, spaet])

    assert paar == (mittag, spaet)


def test_first_overlapping_pair_ist_none_ohne_ueberschneidung():
    assert first_overlapping_pair([
        {'start_time': '08:00', 'end_time': '12:00'},
        {'start_time': '12:00', 'end_time': '16:00'},
    ]) is None


def test_band_within_prueft_vollstaendige_enthaltung():
    """08:00-12:00 liegt in 08:00-18:00. 07:00-12:00 nicht. Gegenprobe noetig,
    sonst prueft der Test nur, dass irgendetwas True zurueckgibt."""
    band = {'start_time': '08:00', 'end_time': '12:00'}
    assert band_within(band, '08:00', '18:00') is True

    band_ausserhalb = {'start_time': '07:00', 'end_time': '12:00'}
    assert band_within(band_ausserhalb, '08:00', '18:00') is False
