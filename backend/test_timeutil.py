"""Monatsgrenzen und lokale Zeitzone.

month_bounds() ist bewusst eine reine Funktion: so laesst sich das Verhalten
an Monatsraendern mit festen Daten pruefen, ohne die Uhr zu manipulieren.
"""

from datetime import date


def test_monatsgrenzen_eines_langen_monats():
    from timeutil import month_bounds

    assert month_bounds(date(2026, 3, 17)) == ('2026-03-01', '2026-03-31')


def test_monatsgrenzen_eines_kurzen_monats():
    from timeutil import month_bounds

    assert month_bounds(date(2026, 2, 1)) == ('2026-02-01', '2026-02-28')


def test_monatsgrenzen_im_schaltjahr():
    from timeutil import month_bounds

    assert month_bounds(date(2028, 2, 29)) == ('2028-02-01', '2028-02-29')


def test_lokales_datum_folgt_der_konfigurierten_zeitzone(monkeypatch):
    """Pacific/Kiritimati (UTC+14) und Pacific/Niue (UTC-11) liegen konstant 25
    Stunden auseinander - beide Zonen sind ganzjaehrig ohne Sommerzeit fest
    verschoben. Eine Verschiebung von mehr als 24 Stunden bedeutet: zu jedem
    beliebigen Weltzeitpunkt liegt Kiritimati mindestens einen ganzen
    Kalendertag vor Niue (mal einen, mal zwei, abhaengig von der Uhrzeit -
    aber nie null). Der Test haengt deshalb trotz echtem datetime.now() nicht
    vom Zeitpunkt der Ausfuehrung ab: mit `python -c` ueber ein Jahr in
    15-Minuten-Schritten durchgerechnet bleibt die Differenz immer 1 oder 2
    Tage, nie 0. Ein regressiertes today_local(), das APP_TIMEZONE ignoriert,
    wuerde dagegen fuer beide Aufrufe denselben Wert liefern und den Test
    zuverlaessig scheitern lassen.
    """
    import sys
    monkeypatch.setenv('APP_TIMEZONE', 'Pacific/Kiritimati')
    sys.modules.pop('timeutil', None)
    import timeutil
    kiritimati = timeutil.today_local()

    monkeypatch.setenv('APP_TIMEZONE', 'Pacific/Niue')
    sys.modules.pop('timeutil', None)
    import timeutil as timeutil_niue
    niue = timeutil_niue.today_local()

    assert kiritimati != niue


def test_unbekannte_zeitzone_faellt_auf_berlin_zurueck(monkeypatch):
    import sys
    monkeypatch.setenv('APP_TIMEZONE', 'Nicht/Existent')
    sys.modules.pop('timeutil', None)
    import timeutil

    assert timeutil.timezone_name() == 'Europe/Berlin'
