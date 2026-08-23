"""Head-to-head comparison of the scheduling approaches.

Run with:  ./venv/bin/python benchmark.py

Each strategy solves the same seeded scenarios under the same hard constraints,
and is scored on what actually matters to an HR user:

  unfilled  - shifts nobody was assigned to (lower is better; dominates everything)
  spread    - busiest employee's shift count minus the quietest (lower is fairer)
  wknd      - the same spread measured over weekend shifts only
  time      - wall-clock seconds to produce the plan

CP-SAT (OR-Tools) is included as a proven-optimal reference point, not as a
candidate implementation: it is a heavy dependency for what this tool needs.
"""

import calendar
import random
import time
from collections import Counter
from datetime import date

import baselines
from block_planner import build_month_blocks
from coverage_model import coverage_curve
from scheduler import (
    CHRONOLOGICAL, DEFAULT_TIME_BUDGET_SECONDS, MOST_CONSTRAINED, PlanTooLarge,
    build_slots, generate_schedule,
)


def employee(id, max_shifts_per_month=None, unavailable_weekdays=None, unavailable_dates=None, allowed_shift_types=None):
    return {
        'id': id,
        'max_shifts_per_month': max_shifts_per_month,
        'unavailable_weekdays': set(unavailable_weekdays or []),
        'unavailable_dates': set(unavailable_dates or []),
        'allowed_shift_types': set(allowed_shift_types) if allowed_shift_types else None,
    }


