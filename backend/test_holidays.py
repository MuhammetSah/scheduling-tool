"""Der Feiertagskalender.

Paragraph 9 ArbZG verbietet Feiertagsarbeit, nennt aber keine Feiertage - er
benutzt den Begriff und ueberlaesst die Fuellung dem Landesrecht. Der Kalender
ist deshalb eine Tabelle je Bundesland.

Geprueft wird jede Zeile dieser Tabelle, und die regionalen als Paar aus einem
Land mit und einem ohne: dass Fronleichnam in Bayern gilt, sagt fuer sich
genommen nichts - erst zusammen damit, dass es in Berlin nicht gilt.
"""

from datetime import date, timedelta

import pytest

from holidays import REGIONS, easter_sunday, holidays_for_year, holidays_in_range


# Bekannte Osterdaten, von aussen geprueft und nicht aus derselben Rechnung
# abgeleitet, die sie absichern sollen.
OSTERN = {
    2024: date(2024, 3, 31),
    2025: date(2025, 4, 20),
    2026: date(2026, 4, 5),
    2027: date(2027, 3, 28),
    2028: date(2028, 4, 16),
    2030: date(2030, 4, 21),
    2038: date(2038, 4, 25),   # spaetestmoegliches Datum
    2285: date(2285, 3, 22),   # frueheestmoegliches Datum
}


@pytest.mark.parametrize('jahr, erwartet', sorted(OSTERN.items()))
def test_ostersonntag(jahr, erwartet):
    assert easter_sunday(jahr) == erwartet


def test_bundesweite_feiertage_gelten_ueberall():
    fest = {'Neujahr', 'Karfreitag', 'Ostermontag', 'Tag der Arbeit',
            'Christi Himmelfahrt', 'Pfingstmontag', 'Tag der Deutschen Einheit',
            '1. Weihnachtstag', '2. Weihnachtstag'}

    for region in REGIONS:
        namen = set(holidays_for_year(2026, region).values())
        assert fest <= namen, (region, fest - namen)


def test_bewegliche_feiertage_liegen_richtig_zu_ostern():
    ostern = OSTERN[2026]
    feiertage = holidays_for_year(2026, 'BY')

    assert feiertage[ostern - timedelta(days=2)] == 'Karfreitag'
    assert feiertage[ostern + timedelta(days=1)] == 'Ostermontag'
    assert feiertage[ostern + timedelta(days=39)] == 'Christi Himmelfahrt'
    assert feiertage[ostern + timedelta(days=50)] == 'Pfingstmontag'
    assert feiertage[ostern + timedelta(days=60)] == 'Fronleichnam'


@pytest.mark.parametrize('name, mit, ohne', [
    ('Heilige Drei Könige', 'BY', 'BE'),
    ('Internationaler Frauentag', 'BE', 'BY'),
    ('Fronleichnam', 'BY', 'BE'),
    ('Mariä Himmelfahrt', 'SL', 'BY'),
    ('Weltkindertag', 'TH', 'SN'),
    ('Reformationstag', 'SN', 'BY'),
    ('Allerheiligen', 'BY', 'BE'),
    ('Buß- und Bettag', 'SN', 'TH'),
    ('Ostersonntag', 'BB', 'BE'),
    ('Pfingstsonntag', 'BB', 'BE'),
])
def test_regionale_feiertage_gelten_nur_wo_sie_gelten(name, mit, ohne):
    """Jede Zeile der Tabelle als Paar.

    Nur "gilt in X" zu pruefen waere auch gruen, wenn der Feiertag ueberall
    stuende - erst das Gegenstueck macht die Aussage.
    """
    assert name in holidays_for_year(2026, mit).values()
    assert name not in holidays_for_year(2026, ohne).values()


@pytest.mark.parametrize('jahr, erwartet', [
    (2024, date(2024, 11, 20)),
    (2025, date(2025, 11, 19)),
    (2026, date(2026, 11, 18)),
    (2027, date(2027, 11, 17)),
    (2028, date(2028, 11, 22)),
])
def test_buss_und_bettag_ist_der_mittwoch_vor_dem_23_november(jahr, erwartet):
    """Die einzige Regel im Kalender, die weder fest noch osterbezogen ist.

    2028 ist der interessante Fall: der 22.11. ist selbst ein Mittwoch, und
    "vor dem 23." schliesst ihn ein.
    """
    feiertage = holidays_for_year(jahr, 'SN')

    assert feiertage[erwartet] == 'Buß- und Bettag'
    assert erwartet.weekday() == 2


def test_ohne_bundesland_kommt_eine_leere_menge():
    """Kein Standardland, weil es keines gibt, das man raten koennte - und
    kein Fehler, weil "noch nicht gewaehlt" ein gueltiger Zustand ist."""
    assert holidays_for_year(2026, None) == {}
    assert holidays_in_range(date(2026, 1, 1), date(2026, 12, 31), None) == {}


def test_unbekanntes_bundesland_ist_ein_fehler():
    """Anders als None: ein Tippfehler soll nicht still zu "keine Feiertage"
    werden."""
    with pytest.raises(ValueError):
        holidays_for_year(2026, 'XX')


def test_der_zeitraum_kann_ueber_den_jahreswechsel_gehen():
    feiertage = holidays_in_range(date(2026, 12, 20), date(2027, 1, 10), 'BY')

    assert feiertage[date(2026, 12, 25)] == '1. Weihnachtstag'
    assert feiertage[date(2027, 1, 1)] == 'Neujahr'
    assert feiertage[date(2027, 1, 6)] == 'Heilige Drei Könige'


def test_der_zeitraum_schneidet_ab():
    feiertage = holidays_in_range(date(2026, 12, 26), date(2026, 12, 31), 'BY')

    assert list(feiertage) == [date(2026, 12, 26)]
