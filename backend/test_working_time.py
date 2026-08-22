"""Arbeitszeit und Ruhepause: die Rechnung hinter Paragraph 2 Abs. 1 und Paragraph 4 ArbZG.

Reine Rechentests ohne Datenbank. Die interessanten Faelle sind die Kanten -
und die liegen nicht dort, wo das Gesetz seine Zahlen nennt.
"""

import pytest

from scheduler import legal_break_minutes, net_working_minutes

STUNDE = 60


@pytest.mark.parametrize('spanne, erwartet', [
    (4 * STUNDE, 0),
    (6 * STUNDE, 0),            # genau sechs Stunden sind NICHT "mehr als sechs"
    (6 * STUNDE + 1, 30),
    (7 * STUNDE, 30),
    (9 * STUNDE, 30),
    (9 * STUNDE + 30, 30),      # 9:30 minus 30 Min = genau 9:00 Arbeitszeit
    (9 * STUNDE + 31, 45),      # 9:31 minus 30 Min waeren 9:01 - zu viel fuer 30
    (12 * STUNDE, 45),
])
def test_gesetzliche_mindestpause(spanne, erwartet):
    assert legal_break_minutes(spanne) == erwartet


def test_die_kante_liegt_bei_neuneinhalb_stunden_nicht_bei_neun():
    """Der Fall, an dem eine naive Umsetzung falsch liegt.

    Wer die Schwelle des Gesetzes (mehr als neun Stunden) direkt auf die
    Spanne anwendet, springt bei 9:01 auf 45 Minuten. Richtig ist 9:31: bei
    9:30 Spanne bleiben nach 30 Minuten Pause genau neun Stunden Arbeitszeit,
    und neun Stunden sind nicht "mehr als neun".
    """
    assert legal_break_minutes(9 * STUNDE + 1) == 30
    assert legal_break_minutes(9 * STUNDE + 30) == 30
    assert legal_break_minutes(9 * STUNDE + 31) == 45


def _gefordert(arbeitszeit):
    """Paragraph 4 woertlich, angewandt auf eine bekannte Arbeitszeit."""
    if arbeitszeit <= 6 * STUNDE:
        return 0
    if arbeitszeit <= 9 * STUNDE:
        return 30
    return 45


def test_die_zurueckgegebene_pause_ist_fuer_ihr_eigenes_ergebnis_ausreichend():
    """Die Eigenschaft, aus der sich die Schwellen ueberhaupt ergeben.

    Diskriminierend gegenueber jeder fest verdrahteten Tabelle: geprueft wird
    nicht, dass bestimmte Zahlen herauskommen, sondern dass das Ergebnis die
    Bedingung erfuellt, aus der es abgeleitet ist.
    """
    for spanne in range(0, 16 * STUNDE + 1):
        pause = legal_break_minutes(spanne)
        assert pause >= _gefordert(spanne - pause), (spanne, pause)


def test_kleinere_pause_wuerde_nicht_reichen():
    """Gegenprobe: die zurueckgegebene Pause ist nicht nur ausreichend, sondern
    auch die kleinste ausreichende.

    Ohne diesen Test waere ein konstantes 45 fuer alles ebenfalls gruen.
    """
    for spanne in range(1, 16 * STUNDE + 1):
        pause = legal_break_minutes(spanne)
        if pause == 0:
            continue
        kleiner = 0 if pause == 30 else 30
        assert kleiner < _gefordert(spanne - kleiner), (spanne, pause, kleiner)


def test_netto_zieht_die_gesetzliche_pause_ab_wenn_keine_gesetzt_ist():
    assert net_working_minutes(8 * STUNDE, None) == 8 * STUNDE - 30


def test_netto_nimmt_die_gesetzte_pause_auch_wenn_sie_kleiner_ist():
    """HR darf weniger eintragen - dann wird auch weniger abgezogen.

    Gewarnt wird darueber an anderer Stelle (constraint_warnings), gerechnet
    wird hier mit dem, was dasteht.
    """
    assert net_working_minutes(8 * STUNDE, 0) == 8 * STUNDE
    assert net_working_minutes(8 * STUNDE, 60) == 7 * STUNDE


def test_netto_ohne_bekannte_dauer_bleibt_unbekannt():
    """Rueckwaertskompatibel zu Aufrufern, die nur mit Schichtzahlen arbeiten -
    dieselbe Haltung wie bei duration_minutes in build_slots()."""
    assert net_working_minutes(None, None) is None
    assert net_working_minutes(None, 30) is None


def test_netto_wird_nicht_negativ():
    """Eine Pause laenger als der Block ist Unsinn, darf aber keine negative
    Arbeitszeit erzeugen - die wuerde sich durch die Wochensumme fressen."""
    assert net_working_minutes(2 * STUNDE, 180) == 0


# ---------- Der Achtstundenschnitt (Paragraph 3 Satz 2 ArbZG, Etappe 5c) ----------


from datetime import date

from scheduler import (
    AVERAGE_REFERENCE_DAYS, MAX_AVERAGE_DAILY_HOURS,
    average_window, working_days_in, exceeds_average,
)


def test_das_fenster_umfasst_24_wochen_und_endet_am_letzten_des_monats():
    beginn, ende = average_window(2026, 9)

    assert ende == date(2026, 9, 30)
    assert (ende - beginn).days + 1 == AVERAGE_REFERENCE_DAYS
    assert AVERAGE_REFERENCE_DAYS == 24 * 7


def test_werktage_sind_montag_bis_samstag():
    """Paragraph 3 rechnet je Werktag. Sonntage sind keine.

    Eine volle Woche hat sechs Werktage, 24 Wochen also genau 144.
    """
    assert working_days_in(date(2026, 9, 7), date(2026, 9, 13)) == 6
    assert working_days_in(*average_window(2026, 9)) == 144


def test_ein_einzelner_sonntag_zaehlt_nicht():
    """Der 06.09.2026 ist ein Sonntag."""
    assert working_days_in(date(2026, 9, 6), date(2026, 9, 6)) == 0
    assert working_days_in(date(2026, 9, 7), date(2026, 9, 7)) == 1


def test_genau_an_der_grenze_wird_nicht_gemeldet():
    """144 Werktage mal acht Stunden sind 69120 Minuten - und "nicht
    ueberschreiten" heisst, dass genau dieser Wert noch geht."""
    grenze = 144 * MAX_AVERAGE_DAILY_HOURS * 60

    assert exceeds_average(grenze, 144) is False
    assert exceeds_average(grenze + 1, 144) is True


def test_ohne_werktage_wird_nichts_gemeldet():
    """Ein leeres Fenster kann nichts ueberschreiten - und eine Division durch
    null darf es hier auch nicht geben."""
    assert exceeds_average(0, 0) is False
    assert exceeds_average(600, 0) is False
