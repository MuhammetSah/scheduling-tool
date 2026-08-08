import { useState } from 'react'
import { api, ABSENCE_LABELS } from '../api'

/**
 * One shift on one date: the hours it runs that day, everyone working it, and
 * (for HR) the controls to change any of that.
 *
 * Times are edited per date here, not per person - if the early shift finishes
 * early on one day it finishes early for everyone on it, so the whole cell
 * shares one pair of inputs.
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
  const [editingTimes, setEditingTimes] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  if (slots.length === 0) {
    return readOnly ? (
      <span className="hint">—</span>
    ) : (
      <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
        + Platz
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
          <input type="time" value={start} onChange={e => setStart(e.target.value)} aria-label="Beginn" />
          <input type="time" value={end} onChange={e => setEnd(e.target.value)} aria-label="Ende" />
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
              title={`Zurück auf ${sample.default_start_time}–${sample.default_end_time}`}
              onClick={() => { onSetTimes(date, shiftType.id, null, null); setEditingTimes(false) }}
            >
              Standard
            </button>
          )}
          <button type="button" className="btn-secondary btn-small" onClick={() => setEditingTimes(false)}>
            ✕
          </button>
        </div>
      ) : (
        <div className={`cell-times ${sample.time_overridden ? 'cell-times-overridden' : ''}`}>
          <span title={sample.time_overridden
            ? `Abweichend von ${sample.default_start_time}–${sample.default_end_time}`
            : undefined}>
            {sample.start_time}–{sample.end_time}{sample.time_overridden ? ' *' : ''}
          </span>
          {!readOnly && (
            <button type="button" className="cell-icon" title="Zeiten für diesen Tag ändern" onClick={startEditing}>
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

      {!readOnly && (
        <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
          + Platz
        </button>
      )}
    </div>
  )
}

/** One person's place within a shift cell - its own component so the
 * replacement-suggestions fetch has somewhere to keep local state. */
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
  const [suggestions, setSuggestions] = useState(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)

  const isAbsence = Boolean(slot.absence_type)
  const absenceLabel = ABSENCE_LABELS[slot.absence_type] || slot.absence_type
  const label = isAbsence
    ? `${absenceLabel}${slot.absent_employee_name ? ` (war: ${slot.absent_employee_name})` : ''}`
    : (slot.employee_name || 'unbesetzt')

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
    onReassign(slot.id, employeeId)
    setSuggestions(null)
  }

  if (readOnly) {
    return (
      <div className={`slot-cell ${slot.employee_id ? '' : 'unfilled'}`}>
        <span className={slot.employee_id ? '' : (isAbsence ? 'calendar-person-absence' : 'calendar-person-unfilled')}>
          {label}
        </span>
      </div>
    )
  }

  return (
    <div className={`slot-cell ${slot.employee_id ? '' : 'unfilled'} ${swapSelection === slot.id ? 'swap-selected' : ''}`}>
      <select value={slot.employee_id ?? ''} onChange={e => onReassign(slot.id, e.target.value)}>
        <option value="">— unbesetzt —</option>
        {employeeOptions(slot.employee_id).map(e => (
          <option key={e.id} value={e.id}>{e.name}</option>
        ))}
      </select>

      {isAbsence && (
        <span
          className={`badge ${slot.absence_type === 'sick' ? 'badge-inactive' : 'badge-pending'}`}
          title={slot.absent_employee_name ? `${slot.absent_employee_name} ist ${absenceLabel}` : undefined}
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
          title="Passende Mitarbeiter für diese Schicht vorschlagen"
        >
          {loadingSuggestions ? '…' : 'Vorschläge'}
        </button>
      )}

      {slot.employee_id !== null && !isAbsence && onReportAbsence && (
        <select
          value=""
          title="Für diesen Mitarbeiter an diesem Tag Krankheit oder Urlaub eintragen - die Schicht wird dann frei"
          onChange={e => {
            const type = e.target.value
            if (type) onReportAbsence(slot.employee_id, date, type)
            e.target.value = ''
          }}
        >
          <option value="">Abwesenheit …</option>
          <option value="sick">Krank melden</option>
          <option value="vacation">Urlaub melden</option>
        </select>
      )}

      <button
        type="button"
        className={`swap-toggle ${swapSelection === slot.id ? 'active' : ''}`}
        title="Für Tausch auswählen"
        onClick={() => onToggleSwap(slot.id)}
      >
        ⇄
      </button>
      <button
        type="button"
        className="cell-icon cell-icon-danger"
        title="Diesen Platz an diesem Tag entfernen"
        onClick={() => onRemoveSlot(slot.id)}
      >
        ✕
      </button>

      {suggestions !== null && (
        <div className="suggestion-list">
          {suggestions.length === 0 ? (
            <span className="hint">Keine geeigneten Vorschläge gefunden.</span>
          ) : (
            suggestions.map(s => (
              <button
                type="button"
                key={s.employee_id}
                className="btn-secondary btn-small"
                onClick={() => pickSuggestion(s.employee_id)}
                title={`${s.current_load} Schichten in diesem Monat`}
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
