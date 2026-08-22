"""Gesetzliche Feiertage in Deutschland, je Bundesland.

Reine Rechenlogik ohne Datenbank und ohne Flask, wie coverage_model.py und
block_planner.py.

Paragraph 9 ArbZG verbietet Feiertagsarbeit, nennt aber keine Feiertage - er
benutzt den Begriff und ueberlaesst die Fuellung dem Landesrecht. Deshalb ist
das hier eine Tabelle je Bundesland und keine Liste.

Keine Bibliothek: Ostern sind zwoelf Zeilen Arithmetik, und der Rest ist eine
Tabelle. Das Projekt hat i18n und den Migrations-Runner aus demselben Grund
selbst gebaut - eine sechste Laufzeitabhaengigkeit fuer eine Tabelle waere
schlecht getauscht.

Was hier NICHT steht, sind Feiertage unterhalb der Bundeslandebene:
Fronleichnam gilt in Sachsen und Thueringen nur in ueberwiegend katholischen
Gemeinden, Mariae Himmelfahrt in Bayern ebenso, und das Augsburger
Friedensfest nur in der Stadt Augsburg. Ein Bundesland allein entscheidet das
nicht. Der Kalender ist damit in der nachsichtigen Richtung unvollstaendig -
er kennt einen Feiertag zu wenig, nie einen zu viel. Wer betroffen ist, traegt
den Tag wie bisher als Oeffnungszeit-Ausnahme ein.
"""

from datetime import date, timedelta

REGIONS = {
    'BW': 'Baden-Württemberg',
    'BY': 'Bayern',
    'BE': 'Berlin',
    'BB': 'Brandenburg',
    'HB': 'Bremen',
    'HH': 'Hamburg',
    'HE': 'Hessen',
    'MV': 'Mecklenburg-Vorpommern',
    'NI': 'Niedersachsen',
    'NW': 'Nordrhein-Westfalen',
    'RP': 'Rheinland-Pfalz',
    'SL': 'Saarland',
    'SN': 'Sachsen',
    'ST': 'Sachsen-Anhalt',
    'SH': 'Schleswig-Holstein',
    'TH': 'Thüringen',
}

# (Monat, Tag, Name, Laender). None statt einer Laenderliste heisst bundesweit.
FIXED_HOLIDAYS = (
    (1, 1, 'Neujahr', None),
    (1, 6, 'Heilige Drei Könige', ('BW', 'BY', 'ST')),
    (3, 8, 'Internationaler Frauentag', ('BE', 'MV')),
    (5, 1, 'Tag der Arbeit', None),
    (8, 15, 'Mariä Himmelfahrt', ('SL',)),
    (9, 20, 'Weltkindertag', ('TH',)),
    (10, 3, 'Tag der Deutschen Einheit', None),
    (10, 31, 'Reformationstag', ('BB', 'HB', 'HH', 'MV', 'NI', 'SN', 'ST', 'SH', 'TH')),
    (11, 1, 'Allerheiligen', ('BW', 'BY', 'NW', 'RP', 'SL')),
    (12, 25, '1. Weihnachtstag', None),
    (12, 26, '2. Weihnachtstag', None),
)

# (Abstand zum Ostersonntag in Tagen, Name, Laender).
EASTER_HOLIDAYS = (
    (-2, 'Karfreitag', None),
    (0, 'Ostersonntag', ('BB',)),
    (1, 'Ostermontag', None),
    (39, 'Christi Himmelfahrt', None),
    (49, 'Pfingstsonntag', ('BB',)),
    (50, 'Pfingstmontag', None),
    (60, 'Fronleichnam', ('BW', 'BY', 'HE', 'NW', 'RP', 'SL')),
)


def easter_sunday(year):
    """Ostersonntag nach dem anonymen gregorianischen Algorithmus.

    Auch als Gauss-Butcher-Verfahren bekannt. Gilt fuer den gregorianischen
    Kalender, also fuer jedes Jahr, das dieses Tool je zu sehen bekommt.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def repentance_day(year):
    """Buss- und Bettag: der Mittwoch vor dem 23. November.

    Die einzige Regel im Kalender, die weder fest noch osterbezogen ist. "Vor
    dem 23." schliesst den 22. ein - faellt der selbst auf einen Mittwoch, ist
    er es.
    """
    tag = date(year, 11, 22)
    return tag - timedelta(days=(tag.weekday() - 2) % 7)


def _applies(regions, region):
    return regions is None or region in regions


def holidays_for_year(year, region):
    """{Datum: Name} der gesetzlichen Feiertage eines Jahres in diesem Land.

    `region` None heisst "noch kein Bundesland gewaehlt" und liefert eine leere
    Menge - ein gueltiger Zustand, kein Fehler. Ein *unbekanntes* Land ist
    dagegen sehr wohl ein Fehler: ein Tippfehler soll nicht still zu "keine
    Feiertage" werden.
    """
    if region is None:
        return {}
    if region not in REGIONS:
        raise ValueError(f'unbekanntes Bundesland: {region}')

    feiertage = {}
    for month, day, name, regions in FIXED_HOLIDAYS:
        if _applies(regions, region):
            feiertage[date(year, month, day)] = name

    ostern = easter_sunday(year)
    for offset, name, regions in EASTER_HOLIDAYS:
        if _applies(regions, region):
            feiertage[ostern + timedelta(days=offset)] = name

    if region == 'SN':
        feiertage[repentance_day(year)] = 'Buß- und Bettag'

    return feiertage


def holidays_in_range(first, last, region):
    """{Datum: Name} der Feiertage in einem einschliessenden Zeitraum.

    Ueber Jahresgrenzen hinweg - ein Zeitraum von 24 Wochen (siehe
    scheduler.average_window) faellt regelmaessig in zwei Jahre.
    """
    feiertage = {}
    for year in range(first.year, last.year + 1):
        for tag, name in holidays_for_year(year, region).items():
            if first <= tag <= last:
                feiertage[tag] = name
    return dict(sorted(feiertage.items()))
