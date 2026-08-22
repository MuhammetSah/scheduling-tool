import calendar
import time
from datetime import date, datetime, timedelta

# Safety valves so a pathological/understaffed month can't hang the request forever.
DEFAULT_NODE_BUDGET = 300_000
DEFAULT_TIME_BUDGET_SECONDS = 8.0

# Slot ordering strategies.
CHRONOLOGICAL = 'chronological'          # v1: plan the month day by day
MOST_CONSTRAINED = 'most_constrained'    # v1.2: hardest-to-staff slots first
AUTO = 'auto'                            # v1.3: chronological, retried harder only if shifts go unfilled


class _BudgetExceeded(Exception):
    pass


def time_to_minutes(hhmm):
    """Minutes since midnight for an "HH:MM" string."""
    hours, _, minutes = hhmm.partition(':')
    return int(hours) * 60 + int(minutes)


def _time_range_minutes(start_time, end_time):
    """Start and end minute of a time range, since midnight of the start day.

    An end at or before its start is taken to lie on the following day and
    gets 1440 added - the same midnight convention as shift_duration_minutes().
    Shared foundation for window_contains_shift() below and, via
    coverage_model's re-export, for the demand-band logic - one rollover rule,
    not one copy per caller.
    """
    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)
    if end <= start:
        end += 24 * 60
    return start, end


def _ranges_overlap(range_a, range_b):
    """Do two minute ranges overlap - even across midnight?

    Half-open bounds [start, end): two ranges that merely touch (one's end
    equals the other's start) do not overlap. The second range is additionally
    checked one cycle earlier and later (+-1440 minutes), because the minute
    axis is really a ring: minute 1800 of a night shift is the same instant as
    minute 360 of the following day.

    The one place this shift is computed - coverage_model's overlap and
    containment checks reuse this function so there aren't several similar
    versions of the same ring logic.
    """
    start_a, end_a = range_a
    start_b, end_b = range_b
    return any(
        start_a < end_b + shift and start_b + shift < end_a
        for shift in (-24 * 60, 0, 24 * 60)
    )


def _closed_range(open_time, close_time):
    """The closed period as a minute range: from close_time to the next open_time.

    Empty (end <= start) when open around the clock - exactly the case of a
    00:00-00:00 window, which _time_range_minutes() turns into [0, 1440) and
    whose closed period collapses to [1440, 1440).
    """
    open_min, close_min = _time_range_minutes(open_time, close_time)
    return close_min, open_min + 24 * 60


def window_contains_shift(window, start_time, end_time):
    """Does the shift fit entirely inside this one window?

    Entirely, not partially - partial coverage is a later stage. Checked via
    the complement: the shift lies inside the window exactly when it does not
    touch the window's CLOSED period. The direct comparison "window_start <=
    shift_start and shift_end <= window_end" cannot handle a window that spans
    the full day: a night shift 22:00-06:00 is [1320, 1800), a round-the-clock
    window 00:00-00:00 is [0, 1440), and 1800 <= 1440 is false - even though
    the window is open around the clock and the shift obviously fits. Read via
    the closed period this resolves itself: it is empty there, and an empty
    range can't intersect anything.

    Shifting the shift by +-1440 and still comparing straight is not enough:
    none of the three placements of [1320, 1800) lie within [0, 1440), because
    the shift crosses the window's edge rather than sitting beside it. The
    ring-ness lives in the window, not in the shift.
    """
    closed_start, closed_end = _closed_range(window['start_time'], window['end_time'])
    if closed_end <= closed_start:
        return True

    return not _ranges_overlap(
        _time_range_minutes(start_time, end_time),
        (closed_start, closed_end),
    )


def window_is_valid_on(window, iso_date):
    """Is this window in effect on this date? Both bounds are inclusive.

    Plain string comparison - ISO dates sort lexicographically correctly, and
    the bounds come from the same source as the slot date.
    """
    valid_from = window.get('valid_from')
    valid_until = window.get('valid_until')
    if valid_from and iso_date < valid_from:
        return False
    if valid_until and iso_date > valid_until:
        return False
    return True


