import { useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

/**
 * One shift on one date: the hours it runs that day, everyone working it, and
 * (for HR) the controls to change any of that.
 *
 * A cell is a list of time groups, one per distinct start/end pair it holds.
 * Usually there is exactly one - three people in the same early shift share
 * its hours - and the cell then looks and behaves as it always did: one time
 * pair at the top, editable for HR, which writes a per-date override for the
 * whole shift type. Underneath, each person's row (AssignmentSlot) can carry
 * its own hours on top of that: it shows and edits them only when that one
 * assignment has an individual override (assignment_time_set), otherwise it
 * silently follows whatever the group above resolves to, so the same time
 * doesn't repeat pointlessly on every row.
 *
 * Several groups appear once a cell holds blocks that genuinely run at
 * different times: the free-block column gathers every template-less block of
 * the date, and since Etappe 4 a block trimmed to someone's availability
 * window keeps its template's shift_type_id while running shorter hours. The
 * cell-level time edit is hidden in that case - it takes shiftType.id rather
 * than an assignment id, so it would rewrite blocks the user wasn't looking
 * at. The per-person edit is the right tool there.
 *
 * `shiftType.id === null` marks the synthetic "free block" column that
 * ScheduleGrid adds for assignments with no shift type of their own - there's
 * nothing to add a per-date override to or add another slot against, so
 * those two cell-level controls are hidden for it (see isFreeBlockColumn
 * below). The same flag also has to reach AssignmentSlot: a block without a
 * shift type can't exist without its own start/end times (the backend
 * rejects that), so assignment_time_set is always true there and the
 * per-person "back to default" button would otherwise show up for every row
 * in that column and fail every time it's pressed.
 */
function ShiftCell({
  date,
  shiftType,
  slots,
  employees,
  readOnly,
  swapSelection,
  onReassign,
  onToggleSwap,
  onSetTimes,
  onAddSlot,
  onRemoveSlot,
  onReportAbsence,
  setFlash,
}) {
  const { t } = useTranslation()
  const [editingTimes, setEditingTimes] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  const isFreeBlockColumn = shiftType.id === null

  if (slots.length === 0) {
    return readOnly || isFreeBlockColumn ? (
      <span className="hint">—</span>
    ) : (
      <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
        {t('shiftCell.addSlotButton')}
      </button>
    )
  }

  const sorted = slots.slice().sort((a, b) => a.slot_index - b.slot_index)

  // Slots sharing one cell no longer share one time pair. Two things broke
  // that assumption in Etappe 4: the free-block column collects every
  // template-less block of the date at once, and a block trimmed to someone's
  // availability window keeps its template's shift_type_id while running
  // different hours. Showing sorted[0]'s times for all of them silently
  // mislabels everyone else, so each distinct pair gets its own heading and
  // its own people underneath it.
  const timeGroups = []
  for (const slot of sorted) {
    const key = `${slot.start_time}-${slot.end_time}`
    const existing = timeGroups.find(group => group.key === key)
    if (existing) existing.slots.push(slot)
    else timeGroups.push({ key, slots: [slot] })
  }

  const sample = timeGroups[0].slots[0]
  // The cell-level time edit writes a per-date override for the whole shift
  // type (onSetTimes takes shiftType.id, not an assignment id), so it only
  // has an unambiguous meaning while the cell shows a single pair. With
  // several, the per-person edit inside AssignmentSlot is the right tool and
  // this control would quietly rewrite blocks the user wasn't looking at.
  const singleTimeGroup = timeGroups.length === 1

  function startEditing() {
    setStart(sample.start_time)
    setEnd(sample.end_time)
    setEditingTimes(true)
  }

  function employeeOptions(currentEmployeeId) {
    return employees
      .filter(e => e.active || e.id === currentEmployeeId)
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  return (
    <div className="shift-cell">
      {timeGroups.map(group => {
        const head = group.slots[0]
        return (
          <div className="cell-time-group" key={group.key}>
            {editingTimes && singleTimeGroup ? (
              <div className="cell-time-edit">
                <input type="time" value={start} onChange={e => setStart(e.target.value)} aria-label={t('shiftCell.startAria')} />
                <input type="time" value={end} onChange={e => setEnd(e.target.value)} aria-label={t('shiftCell.endAria')} />
                <button
                  type="button"
                  className="btn-small"
                  onClick={() => { onSetTimes(date, shiftType.id, start, end); setEditingTimes(false) }}
                >
                  {t('shiftCell.confirmButton')}
                </button>
                {head.time_overridden && (
                  <button
                    type="button"
                    className="btn-secondary btn-small"
                    title={t('shiftCell.resetToDefaultTitle', { start: head.default_start_time, end: head.default_end_time })}
                    onClick={() => { onSetTimes(date, shiftType.id, null, null); setEditingTimes(false) }}
                  >
                    {t('shiftCell.defaultButton')}
                  </button>
                )}
                <button type="button" className="btn-secondary btn-small" onClick={() => setEditingTimes(false)}>
                  ✕
                </button>
              </div>
            ) : (
              <div className={`cell-times ${head.time_overridden ? 'cell-times-overridden' : ''}`}>
                <span title={head.time_overridden
                  ? t('shiftCell.deviatesFromTitle', { start: head.default_start_time, end: head.default_end_time })
                  : undefined}>
                  {head.start_time}–{head.end_time}{head.time_overridden ? ' *' : ''}
                </span>
                {!readOnly && !isFreeBlockColumn && singleTimeGroup && (
                  <button type="button" className="cell-icon" title={t('shiftCell.editTimesTitle')} onClick={startEditing}>
                    ✎
                  </button>
                )}
              </div>
            )}

            {group.slots.map(slot => (
              <AssignmentSlot
                key={slot.id}
                slot={slot}
                date={date}
                readOnly={readOnly}
                isFreeBlockColumn={isFreeBlockColumn}
                swapSelection={swapSelection}
                employeeOptions={employeeOptions}
                onReassign={onReassign}
                onToggleSwap={onToggleSwap}
                onRemoveSlot={onRemoveSlot}
                onReportAbsence={onReportAbsence}
                setFlash={setFlash}
              />
            ))}
          </div>
        )
      })}

      {!readOnly && !isFreeBlockColumn && (
        <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
          {t('shiftCell.addSlotButton')}
        </button>
      )}
    </div>
  )
}

/** One person's place within a shift cell - its own component so the
 * replacement-suggestions fetch and the per-person time edit each have
 * somewhere to keep local state. */
function AssignmentSlot({
  slot,
  date,
  readOnly,
  isFreeBlockColumn,
  swapSelection,
  employeeOptions,
  onReassign,
  onToggleSwap,
  onRemoveSlot,
  onReportAbsence,
  setFlash,
}) {
  const { t, absenceLabels } = useTranslation()
  const [suggestions, setSuggestions] = useState(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [editingTime, setEditingTime] = useState(false)
  const [editingBreak, setEditingBreak] = useState(false)
  const [breakDraft, setBreakDraft] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  // Shown only when it deviates - same restraint as the times above, or the
  // same number would sit on every row and the one that matters would drown.
  // `!= null` rather than a truthiness test on purpose: a stored 0 is the
  // statement "this block runs without a break", and that has to be visible.
  const breakDeviates = slot.break_minutes != null

  const isAbsence = Boolean(slot.absence_type)
  const absenceLabel = absenceLabels[slot.absence_type] || slot.absence_type
  const label = isAbsence
    ? `${absenceLabel}${slot.absent_employee_name ? ` (${t('shiftCell.absentWasPrefix')}: ${slot.absent_employee_name})` : ''}`
    : (slot.employee_name || t('common.unassigned'))

  // Reassigning must carry this assignment's own times and break along, or
  // the PUT below would silently clear them (see SchedulePage.reassign):
  // preserve the times when they're individually set, otherwise there's
  // nothing to keep - the assignment already just follows the cell above.
  // The break is passed as stored, never as resolved: sending the effective
  // value would turn "not separately agreed" into an explicit one, and the
  // block would stop following the legal minimum if its hours ever changed.
  function reassignKeepingTime(employeeIdRaw) {
    onReassign(
      slot.id,
      employeeIdRaw,
      slot.assignment_time_set ? slot.start_time : null,
      slot.assignment_time_set ? slot.end_time : null,
      slot.break_minutes ?? null,
    )
  }

  async function loadSuggestions() {
    setLoadingSuggestions(true)
    try {
      setSuggestions(await api.get(`/assignments/${slot.id}/replacement-suggestions`))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setLoadingSuggestions(false)
    }
  }

  function pickSuggestion(employeeId) {
    reassignKeepingTime(employeeId)
    setSuggestions(null)
  }

  function startEditingTime() {
    setStart(slot.start_time || '')
    setEnd(slot.end_time || '')
    setEditingTime(true)
  }

  function saveTime() {
    onReassign(slot.id, slot.employee_id ?? '', start, end, slot.break_minutes ?? null)
    setEditingTime(false)
  }

  function resetTime() {
    onReassign(slot.id, slot.employee_id ?? '', null, null, slot.break_minutes ?? null)
    setEditingTime(false)
  }

  function saveBreak(rohwert) {
    // Leer heisst zurueck auf die gesetzliche Mindestpause, nicht null Minuten.
    const minuten = rohwert === '' ? null : Math.max(0, Number(rohwert) || 0)
    onReassign(
      slot.id,
      slot.employee_id ?? '',
      slot.assignment_time_set ? slot.start_time : null,
      slot.assignment_time_set ? slot.end_time : null,
      minuten,
    )
    setEditingBreak(false)
  }

  if (readOnly) {
    return (
      <div className={`slot-cell ${slot.employee_id ? '' : 'unfilled'}`}>
        <span className={slot.employee_id ? '' : (isAbsence ? 'calendar-person-absence' : 'calendar-person-unfilled')}>
          {label}
        </span>
        {slot.assignment_time_set && (
          <span className="slot-time" title={t('shiftCell.personalTimeTitle')}>
            {slot.start_time}–{slot.end_time}
          </span>
        )}
        {breakDeviates && (
          <span className="slot-break" title={t('shiftCell.breakTitle')}>
            {t('shiftCell.breakShort', { minutes: slot.break_minutes })}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className={`slot-cell ${slot.employee_id ? '' : 'unfilled'} ${swapSelection === slot.id ? 'swap-selected' : ''}`}>
      <select value={slot.employee_id ?? ''} onChange={e => reassignKeepingTime(e.target.value)}>
        <option value="">{t('shiftCell.unassignedOption')}</option>
        {employeeOptions(slot.employee_id).map(e => (
          <option key={e.id} value={e.id}>{e.name}</option>
        ))}
      </select>

      {editingTime ? (
        <div className="cell-time-edit">
          <input type="time" value={start} onChange={e => setStart(e.target.value)} aria-label={t('shiftCell.startAria')} />
          <input type="time" value={end} onChange={e => setEnd(e.target.value)} aria-label={t('shiftCell.endAria')} />
          <button type="button" className="btn-small" onClick={saveTime}>
            OK
          </button>
          {/* Hidden for the free-block column: assignment_time_set is always
              true there (no shift type to fall back to), so this would
              otherwise always be visible and always fail with a 400 when
              pressed. */}
          {slot.assignment_time_set && !isFreeBlockColumn && (
            <button
              type="button"
              className="btn-secondary btn-small"
              title={t('shiftCell.resetPersonTimeTitle')}
              onClick={resetTime}
            >
              {t('shiftCell.defaultButton')}
            </button>
          )}
          <button type="button" className="btn-secondary btn-small" onClick={() => setEditingTime(false)}>
            ✕
          </button>
        </div>
      ) : (
        <>
          {slot.assignment_time_set && (
            <span className="slot-time" title={t('shiftCell.personalTimeTitle')}>
              {slot.start_time}–{slot.end_time}
            </span>
          )}
          <button type="button" className="cell-icon" title={t('shiftCell.editPersonTimeTitle')} onClick={startEditingTime}>
            ✎
          </button>
          {breakDeviates && (
            <span className="slot-break" title={t('shiftCell.breakTitle')}>
              {t('shiftCell.breakShort', { minutes: slot.break_minutes })}
            </span>
          )}
        </>
      )}

      {editingBreak ? (
        <div className="cell-time-edit">
          <input
            type="number"
            min="0"
            step="5"
            value={breakDraft}
            onChange={e => setBreakDraft(e.target.value)}
            aria-label={t('shiftCell.breakAria')}
            placeholder={String(slot.effective_break_minutes ?? 0)}
          />
          <button type="button" className="btn-small" onClick={() => saveBreak(breakDraft)}>
            {t('shiftCell.confirmButton')}
          </button>
          {/* Empty means back to the legal minimum, which is a different
              thing from zero minutes - hence its own button rather than
              clearing the field and pressing OK. */}
          <button
            type="button"
            className="btn-secondary btn-small"
            title={t('shiftCell.resetBreakTitle')}
            onClick={() => saveBreak('')}
          >
            {t('shiftCell.defaultButton')}
          </button>
          <button type="button" className="btn-secondary btn-small" onClick={() => setEditingBreak(false)}>
            ✕
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="cell-icon"
          title={t('shiftCell.editBreakTitle')}
          onClick={() => { setBreakDraft(String(slot.break_minutes ?? '')); setEditingBreak(true) }}
        >
          ☕
        </button>
      )}

      {isAbsence && (
        <span
          className={`badge ${slot.absence_type === 'sick' ? 'badge-inactive' : 'badge-pending'}`}
          title={slot.absent_employee_name ? `${slot.absent_employee_name}: ${absenceLabel}` : undefined}
        >
          {absenceLabel}
        </span>
      )}

      {slot.employee_id === null && (
        <button
          type="button"
          className="btn-secondary btn-small"
          onClick={loadSuggestions}
          disabled={loadingSuggestions}
          title={t('shiftCell.suggestTitle')}
        >
          {loadingSuggestions ? t('common.ellipsis') : t('shiftCell.suggestButton')}
        </button>
      )}

      {slot.employee_id !== null && !isAbsence && onReportAbsence && (
        <select
          value=""
          title={t('shiftCell.quickAbsenceTitle')}
          onChange={e => {
            const type = e.target.value
            if (type) onReportAbsence(slot.employee_id, date, type)
            e.target.value = ''
          }}
        >
          <option value="">{t('shiftCell.quickAbsencePlaceholder')}</option>
          <option value="sick">{t('shiftCell.reportSickOption')}</option>
          <option value="vacation">{t('shiftCell.reportVacationOption')}</option>
        </select>
      )}

      <button
        type="button"
        className={`swap-toggle ${swapSelection === slot.id ? 'active' : ''}`}
        title={t('shiftCell.selectForSwapTitle')}
        onClick={() => onToggleSwap(slot.id)}
      >
        ⇄
      </button>
      <button
        type="button"
        className="cell-icon cell-icon-danger"
        title={t('shiftCell.removeSlotTitle')}
        onClick={() => onRemoveSlot(slot.id)}
      >
        ✕
      </button>

      {suggestions !== null && (
        <div className="suggestion-list">
          {suggestions.length === 0 ? (
            <span className="hint">{t('shiftCell.noSuggestions')}</span>
          ) : (
            suggestions.map(s => (
              <button
                type="button"
                key={s.employee_id}
                className="btn-secondary btn-small"
                onClick={() => pickSuggestion(s.employee_id)}
                title={t('shiftCell.suggestionLoadTitle', { n: s.current_load })}
              >
                {s.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default ShiftCell
