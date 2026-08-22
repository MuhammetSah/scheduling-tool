import { useTranslation } from '../i18n/context'

/**
 * The month as a wall calendar: one column per weekday, one row per week.
 *
 * Each day cell lists its shift types, and under each one every person working
 * it - a shift needing three people simply shows three names. Read-only by
 * design; editing lives in the table view, which has room for the controls.
 */
function CalendarView({ schedule, shiftTypes, highlightEmployeeId }) {
  // Marking only, never a rule: § 9 forbids work on public holidays and § 10
  // exempts whole industries, and only the operator knows which side this
  // business is on. Empty while no federal state is selected.
  const holidayNames = new Map((schedule.holidays || []).map(h => [h.date, h.name]))
  const { t, weekdayLabels, absenceLabels } = useTranslation()

  function personLabel(slot) {
    if (slot.employee_id !== null) return slot.employee_name
    if (slot.absence_type) {
      const label = absenceLabels[slot.absence_type] || slot.absence_type
      return slot.absent_employee_name
        ? `${label} (${t('shiftCell.absentWasPrefix')}: ${slot.absent_employee_name})`
        : label
    }
    return t('common.unassigned')
  }

  const byDate = new Map()
  for (const a of schedule.assignments) {
    if (!byDate.has(a.date)) byDate.set(a.date, [])
    byDate.get(a.date).push(a)
  }
  if (!schedule.year || !schedule.month) return null

  // Lay the grid out from the calendar month itself, not from the dates that
  // happen to have shifts. An employee only sees the days they work, so driving
  // the layout off the data would slide every date into the wrong weekday.
  const { year, month } = schedule
  const daysInMonth = new Date(year, month, 0).getDate()
  const allDates = Array.from(
    { length: daysInMonth },
    (_, i) => `${year}-${String(month).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
  )

  // Pad so the first row starts on a Monday and the last row ends on a Sunday.
  const leadingBlanks = (new Date(year, month - 1, 1).getDay() + 6) % 7
  const trailingBlanks = 6 - ((new Date(year, month - 1, daysInMonth).getDay() + 6) % 7)

  const cells = [
    ...Array(leadingBlanks).fill(null),
    ...allDates,
    ...Array(trailingBlanks).fill(null),
  ]

  const weeks = []
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7))
  }

  const shiftOrder = new Map(shiftTypes.map((st, i) => [st.id, i]))

  function dayNumber(iso) {
    return Number(iso.slice(8, 10))
  }

  return (
    <div className="calendar">
      <div className="calendar-head">
        {weekdayLabels.map(label => (
          <div key={label} className="calendar-head-cell">{label}</div>
        ))}
      </div>

      {weeks.map((week, weekIndex) => (
        <div key={weekIndex} className="calendar-week">
          {week.map((iso, dayIndex) => {
            if (!iso) {
              return <div key={`blank-${dayIndex}`} className="calendar-day calendar-day-empty" />
            }

            const dayAssignments = byDate.get(iso) || []
            // Keyed on the hours as well as the template, not on the
            // template alone: every template-less block of the day shares the
            // id null, and since Etappe 4 a block trimmed to someone's
            // availability window shares its template's id while running
            // shorter hours. Either way one heading per distinct pair is the
            // only honest rendering - the old key showed the first block's
            // times above everyone in the group.
            const groups = new Map()
            for (const a of dayAssignments) {
              const key = `${a.shift_type_id ?? 'free'}|${a.start_time}|${a.end_time}`
              if (!groups.has(key)) groups.set(key, [])
              groups.get(key).push(a)
            }
            // Template order first, then start time, so two groups of the same
            // template keep a stable, readable order instead of depending on
            // insertion.
            const orderedGroups = [...groups.entries()].sort((a, b) => {
              const orderDiff = (shiftOrder.get(a[1][0].shift_type_id) ?? 0)
                - (shiftOrder.get(b[1][0].shift_type_id) ?? 0)
              return orderDiff !== 0 ? orderDiff : a[1][0].start_time.localeCompare(b[1][0].start_time)
            })
            const isWeekend = dayIndex >= 5
            const hasGap = dayAssignments.some(a => a.employee_id === null)

            return (
              <div key={iso} className={`calendar-day ${isWeekend ? 'calendar-day-weekend' : ''} ${holidayNames.has(iso) ? 'calendar-day-holiday' : ''}`}>
                <div className="calendar-day-header">
                  <span className="calendar-day-number">{dayNumber(iso)}</span>
                  {holidayNames.has(iso) && (
                    <span className="calendar-holiday" title={holidayNames.get(iso)}>
                      {holidayNames.get(iso)}
                    </span>
                  )}
                  {hasGap && <span className="calendar-gap-dot" title={t('calendar.gapTitle')} />}
                </div>

                {orderedGroups.map(([groupKey, slots]) => (
                  <div key={groupKey} className="calendar-shift">
                    <div className="calendar-shift-name">
                      {/* A block with no shift type of its own has neither a
                          name nor a color to show - fall back to the same
                          generic label ScheduleGrid uses for it and a neutral
                          dot instead of a missing/undefined color. */}
                      <span className="badge-dot" style={{ backgroundColor: slots[0].shift_type_color ?? 'var(--text-muted)' }} />
                      {slots[0].shift_type_name ?? t('schedule.freeBlockColumn')}
                      <span
                        className={`calendar-shift-time ${slots[0].time_overridden ? 'calendar-shift-time-changed' : ''}`}
                        title={slots[0].time_overridden
                          ? t('calendar.timeOverrideTitle', {
                              start: slots[0].start_time, end: slots[0].end_time,
                              defaultStart: slots[0].default_start_time, defaultEnd: slots[0].default_end_time,
                            })
                          : undefined}
                      >
                        {slots[0].start_time}–{slots[0].end_time}{slots[0].time_overridden ? ' *' : ''}
                      </span>
                    </div>
                    <ul className="calendar-people">
                      {slots
                        .slice()
                        .sort((a, b) => a.slot_index - b.slot_index)
                        .map(slot => (
                          <li
                            key={slot.id}
                            className={[
                              'calendar-person',
                              slot.employee_id === null ? 'calendar-person-unfilled' : '',
                              slot.absence_type ? 'calendar-person-absence' : '',
                              highlightEmployeeId && (slot.employee_id === highlightEmployeeId || slot.absent_employee_id === highlightEmployeeId)
                                ? 'calendar-person-me' : '',
                            ].join(' ').trim()}
                            title={slot.absence_type && slot.absent_employee_name
                              ? t('calendar.absenceTitle', {
                                  name: slot.absent_employee_name,
                                  label: absenceLabels[slot.absence_type] || slot.absence_type,
                                })
                              : undefined}
                          >
                            {personLabel(slot)}
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export default CalendarView