def scenario_small_team():
    """A cafe: 6 people, two shifts a day, a couple of fixed days off."""
    employees = [
        employee(1), employee(2),
        employee(3, unavailable_weekdays=[2]),
        employee(4, unavailable_weekdays=[5, 6]),
        employee(5, allowed_shift_types=[1]),
        employee(6, max_shifts_per_month=10),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 1 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_realistic_shop():
    """A retail shop: 14 people, three shifts, weekday-heavy staffing."""
    rng = random.Random(7)
    employees = []
    for i in range(1, 15):
        employees.append(employee(
            i,
            max_shifts_per_month=rng.choice([None, None, None, 15, 18]),
            unavailable_weekdays=rng.sample(range(7), k=rng.choice([0, 0, 1, 1, 2])),
            allowed_shift_types=rng.choice([None, None, None, [1], [1, 2]]),
        ))
    shift_types = [
        {'id': 1, 'requirements': {wd: (3 if wd < 5 else 2) for wd in range(7)}},
        {'id': 2, 'requirements': {wd: (2 if wd < 5 else 1) for wd in range(7)}},
        {'id': 3, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_tight():
    """Barely enough staff: heavy restrictions, little slack. Where greedy hurts."""
    employees = [
        employee(1, allowed_shift_types=[1]),
        employee(2, allowed_shift_types=[1]),
        employee(3, allowed_shift_types=[2]),
        employee(4, unavailable_weekdays=[0, 1]),
        employee(5, unavailable_weekdays=[5, 6], max_shifts_per_month=12),
        employee(6, max_shifts_per_month=8),
        employee(7),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 2 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_large_hospital():
    """A ward: 30 people, three round-the-clock shifts, vacation blocks."""
    rng = random.Random(99)
    employees = []
    for i in range(1, 31):
        vacation_start = rng.randint(1, 20)
        employees.append(employee(
            i,
            max_shifts_per_month=rng.choice([None, 20, 22]),
            unavailable_weekdays=rng.sample(range(7), k=rng.choice([0, 1, 1, 2])),
            unavailable_dates=[f'2026-08-{day:02d}' for day in range(vacation_start, vacation_start + rng.choice([0, 0, 5]))],
            allowed_shift_types=rng.choice([None, None, None, [1, 2], [3]]),
        ))
    shift_types = [
        {'id': 1, 'requirements': {wd: 5 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 4 for wd in range(7)}},
        {'id': 3, 'requirements': {wd: 3 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_understaffed():
    """Genuinely too few people for the demand: the plan will have gaps whatever
    you do, so the only question is how many. This is where search earns its keep."""
    employees = [
        employee(1, allowed_shift_types=[1]),
        employee(2, allowed_shift_types=[1], unavailable_weekdays=[5, 6]),
        employee(3, allowed_shift_types=[2]),
        employee(4, max_shifts_per_month=6),
        employee(5, unavailable_weekdays=[0, 1, 2]),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 2 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 2 for wd in range(7)}},
    ]
    return employees, shift_types


# (label, callable, optimises_fairness) - the last flag decides whether a proven
# result may be marked optimal on *both* axes the table reports.
STRATEGIES = [
    ('greedy first-fit', lambda *a: baselines.greedy_first_fit(*a), False),
    ('greedy balanced', lambda *a: baselines.greedy_balanced(*a), False),
    ('random-restart greedy', lambda *a: baselines.random_restart_greedy(*a), False),
    ('v1   chronological', lambda *a: generate_schedule(*a, ordering=CHRONOLOGICAL, fairness=False), False),
    ('v1.2 constrained-first', lambda *a: generate_schedule(*a, ordering=MOST_CONSTRAINED, fairness=False), False),
    ('v1.3 fairness (chrono)', lambda *a: generate_schedule(*a, ordering=CHRONOLOGICAL, fairness=True), True),
    ('v1.3 fairness (constr.)', lambda *a: generate_schedule(*a, ordering=MOST_CONSTRAINED, fairness=True), True),
    ('v1.3 AUTO (production)', lambda *a: generate_schedule(*a), True),
    ('v1.3 AUTO + weekend eq.', lambda *a: generate_schedule(*a, weekend_weight=3), True),
]

if baselines.ORTOOLS_AVAILABLE:
    STRATEGIES.append(('CP-SAT (reference)', lambda *a: baselines.cp_sat(*a), True))


SCENARIOS = [
    ('Small team (6 people, 2 shifts)', scenario_small_team),
    ('Retail shop (14 people, 3 shifts)', scenario_realistic_shop),
    ('Tight staffing (7 people, heavy limits)', scenario_tight),
    ('Hospital ward (30 people, 3 shifts)', scenario_large_hospital),
    ('Understaffed (5 people, gaps unavoidable)', scenario_understaffed),
]


def run():
    import time as _time
    year, month = 2026, 8

    for title, build in SCENARIOS:
        employees, shift_types = build()
        print(f'\n{title}')
        print(f'{"strategy":<26} {"unfilled":>9} {"spread":>7} {"wknd":>5} {"time":>10}')
        print('-' * 62)

        for name, strategy, optimises_fairness in STRATEGIES:
            start = _time.monotonic()
            result = strategy(year, month, employees, shift_types)
            elapsed = result.get('elapsed_seconds', _time.monotonic() - start)
            f = result['fairness']
            proven = result.get('proven_optimal') and optimises_fairness
            print(f'{name:<26} {result["unfilled_count"]:>9} {f["spread"]:>7} '
                  f'{f["weekend_spread"]:>5} {elapsed:>9.3f}s{" *" if proven else ""}')

        print(f'  total slots: {result["total_slots"]}   '
              f'* = proven optimal for gaps and balance together')


# ---------- Etappe 4: alter gegen neuer Bedarfspfad ----------
#
# Zwei Fragen, und nur diese beiden:
#
#   1. Aendert die Umstellung auf coverage_requirements den Plan auf
#      unveraendertem Bestand? Sie darf es nicht. Migration 0007 leitet die
#      Baender aus genau den Schichtarten ab, aus denen build_slots() bisher
#      seine Plaetze gebaut hat - es muessen wieder dieselben Bloecke
#      herauskommen.
#   2. Schliesst der Zuschnitt Luecken? Das ist der Nutzen der ganzen Etappe,
#      und er laesst sich in einer Zahl ausdruecken.


def _timed_employee(id, availability=None, **rest):
    person = employee(id, **rest)
    person.update({
        'weekly_hours': None,
        'min_rest_hours': 11,
        'max_daily_hours': 10,
        'availability_mode': 'windows' if availability else 'anytime',
        'availability': availability or [],
    })
    return person


def _bands_by_date(year, month, shift_types):
    """Die Bedarfsbaender jedes Tages, abgeleitet wie in Migration 0007.

    Kein Datenbankzugriff - dieselbe Rechnung, die 0007 einmalig gegen echte
    Daten gefahren hat, hier gegen die Szenariodaten.
    """
    by_weekday = {}
    for weekday in range(7):
        des_tages = [
            {'start_time': st['start_time'], 'end_time': st['end_time'],
             'required_count': st['requirements'].get(weekday, 0)}
            for st in shift_types if st['requirements'].get(weekday, 0) > 0
        ]
        if des_tages:
            by_weekday[weekday] = coverage_curve(des_tages)

    by_date = {}
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        tag = date(year, month, day)
        if tag.weekday() in by_weekday:
            by_date[tag.isoformat()] = by_weekday[tag.weekday()]
    return by_date


def _block_signature(slots):
    """Was ein Plan an Bloecken enthaelt, unabhaengig von der Reihenfolge."""
    return Counter((s['date'], s['start_time'], s['end_time']) for s in slots)


def scenario_unchanged_stock():
    """Der Bestand, wie ihn Migration 0007 vorgefunden hat: drei Schichtarten
    mit festen Zeiten und Wochentagszahlen, elf Leute."""
    employees = [_timed_employee(i) for i in range(1, 12)]
    shift_types = [
        {'id': 1, 'start_time': '06:00', 'end_time': '14:00',
         'requirements': {wd: (3 if wd < 5 else 2) for wd in range(7)}},
        {'id': 2, 'start_time': '14:00', 'end_time': '22:00',
         'requirements': {wd: (2 if wd < 5 else 1) for wd in range(7)}},
        {'id': 3, 'start_time': '22:00', 'end_time': '06:00',
         'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_windows():
    """Der Fall, fuer den der Zuschnitt gebaut wurde.

    Taeglich drei Plaetze in der Fruehschicht 06:00-14:00. Nur zwei Leute sind
    uneingeschraenkt verfuegbar; die uebrigen vier koennen erst ab 08:00. Ohne
    Zuschnitt bleibt jeden Tag ein Platz leer, obwohl sechs der acht Stunden zu
    decken waeren.

    Bewusst ohne zweite Schichtart: mit einer Spaetschicht 14:00-22:00 waeren
    es genau die Spaetdienste, die unbesetzt blieben - und die beruehren das
    Fenster 08:00-14:00 gar nicht, der Zuschnitt haette dort nichts zu tun.
    Das Szenario haette dann nichts gezeigt.
    """
    fenster = [{'weekday': wd, 'start_time': '08:00', 'end_time': '14:00',
                'valid_from': None, 'valid_until': None} for wd in range(7)]
    employees = (
        [_timed_employee(i) for i in (1, 2)]
        + [_timed_employee(i, availability=fenster) for i in range(3, 7)]
    )
    shift_types = [
        {'id': 1, 'start_time': '06:00', 'end_time': '14:00',
         'requirements': {wd: 3 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_scaled(people, per_day, window_share=0.5, seed=7):
    """Ein Betrieb wachsender Groesse, auf dem Produktionspfad.

    `window_share` ist der Anteil der Belegschaft im Fenster-Modus - genau
    dort sitzen die beiden zurueckgestellten Leistungsbefunde: der Zuschnitt
    in plan_day() greift nur bei Fenster-Leuten, und die Fensterpruefung
    rechnet im innersten Schleifenkoerper von eligible_candidates() alle
    "HH:MM"-Zeichenketten je Kandidat und Knoten neu.

    In Produktion ist employee_availability leer - niemand nutzt den Modus.
    Genau deshalb ist das hier eine Frage nach der Zukunft und nicht nach
    heute.

    Das Szenario ist absichtlich schwer: die Fenster-Leute koennen 08:00-16:00,
    die Schichten laufen 06:00-14:00 und 14:00-22:00, also passt niemand von
    ihnen ganz in eine. Die hohe Zahl unbesetzter Plaetze ist deshalb kein
    Befund, sondern der Aufbau - gemessen werden soll der teure Fall, nicht
    der bequeme.
    """
    rng = random.Random(seed)
    fenster = [{'weekday': wd, 'start_time': '08:00', 'end_time': '16:00',
                'valid_from': None, 'valid_until': None} for wd in range(7)]
    employees = []
    for i in range(1, people + 1):
        mit_fenster = rng.random() < window_share
        employees.append(_timed_employee(
            i,
            availability=fenster if mit_fenster else None,
            unavailable_weekdays=rng.sample(range(7), k=rng.choice([0, 0, 1])),
        ))
    shift_types = [
        {'id': 1, 'start_time': '06:00', 'end_time': '14:00',
         'requirements': {wd: per_day for wd in range(7)}},
        {'id': 2, 'start_time': '14:00', 'end_time': '22:00',
         'requirements': {wd: per_day for wd in range(7)}},
    ]
    return employees, shift_types


def measure_scaling():
    """Wo steht die Wand?

    Die beiden Leistungsbefunde tragen seit ihrer Aufnahme die Notiz "erst
    angehen, wenn der Benchmark es zeigt". Gelaufen ist er dafuer nie. Das
    hier ist die Messung, die die Notiz einloest - nicht eine Optimierung auf
    Verdacht.

    Gemessen werden beide Stufen getrennt, weil die Befunde in verschiedenen
    liegen: build_month_blocks() ist Stufe 1 (der Zuschnitt), generate_schedule()
    ist Stufe 2 (die Suche). Und gegen das Zeitbudget der Suche gehalten, denn
    das ist die Zahl, die zaehlt: wird es erreicht, liefert der Planer weiter
    einen Plan, aber einen schlechteren.
    """
    year, month = 2026, 8
    print('\nSkalierung: wo steht die Wand? (Produktionspfad, Fenster-Modus)')
    print(f'{"people":>7} {"per shift":>10} {"blocks":>7} {"stage 1":>9} {"stage 2":>9} '
          f'{"budget":>8} {"unfilled":>9}')
    print('-' * 68)

    for people, per_day in ((10, 2), (25, 5), (50, 10), (100, 20), (200, 40)):
        employees, shift_types = scenario_scaled(people, per_day)
        bands = _bands_by_date(year, month, shift_types)

        start = time.perf_counter()
        slots = build_month_blocks(year, month, shift_types, bands, employees)
        stufe1 = time.perf_counter() - start

        start = time.perf_counter()
        try:
            ergebnis = generate_schedule(year, month, employees, shift_types, slots=slots)
        except PlanTooLarge as zu_gross:
            # Die Grenze gehoert in die Tabelle, nicht in einen Abbruch: sie
            # ist genau das Ergebnis, wegen dem diese Messung existiert.
            print(f'{people:>7} {per_day:>10} {len(slots):>7} {stufe1:>8.3f}s '
                  f'{"-":>9} {"-":>8} {"zu gross (max " + str(zu_gross.limit) + ")":>9}')
            continue
        stufe2 = time.perf_counter() - start

        anteil = stufe2 / DEFAULT_TIME_BUDGET_SECONDS
        print(f'{people:>7} {per_day:>10} {len(slots):>7} {stufe1:>8.3f}s {stufe2:>8.3f}s '
              f'{anteil:>7.0%} {ergebnis["unfilled_count"]:>9}')

    print('  stage 1 = build_month_blocks (Zuschnitt), stage 2 = generate_schedule (Suche)')
    print(f'  budget = Anteil am Zeitbudget EINES Suchlaufs ({DEFAULT_TIME_BUDGET_SECONDS}s).')
    print('  Ueber 100% heisst nicht ueberzogen: bleiben Luecken, faehrt AUTO einen')
    print('  zweiten Lauf mit anderer Reihenfolge - zwei volle Budgets sind das Maximum.')

def compare_demand_paths():
    year, month = 2026, 8

    print('\nEtappe 4: alter gegen neuer Bedarfspfad')
    print(f'{"scenario":<26} {"path":<10} {"blocks":>7} {"unfilled":>9} {"identical":>10}')
    print('-' * 68)

    for title, build in (('unchanged stock', scenario_unchanged_stock),
                         ('availability windows', scenario_windows)):
        employees, shift_types = build()

        alt_slots = build_slots(year, month, shift_types)
        alt = generate_schedule(year, month, employees, shift_types)

        neu_slots = build_month_blocks(
            year, month, shift_types, _bands_by_date(year, month, shift_types), employees)
        neu = generate_schedule(year, month, employees, shift_types, slots=neu_slots)

        gleich = _block_signature(alt_slots) == _block_signature(neu_slots)
        print(f'{title:<26} {"old":<10} {len(alt_slots):>7} {alt["unfilled_count"]:>9} {"":>10}')
        print(f'{"":<26} {"stage 1":<10} {len(neu_slots):>7} {neu["unfilled_count"]:>9} '
              f'{("yes" if gleich else "no"):>10}')


if __name__ == '__main__':
    run()
    compare_demand_paths()
    measure_scaling()
