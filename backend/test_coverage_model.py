"""Bedarfskurve als reine Funktion.

coverage_curve(), bands_overlap(), first_overlapping_pair() und band_within()
sind reine Funktionen ohne Datenbank und ohne Flask - reine Aufrufe, keine
Fixtures noetig.
"""

from coverage_model import (
    band_within, bands_overlap, coverage_curve, coverage_gaps, first_overlapping_pair,
    trim_band_to_hours,
)


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


def test_band_within_erlaubt_nachtband_bei_ganztaegiger_oeffnung():
    """22:00-06:00 passt in die Oeffnungszeit 00:00-00:00 (ganztags offen).

    Das Band ist [1320, 1800), die Oeffnungszeit [0, 1440) - auf einer geraden
    Achse verglichen faellt das Band hinten heraus, obwohl der Betrieb rund um
    die Uhr offen ist. Genau diese Kombination setzt Migration 0006 (Standard-
    Oeffnungszeit) mit den Baendern zusammen, die Migration 0007 aus
    Nachtschichten ableitet.

    Gegenprobe im selben Test, sonst belegt er nur, dass die Pruefung schwaecher
    geworden ist: bei einer echten Oeffnungszeit 08:00-18:00 bleibt 07:00-12:00
    abgelehnt, und ein Nachtband erst recht.
    """
    nachtband = {'start_time': '22:00', 'end_time': '06:00'}
    assert band_within(nachtband, '00:00', '00:00') is True

    assert band_within({'start_time': '07:00', 'end_time': '12:00'}, '08:00', '18:00') is False
    assert band_within(nachtband, '08:00', '18:00') is False

    # Der Ring loest nur die Mitternachtsueberschreitung auf, er dehnt das
    # Fenster nicht: 20:00-02:00 liegt in 18:00-06:00, 17:00-02:00 nicht.
    assert band_within({'start_time': '20:00', 'end_time': '02:00'}, '18:00', '06:00') is True
    assert band_within({'start_time': '17:00', 'end_time': '02:00'}, '18:00', '06:00') is False


def test_trim_band_to_hours_schneidet_auf_das_oeffnungsfenster_zu():
    """Ein Band ausserhalb der Oeffnungszeit wird beschnitten, nicht gemeldet wie es ist.

    Drei Faelle, weil nur ihre Kombination die Funktion festlegt: teilweise
    ausserhalb -> beschnitten, vollstaendig ausserhalb -> None, vollstaendig
    innerhalb -> unveraendert (dasselbe Objekt, kein neu gebautes mit denselben
    Zeiten). required_count muss den Schnitt ueberleben, sonst waere die
    zugeschnittene Luecke betragsmaessig falsch.
    """
    band = {'start_time': '06:00', 'end_time': '18:00', 'required_count': 3}

    assert trim_band_to_hours(band, '09:00', '12:00') == {
        'start_time': '09:00', 'end_time': '12:00', 'required_count': 3,
    }
    assert trim_band_to_hours(band, '19:00', '23:00') is None
    assert trim_band_to_hours(band, '00:00', '00:00') is band

    # Ueber Mitternacht: das Nachtband ragt in den geschlossenen Teil des Tages,
    # uebrig bleibt sein Stueck innerhalb der Oeffnungszeit - hier der Morgen.
    nachtband = {'start_time': '22:00', 'end_time': '06:00', 'required_count': 2}
    assert trim_band_to_hours(nachtband, '00:00', '12:00') == {
        'start_time': '00:00', 'end_time': '06:00', 'required_count': 2,
    }


# ---------- coverage_gaps(): Deckungsluecken als reine Funktion (Task 6) ----------

def test_volle_deckung_erzeugt_keine_luecke():
    """Bedarf 3 von 08:00-16:00, drei Intervalle decken genau das ab -> keine Luecke."""
    baender = [{'start_time': '08:00', 'end_time': '16:00', 'required_count': 3}]
    intervalle = [
        {'start_time': '08:00', 'end_time': '16:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
    ]

    assert coverage_gaps(baender, intervalle) == []


def test_fehlende_person_erzeugt_eine_luecke_mit_der_richtigen_zahl():
    """Bedarf 3 von 12:00-17:00, zwei Personen da -> eine Luecke, missing = 1."""
    baender = [{'start_time': '12:00', 'end_time': '17:00', 'required_count': 3}]
    intervalle = [
        {'start_time': '12:00', 'end_time': '17:00'},
        {'start_time': '12:00', 'end_time': '17:00'},
    ]

    assert coverage_gaps(baender, intervalle) == [
        {'start_time': '12:00', 'end_time': '17:00', 'missing': 1},
    ]


def test_teilweise_deckung_erzeugt_nur_den_ungedeckten_abschnitt():
    """Bedarf 08:00-16:00 fuer 2, eine Person 08:00-12:00, eine 08:00-16:00
    -> Luecke nur 12:00-16:00 mit missing = 1."""
    baender = [{'start_time': '08:00', 'end_time': '16:00', 'required_count': 2}]
    intervalle = [
        {'start_time': '08:00', 'end_time': '12:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
    ]

    assert coverage_gaps(baender, intervalle) == [
        {'start_time': '12:00', 'end_time': '16:00', 'missing': 1},
    ]


def test_benachbarte_luecken_mit_gleicher_zahl_werden_zusammengefasst():
    """Zwei anschliessende Baender mit je missing = 1 ergeben EINE Luecke, nicht zwei.

    Bedarf 08:00-12:00 und 12:00-16:00, je required_count 2, aber durchgehend
    nur eine Person da - ohne Zusammenfassung kaemen zwei benachbarte
    Eintraege mit derselben Zahl statt eines.
    """
    baender = [
        {'start_time': '08:00', 'end_time': '12:00', 'required_count': 2},
        {'start_time': '12:00', 'end_time': '16:00', 'required_count': 2},
    ]
    intervalle = [{'start_time': '08:00', 'end_time': '16:00'}]

    assert coverage_gaps(baender, intervalle) == [
        {'start_time': '08:00', 'end_time': '16:00', 'missing': 1},
    ]


def test_uebererfuellung_erzeugt_keine_luecke():
    """Vier Personen bei Bedarf 3 - kein Eintrag, und schon gar kein negativer."""
    baender = [{'start_time': '08:00', 'end_time': '16:00', 'required_count': 3}]
    intervalle = [
        {'start_time': '08:00', 'end_time': '16:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
        {'start_time': '08:00', 'end_time': '16:00'},
    ]

    assert coverage_gaps(baender, intervalle) == []
