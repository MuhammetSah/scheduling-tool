"""Bedarfskurve aus Schichtarten ableiten.

Reine Rechenlogik ohne Datenbank und ohne Flask: aus den Schichtarten eines
einzelnen Wochentags (je mit Start, Ende und benoetigter Anzahl) wird eine
ueberlappungsfreie Bedarfskurve. Datei heisst bewusst nicht coverage.py -
das PyPI-Paket coverage (Abhaengigkeit von pytest-cov) wuerde sonst von
einer gleichnamigen lokalen Datei verdeckt.

Die Minutenachse und ihre Mitternachtsregel kommen aus scheduler.py und
werden hier nur wiederverwendet, nicht zweites Mal implementiert.
"""

from scheduler import time_to_minutes, window_contains_shift


def _band_range(start_time, end_time):
    """Start- und Endminute einer Schicht, mit Mitternachtsregel.

    end_time <= start_time bedeutet Ueberschreitung nach Mitternacht - dieselbe
    Konvention wie in scheduler.window_contains_shift().
    """
    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)
    if end <= start:
        end += 24 * 60
    return start, end


def _minutes_to_time(minutes):
    """Minute seit Mitternacht zurueck in einen "HH:MM"-String.

    Modulo 1440, weil eine Nachtschicht-Grenze ueber 24:00 hinaus gezaehlt
    wird (z.B. 06:00 des Folgetags als 1800), im Ergebnis aber wieder als
    Uhrzeit des jeweiligen Tages erscheinen soll.
    """
    minutes_of_day = minutes % (24 * 60)
    return f'{minutes_of_day // 60:02d}:{minutes_of_day % 60:02d}'


def coverage_curve(shift_types):
    """Ueberlappungsfreie Bedarfskurve aus den Schichtarten eines Wochentags.

    Ereignispunkt-Verfahren statt Raster: alle Start- und Endminuten der
    Schichtarten werden als Kandidatengrenzen gesammelt und sortiert. Jedes
    Intervall zwischen zwei aufeinanderfolgenden Grenzen bekommt die Summe
    der required_count aller Schichtarten, die es vollstaendig ueberdecken.
    Benachbarte Intervalle mit gleicher Summe werden anschliessend zu einem
    Band verschmolzen, Intervalle mit Summe 0 fallen weg.
    """
    if not shift_types:
        return []

    ranges = [
        (*_band_range(shift['start_time'], shift['end_time']), shift['required_count'])
        for shift in shift_types
    ]

    boundaries = sorted({start for start, _, _ in ranges} | {end for _, end, _ in ranges})

    raw_bands = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        total = sum(count for start, end, count in ranges if start <= lo and hi <= end)
        if total > 0:
            raw_bands.append((lo, hi, total))

    merged = []
    for lo, hi, total in raw_bands:
        if merged and merged[-1][1] == lo and merged[-1][2] == total:
            prev_lo, _, prev_total = merged[-1]
            merged[-1] = (prev_lo, hi, prev_total)
        else:
            merged.append((lo, hi, total))

    return [
        {
            'start_time': _minutes_to_time(lo),
            'end_time': _minutes_to_time(hi),
            'required_count': total,
        }
        for lo, hi, total in merged
    ]


def first_overlapping_pair(bands):
    """Erstes ueberlappende Bandpaar der Liste, oder None wenn keines ueberlappt.

    Dieselbe Minutenachsen-Logik wie bands_overlap() (siehe dort), aber mit dem
    Paar selbst als Ergebnis statt nur True/False: eine brauchbare Fehlermeldung
    fuer HR muss sagen KOENNEN, welche zwei Baender kollidieren, nicht nur DASS
    irgendwo eine Kollision vorliegt. bands_overlap() ist unten auf diese
    Funktion zurueckgefuehrt, damit die Vergleichslogik nur einmal existiert.
    """
    ranges = [_band_range(band['start_time'], band['end_time']) for band in bands]

    for i in range(len(ranges)):
        start_i, end_i = ranges[i]
        for j in range(i + 1, len(ranges)):
            start_j, end_j = ranges[j]
            for shift in (-24 * 60, 0, 24 * 60):
                if start_i < end_j + shift and start_j + shift < end_i:
                    return bands[i], bands[j]

    return None


def bands_overlap(bands):
    """True, wenn sich zwei Baender derselben Liste auf der Minutenachse ueberschneiden.

    Halboffene Grenze [start, end): zwei Baender, die sich nur beruehren
    (Ende des einen = Start des anderen), ueberlappen NICHT. Jedes Band wird
    zusaetzlich einen Zyklus frueher und spaeter verglichen (+-1440 Minuten),
    damit eine Nachtschicht ueber Mitternacht auch mit einem Band am naechsten
    Morgen als ueberlappend erkannt wird.
    """
    return first_overlapping_pair(bands) is not None


def band_within(band, open_time, close_time):
    """Liegt das Band vollstaendig innerhalb von open_time bis close_time?

    Dieselbe Enthaltensein-Regel wie scheduler.window_contains_shift() - hier
    direkt wiederverwendet, damit es nur eine Mitternachtsregel im Projekt
    gibt statt einer zweiten Kopie fuer Baender.
    """
    window = {'start_time': open_time, 'end_time': close_time}
    return window_contains_shift(window, band['start_time'], band['end_time'])
