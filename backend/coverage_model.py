"""Bedarfskurve aus Schichtarten ableiten.

Reine Rechenlogik ohne Datenbank und ohne Flask: aus den Schichtarten eines
einzelnen Wochentags (je mit Start, Ende und benoetigter Anzahl) wird eine
ueberlappungsfreie Bedarfskurve. Datei heisst bewusst nicht coverage.py -
das PyPI-Paket coverage (Abhaengigkeit von pytest-cov) wuerde sonst von
einer gleichnamigen lokalen Datei verdeckt.

Die Minutenachse und ihre Mitternachtsregel kommen aus scheduler.py und
werden hier nur wiederverwendet, nicht zweites Mal implementiert. Das gilt
seit dem Fix von window_contains_shift() auch fuer die beiden Ring-Primitiven
_closed_range() und _ranges_overlap(): sie leben jetzt in scheduler.py, weil
dort die Mitternachtskonvention ohnehin zu Hause ist (time_to_minutes(),
_time_range_minutes()), und werden hier nur importiert - genau eine Fassung,
nicht zwei.
"""

from scheduler import _closed_range, _ranges_overlap, _time_range_minutes


def _band_range(start_time, end_time):
    """Start- und Endminute eines Bandes, mit Mitternachtsregel.

    Duenner Namens-Wrapper um scheduler._time_range_minutes() - "Band" ist die
    Domaenensprache dieser Datei (Bedarfsbaender), die Rechenlogik selbst
    bleibt eine einzige Fassung in scheduler.py. end_time <= start_time
    bedeutet Ueberschreitung nach Mitternacht - dieselbe Konvention wie in
    scheduler.window_contains_shift().
    """
    return _time_range_minutes(start_time, end_time)


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

    Mitternacht: die Grenzen werden ueber _band_range() gebildet und liegen
    deshalb auf einer Achse, die ueber 1440 hinausreicht - eine Nachtschicht
    22:00-06:00 wird zu [1320, 1800). Die Funktion erzeugt also nachweislich
    Baender, die ueber Mitternacht gehen, und gibt sie als "22:00"/"06:00"
    zurueck (_minutes_to_time() rechnet modulo 1440). Jede Weiterverarbeitung
    muss ein solches Band vertragen: band_within() prueft die Enthaltung
    deshalb auf dem Ring, nicht auf einer geraden Achse. Ein Band ist nie
    laenger als 1440 Minuten, weil keine einzelne Schichtart es sein kann.
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
        for j in range(i + 1, len(ranges)):
            if _ranges_overlap(ranges[i], ranges[j]):
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

    Geprueft ueber die Gegenmenge: das Band liegt genau dann innerhalb der
    Oeffnungszeit, wenn es die SCHLIESSZEIT nicht beruehrt. Der direkte
    Vergleich "Fensterstart <= Bandstart und Bandende <= Fensterende" (so
    machte es diese Funktion frueher, und so machte es scheduler.
    window_contains_shift() bis zu dessen Fix in derselben Etappe wie dieser
    Kommentar) kann das nicht leisten, sobald das Band ueber Mitternacht
    geht: eine Nachtschicht 22:00-06:00 ist [1320, 1800), eine ganztaegige
    Oeffnungszeit 00:00-00:00 ist [0, 1440), und 1800 <= 1440 ist falsch -
    obwohl der Betrieb rund um die Uhr offen ist und das Band offensichtlich
    hineinpasst. Ueber die Schliesszeit gelesen loest sich das auf: sie ist
    dort leer, und ein leerer Bereich kann nichts schneiden.

    Es reicht nicht, das Band um +-1440 zu verschieben und weiter gerade zu
    vergleichen - keine der drei Lagen von [1320, 1800) liegt in [0, 1440),
    weil das Band die Fensterkante ueberschreitet statt neben ihr zu liegen.
    Die Ringnatur steckt im Fenster, nicht im Band.

    Die Verschiebung selbst macht _ranges_overlap(), dieselbe Funktion, die
    first_overlapping_pair() benutzt - keine zweite Fassung davon.

    Erlaubt wird dadurch nichts, was vorher zu Recht verboten war: bei
    Oeffnungszeit 08:00-18:00 reicht die Schliesszeit von 1080 bis 1920, und
    ein Band 07:00-12:00 ([420, 720)) schneidet ihre um 1440 zurueckversetzte
    Kopie [-360, 480) - es bleibt abgelehnt. Der Ring greift nur da, wo er
    eine Mitternachtsueberschreitung aufloest.
    """
    closed_start, closed_end = _closed_range(open_time, close_time)
    if closed_end <= closed_start:
        return True

    return not _ranges_overlap(
        _band_range(band['start_time'], band['end_time']),
        (closed_start, closed_end),
    )


def trim_band_to_hours(band, open_time, close_time):
    """Das Band auf die Oeffnungszeit zugeschnitten, oder None wenn nichts uebrig bleibt.

    Sicherheitsnetz fuer Altbestand: ein Band kann aelter sein als die
    Oeffnungszeit, unter der es heute gelesen wird - Migration 0007 leitet
    Baender aus den Schichtarten ab und schreibt sie an der API vorbei, und
    jede Datenbank, die vor der Gegenpruefung in replace_business_hours()
    bearbeitet wurde, kann ebenfalls Baender ausserhalb der Oeffnungszeit
    enthalten. Solche Baender duerfen keine Deckungsluecke fuer einen
    geschlossenen Betrieb melden.

    Passt das Band ohnehin ganz hinein (band_within()), kommt es unveraendert
    zurueck - insbesondere bleibt ein Nachtband unter einer ganztaegigen
    Oeffnungszeit unangetastet. Sonst wird der Schnitt mit dem Fenster
    gebildet, wieder mit denselben +-1440-Lagen wie ueberall sonst in dieser
    Datei; von mehreren moeglichen Lagen gewinnt die mit dem groessten
    Ueberlapp. Zerfaellt der Schnitt theoretisch in zwei Stuecke (nur bei
    einem Fenster laenger als 22 Stunden zusammen mit einem langen Nachtband
    ueberhaupt erreichbar), wird bewusst nur das groessere gemeldet: zu wenig
    Bedarf zu melden ist die harmlose Richtung, zu viel waere genau der
    Fehler, den diese Funktion behebt.

    required_count und alles Weitere am Band bleiben erhalten, nur die Zeiten
    werden ersetzt.
    """
    if band_within(band, open_time, close_time):
        return band

    start, end = _band_range(band['start_time'], band['end_time'])
    open_min, close_min = _band_range(open_time, close_time)

    best = None
    for shift in (-24 * 60, 0, 24 * 60):
        lo = max(start + shift, open_min)
        hi = min(end + shift, close_min)
        if hi > lo and (best is None or hi - lo > best[1] - best[0]):
            best = (lo, hi)

    if best is None:
        return None

    return {
        **band,
        'start_time': _minutes_to_time(best[0]),
        'end_time': _minutes_to_time(best[1]),
    }


def coverage_gaps(bands, covered_intervals):
    """Deckungsluecken eines einzelnen Datums: wo der Bedarf die tatsaechliche Deckung uebersteigt.

    Reine Rechenlogik, kein Datenbankzugriff - `bands` (Bedarfsbaender des
    Wochentags, je mit start_time/end_time/required_count) und
    `covered_intervals` (die Zeiten, die tatsaechlich von jemandem abgedeckt
    sind, je nur start_time/end_time) werden fertig uebergeben. Der Aufrufer
    entscheidet, was ueberhaupt ein Intervall ist - eine Zuweisung ohne
    Mitarbeiter oder eine durch Abwesenheit freigewordene gehoert dort schon
    nicht mehr in die Liste.

    Ereignispunkt-Verfahren wie coverage_curve(): alle Grenzen von Baendern
    und Intervallen zusammen sortiert, jedes Teilstueck bekommt seinen Bedarf
    (Summe der required_count der Baender, die es vollstaendig ueberdecken -
    Baender desselben Wochentags ueberlappen sich nicht, siehe
    replace_coverage_requirements(), es kann also hoechstens eines sein) und
    seine Deckung (Anzahl Intervalle, die es vollstaendig ueberdecken).
    missing = Bedarf minus Deckung; Teilstuecke ohne Bedarf oder mit
    Deckung >= Bedarf liefern keinen Eintrag - insbesondere nie einen
    negativen. Benachbarte Teilstuecke mit gleichem missing werden
    anschliessend zu einer Luecke zusammengefasst, genau wie coverage_curve()
    gleiche Nachbarn verschmilzt.
    """
    if not bands:
        return []

    band_ranges = [
        (*_band_range(band['start_time'], band['end_time']), band['required_count'])
        for band in bands
    ]
    interval_ranges = [
        _band_range(interval['start_time'], interval['end_time'])
        for interval in covered_intervals
    ]

    boundaries = sorted(
        {start for start, _, _ in band_ranges} | {end for _, end, _ in band_ranges}
        | {start for start, _ in interval_ranges} | {end for _, end in interval_ranges}
    )

    raw_gaps = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        required = sum(count for start, end, count in band_ranges if start <= lo and hi <= end)
        if required == 0:
            continue
        covered = sum(1 for start, end in interval_ranges if start <= lo and hi <= end)
        missing = required - covered
        if missing > 0:
            raw_gaps.append((lo, hi, missing))

    merged = []
    for lo, hi, missing in raw_gaps:
        if merged and merged[-1][1] == lo and merged[-1][2] == missing:
            prev_lo, _, prev_missing = merged[-1]
            merged[-1] = (prev_lo, hi, prev_missing)
        else:
            merged.append((lo, hi, missing))

    return [
        {
            'start_time': _minutes_to_time(lo),
            'end_time': _minutes_to_time(hi),
            'missing': missing,
        }
        for lo, hi, missing in merged
    ]