def shift_duration_minutes(start_time, end_time):
    """Minutes a shift lasts, given "HH:MM" strings.

    A shift that ends at or before its own start time (e.g. 22:00-06:00) is
    taken to run past midnight into the next day, not backwards in time.
    """
    start = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')
    if end <= start:
        end += timedelta(days=1)
    return int((end - start).total_seconds() // 60)


# § 4 ArbZG, resolved onto the span rather than onto working time.
#
# The law measures the break against the *working* time, and working time is
# the span minus the break - so read literally the rule chases its own tail: a
# 6:30 span is 6:30 of work without a break, which is "more than six hours" and
# demands 30 minutes, which brings the work down to exactly 6:00, which demands
# nothing at all. Resolved by asking which break is sufficient for the working
# time it itself produces, and taking the smallest such break.
#
# On the span that lands on 6:00 and 9:30 - note 9:30, not 9:00. At a 9:30 span
# a 30-minute break still leaves exactly nine hours, and nine hours is not
# "more than nine"; only from 9:31 does 30 minutes stop being enough. Applying
# the law's own numbers directly to the span is the obvious mistake here.
BREAK_THRESHOLDS = ((6 * 60, 0), (9 * 60 + 30, 30))
LONG_SHIFT_BREAK_MINUTES = 45


def legal_break_minutes(duration_minutes):
    """The shortest break § 4 ArbZG allows for a block of this span."""
    if duration_minutes is None:
        return 0
    for limit, minutes in BREAK_THRESHOLDS:
        if duration_minutes <= limit:
            return minutes
    return LONG_SHIFT_BREAK_MINUTES


def net_working_minutes(duration_minutes, break_minutes):
    """Working time in the sense of § 2 Abs. 1 ArbZG: the span without the break.

    `break_minutes` None means "not separately agreed", which reads as the
    legal minimum for this span - the law requires that break, so a plan that
    did not subtract it would be claiming someone works eight hours straight
    through. A stored value wins, including a zero: that is HR saying
    something, and constraint_warnings() is where it gets questioned, not here.

    None duration in, None out - same backward compatibility as
    duration_minutes in build_slots(): a caller that only ever dealt in shift
    counts has no hours to subtract from, and gets nothing to enforce.
    """
    if duration_minutes is None:
        return None
    taken = legal_break_minutes(duration_minutes) if break_minutes is None else break_minutes
    return max(0, duration_minutes - taken)


def shift_datetimes(iso_date, start_time, end_time):
    """The (start, end) datetimes of a shift on a given calendar date.

    Same midnight-crossing rule as shift_duration_minutes, applied to actual
    datetimes so gaps between two different shifts (on two different dates)
    can be measured directly.
    """
    d = date.fromisoformat(iso_date) if isinstance(iso_date, str) else iso_date
    start_dt = datetime.combine(d, datetime.strptime(start_time, '%H:%M').time())
    end_dt = datetime.combine(d, datetime.strptime(end_time, '%H:%M').time())
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def rest_gap_hours(earlier, later):
    """Hours between the end of one shift and the start of a later one.

    Each argument is a (start_dt, end_dt) pair as returned by shift_datetimes().
    Negative means the two shifts actually overlap.
    """
    _, earlier_end = earlier
    later_start, _ = later
    return (later_start - earlier_end).total_seconds() / 3600


def build_slots(year, month, shift_types):
    """Expand shift requirements into one entry per person-shift that must be staffed."""
    days_in_month = calendar.monthrange(year, month)[1]
    slots = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        weekday = d.weekday()
        # Monday of this date's calendar week - the bucket weekly-hours caps
        # are tracked against (0=Monday convention, same as WEEKDAYS in db.py).
        week_start = (d - timedelta(days=weekday)).isoformat()
        for shift_type in shift_types:
            required_count = shift_type['requirements'].get(weekday, 0)
            start_time = shift_type.get('start_time')
            end_time = shift_type.get('end_time')
            # None (rather than crashing) when a caller doesn't supply hours -
            # keeps this backward compatible with callers/tests that only ever
            # cared about shift *counts*. Duration- and rest-aware checks
            # simply have nothing to enforce in that case.
            duration_minutes = (
                shift_duration_minutes(start_time, end_time)
                if start_time and end_time else None
            )
            for slot_index in range(required_count):
                slots.append({
                    'date': d.isoformat(),
                    'weekday': weekday,
                    'week_start': week_start,
                    'shift_type_id': shift_type['id'],
                    'slot_index': slot_index,
                    'is_weekend': weekday >= 5,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_minutes': duration_minutes,
                })
    return slots


def structurally_eligible(employee, slot):
    """Constraints that depend only on the employee and the slot, not on other assignments."""
    if slot['weekday'] in employee['unavailable_weekdays']:
        return False
    if slot['date'] in employee['unavailable_dates']:
        return False
    allowed = employee['allowed_shift_types']
    if allowed and slot['shift_type_id'] not in allowed:
        return False
    if employee.get('availability_mode', 'anytime') == 'windows':
        # Without known shift hours there is nothing to check - same stance
        # as the rest-period check (see rest_period_ok).
        if slot.get('start_time') and slot.get('end_time'):
            if not any(
                window_contains_shift(window, slot['start_time'], slot['end_time'])
                for window in employee.get('availability', ())
                if window['weekday'] == slot['weekday']
                and window_is_valid_on(window, slot['date'])
            ):
                return False
    return True


def order_slots(slots, employees, ordering):
    """v1.2: decide the order the search fills slots in.

    Filling the hardest slots first ("most constrained first", the classic CSP
    minimum-remaining-values heuristic) means a dead end is hit near the top of
    the search tree, where backtracking is cheap, instead of after committing to
    hundreds of assignments. Chronological order is kept so the two can be
    compared - see benchmark.py.
    """
    if ordering == CHRONOLOGICAL:
        return list(slots)
    if ordering != MOST_CONSTRAINED:
        raise ValueError(f'unknown ordering: {ordering}')

    def sort_key(slot):
        eligible_count = sum(1 for e in employees if structurally_eligible(e, slot))
        # Date/shift tie-breakers only exist to keep the ordering deterministic.
        # shift_type_id is None for a block with no template, and None does not
        # compare against int - the raw value would raise TypeError as soon as
        # stage 1 emits one. Same shape as the result sort at the end of
        # _search(): template-less last, then by the hours.
        return (
            eligible_count,
            slot['date'],
            slot['shift_type_id'] is None,
            slot['shift_type_id'] or 0,
            slot.get('start_time') or '',
            slot['slot_index'],
        )

    return sorted(slots, key=sort_key)


def ideal_sum_squares(total, count):
    """Lowest achievable sum of squared loads: spread `total` shifts over `count` people."""
    if count == 0:
        return 0
    base, remainder = divmod(total, count)
    return remainder * (base + 1) ** 2 + (count - remainder) * base ** 2


def fairness_stats(assignments, employees):
    loads = {e['id']: 0 for e in employees}
    weekend_loads = {e['id']: 0 for e in employees}
    for a in assignments:
        if a['employee_id'] is None:
            continue
        loads[a['employee_id']] = loads.get(a['employee_id'], 0) + 1
        if a.get('is_weekend'):
            weekend_loads[a['employee_id']] = weekend_loads.get(a['employee_id'], 0) + 1

    values = list(loads.values())
    if not values:
        return {'loads': {}, 'weekend_loads': {}, 'spread': 0, 'sum_squares': 0, 'weekend_spread': 0}

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    weekend_values = list(weekend_loads.values())

    return {
        'loads': loads,
        'weekend_loads': weekend_loads,
        'spread': max(values) - min(values),
        'weekend_spread': max(weekend_values) - min(weekend_values),
        'sum_squares': sum(v * v for v in values),
        'stdev': round(variance ** 0.5, 3),
        'min': min(values),
        'max': max(values),
    }


def _search(
    year,
    month,
    employees,
    shift_types,
    ordering,
    fairness,
    weekend_weight,
    node_budget,
    time_budget_seconds,
    slots=None,
):
    """Run one backtracking search with a fixed slot ordering.

    This is deliberately *not* greedy: a greedy pass assigns the first workable
    candidate to each slot and never reconsiders. Here, whenever a choice earlier
    in the search makes a later slot unfillable, the search undoes (backtracks)
    that choice and tries another - see `backtrack` below.

    Search is branch-and-bound over a lexicographic objective:
      1. minimise unfilled slots (never trade a staffed shift for a fairer plan)
      2. minimise the sum of squared shift counts per employee (v1.3 fairness)

    Minimising the sum of squares is equivalent to minimising the variance of the
    workload once the number of assigned shifts is fixed, and it updates in O(1)
    per assignment: giving a shift to someone who already has L raises it by 2L+1,
    so each additional shift for an already-busy person is penalised more than a
    first shift for an idle one. Both objective components only ever grow as the
    search goes deeper, so a branch whose partial cost already loses to the best
    complete plan can be pruned safely.
    """
    # Stage 1 (block_planner.build_month_blocks) hands its blocks in ready-made
    # since Etappe 4; build_slots() below is the pre-Etappe-4 path, still used
    # by benchmark.py as a comparison basis and by the 23 backward-compatibility
    # tests in test_scheduler.py.
    raw_slots = build_slots(year, month, shift_types) if slots is None else slots
    slots = order_slots(raw_slots, employees, ordering)

    total_slots = len(slots)
    assignment = [None] * total_slots
    # (employee_id, date) -> the (start_time, end_time) pairs assigned there.
    # Was a plain date -> set(employee_id) until Etappe 4, when "works today"
    # was all anyone needed to know: nobody could work twice in a day. A split
    # shift makes the question "does this block overlap one they already have"
    # instead, and only an overlap is genuinely impossible - two blocks either
    # side of a break are exactly what Spec §4.4 asks for.
    day_hours = {}
    # (employee_id, date) -> number of blocks assigned there whose hours are
    # unknown. Those have no minute axis, so overlap cannot be checked and the
    # old one-per-day rule keeps applying to them. This is the branch that
    # keeps the 23 backward-compatibility tests in test_scheduler.py green.
    day_untimed = {}
    # (employee_id, date) -> minutes assigned there, mirroring week_minutes
    # below. § 3 ArbZG caps the working time of a single day; § 2 Abs. 1 says
    # that is the sum of the blocks, not the span from first start to last end,
    # because the interruption of a split shift is not working time.
    day_minutes = {}
    # (employee_id, week_start) -> minutes assigned so far that week, only
    # tracked where a weekly_hours target makes it relevant.
    week_minutes = {}
    load = {emp['id']: 0 for emp in employees}
    weekend_load = {emp['id']: 0 for emp in employees}

    # Cost is compared lexicographically as (unfilled, fairness_cost).
    best = {'assignment': None, 'unfilled': total_slots + 1, 'cost': 0}
    state = {'nodes': 0, 'start': time.monotonic(), 'exhausted': True}

    ideal_cost = ideal_sum_squares(total_slots, len(employees)) if employees else 0

    def check_budget():
        state['nodes'] += 1
        if state['nodes'] > node_budget:
            raise _BudgetExceeded()
        if state['nodes'] % 2000 == 0 and time.monotonic() - state['start'] > time_budget_seconds:
            raise _BudgetExceeded()

    def day_envelope(iso_date, hours):
        """The working-time envelope of one day: (earliest start, latest end).

        § 5 Abs. 1 ArbZG measures the rest period from the end of the *daily
        working time*, so with a split shift it is the last block's end that
        counts, not the first's. The interruption in between is not rest - it
        sits inside the working day, which only finishes when the last block
        does. shift_datetimes() carries an overnight block past midnight, so an
        envelope ending 06:00 the next morning stays comparable.
        """
        pairs = [shift_datetimes(iso_date, start, end) for start, end in hours]
        return min(start for start, _ in pairs), max(end for _, end in pairs)

    def rest_period_ok(emp, slot):
        """Would assigning `emp` to `slot` leave enough rest either side of it?

        Only checked when the slot's hours are known (backward compatible with
        callers - e.g. existing tests - that only ever dealt in shift counts).
        Like max_shifts_per_month, this is inherently scoped to the month being
        generated: a slot on the 1st can't see what was assigned on the last
        day of the previous month, since that's a different generation run.
        constraint_warnings() in app.py covers that gap for manual edits, where
        the already-saved data spans month boundaries freely.

        Compared day against day, never block against block: a person working
        08:00-12:00 and 16:00-20:00 has four hours in between, and no rest
        period is owed for them.
        """
        min_rest = emp.get('min_rest_hours')
        if not min_rest or not slot['start_time'] or not slot['end_time']:
            return True
        eid = emp['id']
        d = date.fromisoformat(slot['date'])
        previous_day = (d - timedelta(days=1)).isoformat()
        next_day = (d + timedelta(days=1)).isoformat()

        this_day = day_envelope(
            slot['date'],
            list(day_hours.get((eid, slot['date']), ())) + [(slot['start_time'], slot['end_time'])],
        )

        prev = day_hours.get((eid, previous_day))
        if prev and rest_gap_hours(day_envelope(previous_day, prev), this_day) < min_rest:
            return False

        nxt = day_hours.get((eid, next_day))
        if nxt and rest_gap_hours(this_day, day_envelope(next_day, nxt)) < min_rest:
            return False

        return True

    def day_is_free(emp, slot):
        """May `emp` take this block on top of what they already have that day?

        A block with known hours may join others as long as it overlaps none of
        them. A block without hours has no minute axis to compare, so the old
        one-per-day rule still governs it - in both directions, so an untimed
        block and a timed one never end up on the same person on the same day
        either.
        """
        key = (emp['id'], slot['date'])
        held = day_hours.get(key, ())
        untimed = day_untimed.get(key, 0)

        if not slot['start_time'] or not slot['end_time']:
            return not held and not untimed
        if untimed:
            return False

        this_range = _time_range_minutes(slot['start_time'], slot['end_time'])
        return not any(
            _ranges_overlap(this_range, _time_range_minutes(start, end))
            for start, end in held
        )

    def eligible_candidates(slot):
        candidates = []
        for emp in employees:
            eid = emp['id']
            if not day_is_free(emp, slot):
                continue
            if not structurally_eligible(emp, slot):
                continue
            daily_cap = emp.get('max_daily_hours')
            if daily_cap is not None and slot['duration_minutes'] is not None:
                current = day_minutes.get((eid, slot['date']), 0)
                if current + slot['duration_minutes'] > daily_cap * 60:
                    continue
            cap = emp['max_shifts_per_month']
            if cap is not None and load[eid] >= cap:
                continue
            weekly_cap = emp.get('weekly_hours')
            if weekly_cap is not None and slot['duration_minutes'] is not None:
                current = week_minutes.get((eid, slot['week_start']), 0)
                if current + slot['duration_minutes'] > weekly_cap * 60:
                    continue
            if not rest_period_ok(emp, slot):
                continue
            candidates.append(emp)

        # Try the least-loaded people first. With the fairness objective this
        # makes the very first complete plan the search finds already close to
        # balanced, which in turn prunes most of the remaining search tree.
        if weekend_weight and slot['is_weekend']:
            candidates.sort(key=lambda e: (weekend_load[e['id']], load[e['id']], e['id']))
        else:
            candidates.sort(key=lambda e: (load[e['id']], e['id']))
        return candidates

    def is_worse_or_equal(unfilled, cost):
        if unfilled != best['unfilled']:
            return unfilled > best['unfilled']
        return cost >= best['cost']

    def backtrack(i, unfilled_so_far, cost_so_far):
        check_budget()

        # Both objective components only grow deeper in the tree, so a partial
        # plan that already ties or loses can never win.
        if best['assignment'] is not None and is_worse_or_equal(unfilled_so_far, cost_so_far):
            return

        if i == total_slots:
            best['unfilled'] = unfilled_so_far
            best['cost'] = cost_so_far
            best['assignment'] = assignment.copy()
            return

        slot = slots[i]
        d = slot['date']

        for emp in eligible_candidates(slot):
            eid = emp['id']
            added = 0
            if fairness:
                added = 2 * load[eid] + 1
                if weekend_weight and slot['is_weekend']:
                    added += weekend_weight * (2 * weekend_load[eid] + 1)

            has_hours = bool(slot['start_time'] and slot['end_time'])
            week_key = (eid, slot['week_start'])

            day_key = (eid, d)

            assignment[i] = eid
            if has_hours:
                day_hours.setdefault(day_key, []).append(
                    (slot['start_time'], slot['end_time']))
            else:
                day_untimed[day_key] = day_untimed.get(day_key, 0) + 1
            if slot['duration_minutes'] is not None:
                week_minutes[week_key] = week_minutes.get(week_key, 0) + slot['duration_minutes']
                day_minutes[day_key] = day_minutes.get(day_key, 0) + slot['duration_minutes']
            load[eid] += 1
            if slot['is_weekend']:
                weekend_load[eid] += 1

            backtrack(i + 1, unfilled_so_far, cost_so_far + added)

            if has_hours:
                # pop(), not del: the same person may hold several blocks that
                # day now, and only this one is being taken back.
                day_hours[day_key].pop()
                if not day_hours[day_key]:
                    del day_hours[day_key]
            else:
                day_untimed[day_key] -= 1
                if not day_untimed[day_key]:
                    del day_untimed[day_key]
            if slot['duration_minutes'] is not None:
                week_minutes[week_key] -= slot['duration_minutes']
                day_minutes[day_key] -= slot['duration_minutes']
            load[eid] -= 1
            if slot['is_weekend']:
                weekend_load[eid] -= 1
            assignment[i] = None

            # A perfectly even, fully staffed plan cannot be beaten - stop early.
            if best['assignment'] is not None and best['unfilled'] == 0:
                if not fairness or best['cost'] <= ideal_cost:
                    return

        # Last resort: leave this slot unfilled and carry on, in case the rest of
        # the month can still be completed (or at least have fewer gaps).
        assignment[i] = None
        backtrack(i + 1, unfilled_so_far + 1, cost_so_far)

    budget_exceeded = False
    try:
        backtrack(0, 0, 0)
    except _BudgetExceeded:
        budget_exceeded = True
        state['exhausted'] = False

    if best['assignment'] is not None:
        result_assignment = best['assignment']
        unfilled_count = best['unfilled']
    else:
        # Budget ran out before a single complete plan was found; fall back to
        # whatever the search had committed to at that point.
        result_assignment = list(assignment)
        unfilled_count = sum(1 for v in result_assignment if v is None)

    assignments = [
        {
            'date': slot['date'],
            'shift_type_id': slot['shift_type_id'],
            'slot_index': slot['slot_index'],
            'employee_id': emp_id,
            'is_weekend': slot['is_weekend'],
            # Carried through since Etappe 4: the generator now decides a
            # block's hours (stage 1 cuts them to demand and to availability
            # windows), so the caller has something to store. Still None for
            # callers that only ever dealt in shift counts.
            'start_time': slot.get('start_time'),
            'end_time': slot.get('end_time'),
        }
        for slot, emp_id in zip(slots, result_assignment)
    ]
    # Emit in calendar order regardless of the order the search used internally.
    # shift_type_id is None for a block with no template, and None does not
    # compare against int - sorting the raw value raises TypeError the moment
    # stage 1 emits its first template-less block. Those sort last, then by
    # the hours, so a date's blocks come out in a stable, readable order.
    assignments.sort(key=lambda a: (
        a['date'],
        a['shift_type_id'] is None,
        a['shift_type_id'] or 0,
        a['start_time'] or '',
        a['slot_index'],
    ))

    hit_ideal = fairness and unfilled_count == 0 and best['cost'] <= ideal_cost

    return {
        'assignments': assignments,
        'total_slots': total_slots,
        'unfilled_count': unfilled_count,
        'cost': best['cost'] if best['assignment'] is not None else float('inf'),
        'complete': unfilled_count == 0,
        'budget_exceeded': budget_exceeded,
        # True only with respect to the objective this run was configured with:
        # with fairness off, "optimal" means no avoidable gaps and says nothing
        # about how evenly the work is spread.
        'proven_optimal': state['exhausted'] or hit_ideal,
        'nodes_explored': state['nodes'],
        'ordering_used': ordering,
    }


def generate_schedule(
    year,
    month,
    employees,
    shift_types,
    ordering=AUTO,
    fairness=True,
    weekend_weight=0,
    node_budget=DEFAULT_NODE_BUDGET,
    time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
    slots=None,
):
    """Build a month's schedule, choosing a search strategy to suit the month.

    employees: [{id, max_shifts_per_month, unavailable_weekdays: set[int],
                 unavailable_dates: set[str ISO date], allowed_shift_types: set[int] or None,
                 weekly_hours: number or None, min_rest_hours: number or None,
                 availability_mode: 'anytime' or 'windows', optional, default 'anytime',
                 availability: list of {weekday: int, start_time: "HH:MM", end_time: "HH:MM",
                                        valid_from: str or None, valid_until: str or None},
                 optional, only consulted when availability_mode == 'windows'}]
    shift_types: [{id, requirements: {weekday(0-6): required_count},
                   start_time: "HH:MM" or None, end_time: "HH:MM" or None}]

    slots: the month's blocks, ready-made. Since Etappe 4 this is how the
    application plans: block_planner.build_month_blocks() builds the blocks out
    of the demand bands, cutting them to demand and to availability windows,
    and `requirements` above is no longer read at all. Left as None - the
    default - build_slots() expands `requirements` the pre-Etappe-4 way, which
    is what benchmark.py compares against and what the 23 backward-compatibility
    tests in test_scheduler.py exercise.

    weekly_hours and min_rest_hours are both optional, hard, best-effort caps -
    same "no guarantee, reports gaps rather than failing" philosophy as
    max_shifts_per_month - and both fall back to doing nothing when a shift
    type has no start/end time, so existing callers that only ever dealt in
    shift counts are unaffected. availability_mode/availability follow the
    same pattern: callers (including all existing tests) that never supply
    them get 'anytime' behaviour, i.e. no restriction at all - see
    structurally_eligible().

    Benchmarking the two slot orderings against each other (see benchmark.py)
    showed they win in different situations, so neither is right on its own:

      * Chronological order interleaves the days naturally, so always picking the
        least-loaded eligible person lands on an evenly balanced plan straight
        away - often provably the most balanced one possible - in roughly one
        node per shift.
      * Most-constrained-first is far better when there genuinely are not enough
        people: on an understaffed test month it left 17 shifts unstaffed, which
        an exact CP-SAT solve confirmed is the true minimum, where chronological
        order left 23. But it scrambles the day order, which costs balance on
        months that were comfortably staffable anyway.

    So AUTO plans chronologically first, and only if that leaves shifts unstaffed
    does it pay for a second, harder search - taking whichever plan comes out
    better. Normal months therefore cost one cheap pass, and difficult months get
    the extra effort where it actually buys something.
    """
    def run(order):
        return _search(year, month, employees, shift_types, order, fairness,
                       weekend_weight, node_budget, time_budget_seconds, slots)

    if ordering != AUTO:
        result = run(ordering)
    else:
        result = run(CHRONOLOGICAL)
        if result['unfilled_count'] > 0:
            alternative = run(MOST_CONSTRAINED)
            nodes = result['nodes_explored'] + alternative['nodes_explored']
            if (alternative['unfilled_count'], alternative['cost']) < (result['unfilled_count'], result['cost']):
                result = alternative
            result['nodes_explored'] = nodes

    result['fairness'] = fairness_stats(result['assignments'], employees)
    return result
