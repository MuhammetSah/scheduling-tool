"""Stufe 1 der Planung: aus Bedarf und Vorlagen werden Bloecke.

Reine Rechenlogik ohne Datenbank und ohne Flask, wie coverage_model.py
nebenan. Diese Datei beantwortet genau eine Frage: welche Bloecke muss ein Tag
haben? Wer sie arbeitet, entscheidet der Suchkern in scheduler.py.

Die Minutenachse und ihre Mitternachtsregel kommen aus scheduler.py und
werden hier nur wiederverwendet - dieselbe Linie wie in coverage_model.py,
genau eine Fassung statt drei.

Der Dateiname folgt der Lehre aus Etappe 3 (coverage_model statt coverage):
block_planner statt planner, damit kein installiertes Paket verdeckt werden
kann.
"""

from coverage_model import _minutes_to_time
from scheduler import _time_range_minutes

# Kuerzer als das schneidet Stufe 1 nichts zu - sonst entstehen Schnipsel, die
# niemand arbeiten will. Gilt ausdruecklich NUR fuer den Zuschnitt auf ein
# Arbeitszeitfenster, nicht fuer Bloecke, die direkt aus einem Bedarfsband
# entstehen: ein Zwei-Stunden-Band hat jemand bewusst so gepflegt, und es
# unter Verweis auf diese Konstante fallen zu lassen hiesse eine Eingabe
# anzunehmen und zu verwerfen.
MIN_BLOCK_MINUTES = 180

# Obergrenze fuer einen Block, den Stufe 1 ohne passende Vorlage selbst bildet.
# Zehn Stunden sind nach Paragraph 3 ArbZG das Aeusserste, was jemand an einem
# Werktag arbeiten darf - ein laengerer Block waere per Definition von
# niemandem zu besetzen und wuerde als Ganzes zur Deckungsluecke, statt in
# arbeitbare Stuecke zu zerfallen. Vorlagen bindet diese Grenze nicht: eine
# Vorlage, die jemand so angelegt hat, bleibt wie sie ist.
MAX_BLOCK_MINUTES = 600


def _elementary_profile(bands, extra_boundaries=()):
    """Restbedarf je Elementarintervall, als Liste [start, ende, anzahl].

    Ereignispunkt-Verfahren wie coverage_curve() und coverage_gaps(): alle
    Bandgrenzen - und alle zusaetzlich uebergebenen Grenzen, in der Regel die
    der Vorlagen - werden sortiert, und jedes Stueck zwischen zwei
    aufeinanderfolgenden Grenzen bekommt seinen Bedarf.

    Warum die Vorlagengrenzen mit hineingehoeren: nur wenn eine Vorlage an
    Intervallkanten beginnt und endet, laesst sich ihr Beitrag exakt abziehen.
    Ohne sie muesste ein Band, das eine Vorlage nur halb ueberlappt, ganz oder
    gar nicht verringert werden - beides falsch.

    Baender desselben Wochentags ueberlappen sich nicht (siehe
    replace_coverage_requirements()), auf jedes Stueck passt also hoechstens
    eines. Stuecke ohne Band bekommen 0 und bleiben in der Liste stehen: sie
    sind es, an denen eine zu lange Vorlage unten scheitert.
    """
    ranges = [
        (*_time_range_minutes(band['start_time'], band['end_time']), band['required_count'])
        for band in bands
    ]
    if not ranges:
        return []

    boundaries = sorted(
        {start for start, _, _ in ranges}
        | {end for _, end, _ in ranges}
        | set(extra_boundaries)
    )

    profile = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        demand = sum(count for start, end, count in ranges if start <= lo and hi <= end)
        profile.append([lo, hi, demand])
    return profile


def _min_demand(profile, start, end):
    """Kleinster Restbedarf ueber [start, end) - 0, wenn irgendwo nichts offen ist.

    Damit beantwortet die Funktion genau die Frage "wie oft wird diese Vorlage
    ueber ihre ganze Laufzeit gebraucht". Eine 0 an einer einzigen Stelle
    heisst: die Vorlage laeuft dort ins Leere, sie wuerde ueberbesetzen.
    """
    inside = [demand for lo, hi, demand in profile if lo >= start and hi <= end]
    if not inside:
        return 0
    return min(inside)


def _subtract(profile, start, end, count):
    """count Personen ueber [start, end) vom Restbedarf abziehen.

    Exakt, weil die Grenzen von start und end selbst Intervallkanten sind -
    siehe _elementary_profile().
    """
    for entry in profile:
        lo, hi, remaining = entry
        if lo >= start and hi <= end:
            entry[2] = max(0, remaining - count)


def _split_at(profile, point):
    """Das Elementarintervall teilen, durch das `point` mitten hindurchgeht.

    Gebraucht, wenn ein Block an einer Stelle enden soll, die keine Bandgrenze
    und keine Vorlagengrenze ist - beim Deckel MAX_BLOCK_MINUTES und beim
    Zuschnitt auf ein Arbeitszeitfenster. _subtract() zieht nur ueber ganze
    Intervalle ab, die Kante muss also erst existieren.
    """
    for index, (lo, hi, demand) in enumerate(profile):
        if lo < point < hi:
            profile[index] = [lo, point, demand]
            profile.insert(index + 1, [point, hi, demand])
            return


