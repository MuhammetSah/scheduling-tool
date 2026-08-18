import { useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

/**
 * One shift on one date: the hours it runs that day, everyone working it, and
 * (for HR) the controls to change any of that.
 *
 * The cell's own time pair (top of the cell) is the shift's hours for this
 * date - editing it there still changes it for everyone on the shift that
 * day, exactly as before. Underneath, each person's row (AssignmentSlot) can
 * carry its own hours on top of that: it shows and edits them only when that
 * one assignment has an individual override (assignment_time_set), otherwise
 * it silently follows whatever the cell above resolves to, so the same time
 * doesn't repeat pointlessly on every row.
 *
 * `shiftType.id === null` marks the synthetic "free block" column that
 * ScheduleGrid adds for assignments with no shift type of their own - there's
 * nothing to add a per-date override to or add another slot against, so
 * those two cell-level controls are hidden for it (see isFreeBlockColumn
 * below).
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
  const sample = sorted[0]

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
      {editingTimes ? (
        <div className="cell-time-edit">
          <input type="time" value={start} onChange={e => setStart(e.target.value)} aria-label={t('shiftCell.startAria')} />
          <input type="time" value={end} onChange={e => setEnd(e.target.value)} aria-label={t('shiftCell.endAria')} />
          <button
            type="button"
            className="btn-small"
            onClick={() => { onSetTimes(date, shiftType.id, start, end); setEditingTimes(false) }}
          >
            OK
          </button>
          {sample.time_overridden && (
            <button
              type="button"
              className="btn-secondary btn-small"
              title={t('shiftCell.resetToDefaultTitle', { start: sample.default_start_time, end: sample.default_end_time })}
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
        <div className={`cell-times ${sample.time_overridden ? 'cell-times-overridden' : ''}`}>
          <span title={sample.time_overridden
            ? t('shiftCell.deviatesFromTitle', { start: sample.default_start_time, end: sample.default_end_time })
            : undefined}>
            {sample.start_time}–{sample.end_time}{sample.time_overridden ? ' *' : ''}
          </span>
          {!readOnly && !isFreeBlockColumn && (
            <button type="button" className="cell-icon" title={t('shiftCell.editTimesTitle')} onClick={startEditing}>
              ✎
            </button>
          )}
        </div>
      )}

      {sorted.map(slot => (
        <AssignmentSlot
          key={slot.id}
          slot={slot}
          date={date}
          readOnly={readOnly}
          swapSelection={swapSelection}
          employeeOptions={employeeOptions}
          onReassign={onReassign}
          onToggleSwap={onToggleSwap}
          onRemoveSlot={onRemoveSlot}
          onReportAbsence={onReportAbsence}
          setFlash={setFlash}
        />
      ))}

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
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  const isAbsence = Boolean(slot.absence_type)
  const absenceLabel = absenceLabels[slot.absence_type] || slot.absence_type
  const label = isAbsence
    ? `${absenceLabel}${slot.absent_employee_name ? ` (${t('shiftCell.absentWasPrefix')}: ${slot.absent_employee_name})` : ''}`
    : (slot.employee_name || t('common.unassigned'))

  // Reassigning must carry this assignment's own times along, or the PUT
  // below would silently clear them (see SchedulePage.reassign): preserve
  // them when they're individually set, otherwise there's nothing to keep -
  // the assignment already just follows the cell above.
  function reassignKeepingTime(employeeIdRaw) {
    onReassign(
      slot.id,
      employeeIdRaw,
      slot.assignment_time_set ? slot.start_time : null,
      slot.assignment_time_set ? slot.end_time : null,
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
    onReassign(slot.id, slot.employee_id ?? '', start, end)
    setEditingTime(false)
  }

  function resetTime() {
    onReassign(slot.id, slot.employee_id ?? '', null, null)
    setEditingTime(false)
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
          {slot.assignment_time_set && (
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
        </>
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