def _block(shift_type_id, start, end):
    return {
        'shift_type_id': shift_type_id,
        'start_time': _minutes_to_time(start),
        'end_time': _minutes_to_time(end),
    }


def _matching_template(templates, start, end):
    """Die Vorlage, deren Zeiten genau getroffen werden - oder None.

    Ein Block, der zufaellig genau auf einer Vorlage liegt, soll deren Namen
    und Farbe tragen statt als namenloser Dienst zu erscheinen.
    """
    for template in sorted(templates, key=lambda tpl: tpl['id']):
        if _time_range_minutes(template['start_time'], template['end_time']) == (start, end):
            return template['id']
    return None


def _templates_starting_at(templates, profile, point):
    """Vorlagen, die an `point` beginnen und ganz im Restbedarf liegen.

    "Ganz im Restbedarf" heisst: ueber ihre gesamte Laufzeit ist noch etwas
    offen. Eine Vorlage, die ueber das Ende des Bedarfs hinauslaeuft, wuerde
    ueberbesetzen - zu viel zu planen kostet Geld und stuende in keinem Band.
    Sortiert nach Dauer absteigend, bei Gleichstand nach ID: die laengste
    passende Vorlage traegt am meisten Bedarf ab, und die ID haelt das
    Ergebnis deterministisch.
    """
    passend = []
    for template in templates:
        start, end = _time_range_minutes(template['start_time'], template['end_time'])
        if start != point:
            continue
        if _min_demand(profile, start, end) == 0:
            continue
        passend.append((end - start, -template['id'], template['id'], end))
    passend.sort(reverse=True)
    return [(template_id, end) for _, _, template_id, end in passend]


def cover_demand(bands, templates):
    """Bedarfsbaender eines Tages zu Bloecken machen.

    Verfahren: immer am fruehesten Punkt mit offenem Restbedarf ansetzen und
    von dort einen Block bilden. Beginnt dort eine Vorlage, die ganz im
    Restbedarf liegt, wird die laengste davon genommen - das ist der
    Normalfall und ergibt genau das erwartete Bild. Sonst reicht der Block so
    weit nach rechts, wie der Restbedarf nicht abreisst, hoechstens aber
    MAX_BLOCK_MINUTES.

    Warum von links und nicht nach "welche Vorlage traegt am meisten ab":
    Diese naheliegende Gewichtung deckt die Spitze zuerst und laesst die
    Schulter als eigenen Rest stehen. Bei Bedarf 06:00-08:00 fuer zwei und
    08:00-14:00 fuer drei liefert sie 3 mal 08:00-14:00 plus 2 mal
    06:00-08:00 - fuenf Leute und zwei Zwei-Stunden-Bloecke, die niemand
    arbeiten will. Von links gelesen entstehen 2 mal 06:00-14:00 plus 1 mal
    08:00-14:00: drei Leute, und das ist zugleich das Minimum, denn unter die
    hoechste Spitze der Bedarfskurve kommt keine Loesung.

    Warum das die Umstellung rueckwaertskompatibel macht: Migration 0007 hat
    die Baender aus genau diesen Vorlagen abgeleitet. Auf unveraendertem
    Bestand beginnt an jedem offenen Punkt genau die Vorlage, aus der das Band
    stammt, und es entstehen wieder exakt die Bloecke, die build_slots()
    bisher gebaut hat.
    """
    boundaries = set()
    for template in templates:
        boundaries.update(_time_range_minutes(template['start_time'], template['end_time']))
    profile = _elementary_profile(bands, boundaries)
    if not profile:
        return []

    ordered_templates = sorted(templates, key=lambda tpl: tpl['id'])
    blocks = []

    while True:
        first = next((i for i, entry in enumerate(profile) if entry[2] > 0), None)
        if first is None:
            break
        start = profile[first][0]

        passend = _templates_starting_at(ordered_templates, profile, start)
        if passend:
            template_id, end = passend[0]
        else:
            # Erst die Kante am Deckel schaffen, dann nach rechts laufen: ohne
            # sie koennte ein einziges langes Band gar nicht geteilt werden,
            # weil die Schleife nur an vorhandenen Intervallgrenzen haltmacht.
            _split_at(profile, start + MAX_BLOCK_MINUTES)
            first = next(i for i, entry in enumerate(profile) if entry[0] == start)
            last = first
            while (last + 1 < len(profile) and profile[last + 1][2] > 0
                   and profile[last + 1][0] == profile[last][1]
                   and profile[last + 1][1] - start <= MAX_BLOCK_MINUTES):
                last += 1
            end = profile[last][1]
            template_id = _matching_template(ordered_templates, start, end)

        blocks.append(_block(template_id, start, end))
        _subtract(profile, start, end, 1)

    return blocks
