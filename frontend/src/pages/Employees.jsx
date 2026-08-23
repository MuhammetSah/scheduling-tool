import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

const emptyForm = {
  id: null,
  name: '',
  email: '',
  active: true,
  max_shifts_per_month: '',
  weekly_hours: '',
  min_rest_hours: 11,
  max_daily_hours: 10,
  unavailable_weekdays: [],
  allowed_shift_types: [],
  qualifications: [],
  unavailable_dates: [],
  availability_mode: 'anytime',
  availability: [],
}

// True while today falls inside a window's valid_from/valid_until bounds.
// Both are optional and both are inclusive, matching the backend's
// window_is_valid_on(). ISO dates compare correctly as plain strings, which is
// what the backend does too.
function windowAppliesToday(w, today) {
  if (w.valid_from && today < w.valid_from) return false
  if (w.valid_until && today > w.valid_until) return false
  return true
}

// Groups a weekday/start_time-sorted availability list (as returned by the
// API) into one entry per weekday, for the compact per-weekday badge in the
// list view. Relies on the backend's sort order rather than re-sorting here.
//
// Expired and not-yet-started windows are left out: the generator ignores
// them, so showing them as badges made the list claim an availability the
// planner would not use - and the person read as available on a day they were
// not.
function groupByWeekday(availability, today) {
  const groups = []
  for (const w of availability.filter(w => windowAppliesToday(w, today))) {
    const last = groups[groups.length - 1]
    if (last && last.weekday === w.weekday) {
      last.windows.push(w)
    } else {
      groups.push({ weekday: w.weekday, windows: [w] })
    }
  }
  return groups
}

function Employees({ setFlash }) {
  const { t, weekdayLabels, weekdayNames } = useTranslation()
  // Computed once per render rather than per badge, and as a local ISO date -
  // toISOString() would hand back UTC and shift the day for anyone east of
  // Greenwich in the evening.
  const today = new Date().toLocaleDateString('sv-SE')
  const [employees, setEmployees] = useState([])
  const [shiftTypes, setShiftTypes] = useState([])
  const [qualifications, setQualifications] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [newDate, setNewDate] = useState('')
  // Local-only key for React list identity and per-window UI state (the
  // expanded/collapsed validity range); stripped out again in submitForm()
  // before the payload goes to the API, which knows nothing about it.
  const nextWindowKey = useRef(0)

  async function load() {
    try {
      const [emps, types, nachweise] = await Promise.all([
        api.get('/employees'), api.get('/shift-types'), api.get('/qualifications')])
      setEmployees(emps)
      setShiftTypes(types)
      setQualifications(nachweise)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the awaits inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function startCreate() {
    setForm(emptyForm)
    setShowForm(true)
  }

  function startEdit(emp) {
    setForm({
      id: emp.id,
      name: emp.name,
      email: emp.email || '',
      active: emp.active,
      max_shifts_per_month: emp.max_shifts_per_month ?? '',
      weekly_hours: emp.weekly_hours ?? '',
      min_rest_hours: emp.min_rest_hours ?? 11,
      max_daily_hours: emp.max_daily_hours ?? 10,
      unavailable_weekdays: emp.unavailable_weekdays,
      allowed_shift_types: emp.allowed_shift_types,
      qualifications: (emp.qualifications || []).map(q => ({
        qualification_id: q.qualification_id, valid_until: q.valid_until })),
      unavailable_dates: emp.unavailable_dates,
      availability_mode: emp.availability_mode || 'anytime',
      availability: emp.availability.map(w => ({
        ...w,
        _key: `w${++nextWindowKey.current}`,
        // Existing windows show their validity range expanded so it isn't
        // hidden away; only newly added windows (addWindow()) start collapsed.
        _expanded: Boolean(w.valid_from || w.valid_until),
      })),
    })
    setShowForm(true)
  }

  function toggleWeekday(wd) {
    setForm(f => ({
      ...f,
      unavailable_weekdays: f.unavailable_weekdays.includes(wd)
        ? f.unavailable_weekdays.filter(x => x !== wd)
        : [...f.unavailable_weekdays, wd],
    }))
  }

  function toggleQualification(id) {
    setForm(f => ({
      ...f,
      qualifications: f.qualifications.some(q => q.qualification_id === id)
        ? f.qualifications.filter(q => q.qualification_id !== id)
        : [...f.qualifications, { qualification_id: id, valid_until: null }],
    }))
  }

  function setValidUntil(id, bis) {
    setForm(f => ({
      ...f,
      qualifications: f.qualifications.map(
        q => (q.qualification_id === id ? { ...q, valid_until: bis } : q)),
    }))
  }

  function toggleShiftType(id) {
    setForm(f => ({
      ...f,
      allowed_shift_types: f.allowed_shift_types.includes(id)
        ? f.allowed_shift_types.filter(x => x !== id)
        : [...f.allowed_shift_types, id],
    }))
  }

  function addWindow(weekday) {
    setForm(f => ({
      ...f,
      availability: [
        ...f.availability,
        { _key: `w${++nextWindowKey.current}`, _expanded: false, weekday, start_time: '', end_time: '', valid_from: null, valid_until: null },
      ],
    }))
  }

  function updateWindow(key, changes) {
    setForm(f => ({
      ...f,
      availability: f.availability.map(w => (w._key === key ? { ...w, ...changes } : w)),
    }))
  }

  function removeWindow(key) {
    setForm(f => ({ ...f, availability: f.availability.filter(w => w._key !== key) }))
  }

  function toggleWindowValidity(key) {
    setForm(f => ({
      ...f,
      availability: f.availability.map(w => (w._key === key ? { ...w, _expanded: !w._expanded } : w)),
    }))
  }

  function addUnavailableDate() {
    if (!newDate || form.unavailable_dates.some(d => d.date === newDate)) return
    setForm(f => ({ ...f, unavailable_dates: [...f.unavailable_dates, { date: newDate, reason: '' }] }))
    setNewDate('')
  }

  function removeUnavailableDate(date) {
    setForm(f => ({ ...f, unavailable_dates: f.unavailable_dates.filter(d => d.date !== date) }))
  }

  async function submitForm(e) {
    e.preventDefault()
    const payload = {
      name: form.name,
      email: form.email || null,
      active: form.active,
      max_shifts_per_month: form.max_shifts_per_month === '' ? null : Number(form.max_shifts_per_month),
      weekly_hours: form.weekly_hours === '' ? null : Number(form.weekly_hours),
      min_rest_hours: form.min_rest_hours === '' ? null : Number(form.min_rest_hours),
      max_daily_hours: form.max_daily_hours === '' ? null : Number(form.max_daily_hours),
      unavailable_weekdays: form.unavailable_weekdays,
      allowed_shift_types: form.allowed_shift_types,
      unavailable_dates: form.unavailable_dates,
      availability_mode: form.availability_mode,
      // Drop windows that never got any hours typed into them, and strip the
      // local-only _key/_expanded fields (see nextWindowKey above) - the API
      // knows nothing about them.
      //
      // The filter is not a second validation layer duplicating backend rules
      // (it checks nothing about the *values*, and produces no message of its
      // own): it only skips a row the user added but left completely empty.
      // Without it, adding a window, leaving it blank and switching back to
      // 'anytime' submits `start_time: ''` - the time inputs are unmounted by
      // then, so the browser's `required` no longer fires, and the backend
      // answers 400 about a field that is not on screen. A half-filled window
      // in 'windows' mode is still caught by `required` and never reaches
      // here. Filtering rather than clearing `availability` on the mode switch
      // keeps the entered windows around when HR toggles back and forth -
      // silently discarding them would be the same data loss the mode switch
      // deliberately avoids for unavailable_weekdays.
      availability: form.availability.filter(w => w.start_time && w.end_time).map(w => ({
        weekday: w.weekday,
        start_time: w.start_time,
        end_time: w.end_time,
        valid_from: w.valid_from,
        valid_until: w.valid_until,
      })),
    }
    try {
      // Die Nachweise hängen an einer eigenen Route: sie sind eine Liste mit
      // eigenen Feldern, und sie in den Mitarbeiter-Rumpf zu falten hieße,
      // ihn zu einem Sammelbecken zu machen — dasselbe, was den
      // Arbeitszeitfenstern in Etappe 4 eine eigene Route gebracht hat.
      let ziel = form.id
      if (ziel) {
        await api.put(`/employees/${ziel}`, payload)
      } else {
        ziel = (await api.post('/employees', payload)).id
        // Die neue Kennung sofort ins Formular. Schlägt der zweite Aufruf
        // fehl, steht der Mitarbeiter bereits in der Datenbank — ohne das
        // hier legte ein zweiter Versuch ihn ein zweites Mal an.
        setForm(f => ({ ...f, id: ziel }))
      }
      await api.put(`/employees/${ziel}/qualifications`,
                    { qualifications: form.qualifications })
      setFlash({ type: 'success',
                 text: t(form.id ? 'employees.flashUpdated' : 'employees.flashCreated') })
      setShowForm(false)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function exportEmployeeData(id, name) {
    try {
      await api.download(`/employees/${id}/data-export`,
                         `auskunft-${name.replace(/[^\w-]+/g, '-').toLowerCase()}.json`)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteEmployee(id) {
    if (!confirm(t('employees.confirmDelete'))) return
    try {
      const result = await api.delete(`/employees/${id}`)
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function shiftTypeName(id) {
    return shiftTypes.find(s => s.id === id)?.name || `#${id}`
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>{t('employees.title')}</h2>
          <button onClick={startCreate}>{t('employees.newButton')}</button>
        </div>

        {employees.length === 0 ? (
          <p className="empty-state">{t('employees.empty')}</p>
        ) : (
          <ul className="item-list">
            {employees.map(emp => (
              <li key={emp.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">{emp.name}{!emp.active && t('employees.inactiveSuffix')}</span>
                  <div className="item-meta">
                    {emp.email && <span className="badge">{emp.email}</span>}
                    {emp.max_shifts_per_month != null && (
                      <span className="badge">{t('employees.maxPerMonthBadge', { n: emp.max_shifts_per_month })}</span>
                    )}
                    {emp.weekly_hours != null && (
                      <span className="badge">{t('employees.weeklyHoursBadge', { n: emp.weekly_hours })}</span>
                    )}
                    {emp.min_rest_hours != null && emp.min_rest_hours !== 11 && (
                      <span className="badge">{t('employees.restHoursBadge', { n: emp.min_rest_hours })}</span>
                    )}
                    {emp.unavailable_weekdays.map(wd => (
                      <span key={wd} className="badge">{t('employees.notOnWeekdayBadge', { weekday: weekdayNames[wd] })}</span>
                    ))}
                    {emp.allowed_shift_types.length > 0 && (
                      <span className="badge">
                        {t('employees.onlyShiftTypesBadge', { list: emp.allowed_shift_types.map(shiftTypeName).join(', ') })}
                      </span>
                    )}
                    {emp.unavailable_dates.length > 0 && (
                      <span className="badge">{t('employees.freeDaysBadge', { n: emp.unavailable_dates.length })}</span>
                    )}
                    {emp.availability_mode === 'windows' && emp.availability.length === 0 && (
                      <span className="badge">{t('employees.windowsModeNoWindowsBadge')}</span>
                    )}
                    {/* Hinterlegt, aber heute ohne Wirkung - das ist etwas anderes
                        als gar kein Fenster, und der Unterschied entscheidet, ob
                        jemand ein Fenster anlegen oder eine Grenze aendern muss. */}
                    {emp.availability_mode === 'windows' && emp.availability.length > 0
                      && groupByWeekday(emp.availability, today).length === 0 && (
                      <span className="badge">{t('employees.windowsAllExpiredBadge')}</span>
                    )}
                    {emp.availability_mode === 'windows' && groupByWeekday(emp.availability, today).map(g => (
                      <span key={g.weekday} className="badge">
                        {t('employees.windowBadge', {
                          weekday: weekdayLabels[g.weekday],
                          times: g.windows.map(w => `${w.start_time}–${w.end_time}`).join(', '),
                        })}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="item-actions">
                  <button className="btn-secondary btn-small" onClick={() => startEdit(emp)}>{t('common.edit')}</button>
                  <button className="btn-secondary btn-small" title={t('employees.dataExportTitle')} onClick={() => exportEmployeeData(emp.id, emp.name)}>{t('employees.dataExportButton')}</button>
                  <button className="btn-danger btn-small" onClick={() => deleteEmployee(emp.id)}>{t('common.delete')}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showForm && (
        <div className="panel">
          <h3>{form.id ? t('employees.editTitle') : t('employees.newTitle')}</h3>
          <form onSubmit={submitForm}>
            <div className="field">
              <label htmlFor="emp-name">{t('common.name')}</label>
              <input id="emp-name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
            </div>
            <div className="field">
              <label htmlFor="emp-email">{t('employees.emailLabel')}</label>
              <input id="emp-email" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="emp-max">{t('employees.maxShiftsLabel')}</label>
              <input id="emp-max" type="number" min="0" value={form.max_shifts_per_month} onChange={e => setForm(f => ({ ...f, max_shifts_per_month: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="emp-weekly-hours">{t('employees.weeklyHoursLabel')}</label>
              <input
                id="emp-weekly-hours"
                type="number"
                min="0"
                step="0.5"
                placeholder={t('employees.weeklyHoursPlaceholder')}
                value={form.weekly_hours}
                onChange={e => setForm(f => ({ ...f, weekly_hours: e.target.value }))}
              />
              <p className="hint">{t('employees.weeklyHoursHint')}</p>
            </div>
            <div className="field">
              <label htmlFor="emp-rest">{t('employees.minRestLabel')}</label>
              <input
                id="emp-rest"
                type="number"
                min="0"
                step="0.5"
                value={form.min_rest_hours}
                onChange={e => setForm(f => ({ ...f, min_rest_hours: e.target.value }))}
                required
              />
              <p className="hint">{t('employees.minRestHint')}</p>
            </div>
            <div className="field">
              <label htmlFor="emp-daily">{t('employees.maxDailyHoursLabel')}</label>
              <input
                id="emp-daily"
                type="number"
                min="0.5"
                max="10"
                step="0.5"
                value={form.max_daily_hours}
                onChange={e => setForm(f => ({ ...f, max_daily_hours: e.target.value }))}
                required
              />
              <p className="hint">{t('employees.maxDailyHoursHint')}</p>
            </div>
            <div className="field checkbox-field">
              <input id="emp-active" type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
              <label htmlFor="emp-active">{t('employees.activeLabel')}</label>
            </div>
            <div className="field">
              <label>{t('employees.availabilityModeLabel')}</label>
              <div className="view-toggle" role="group" aria-label={t('employees.availabilityModeLabel')}>
                <button
                  type="button"
                  className={form.availability_mode !== 'windows' ? 'active' : ''}
                  onClick={() => setForm(f => ({ ...f, availability_mode: 'anytime' }))}
                >
                  {t('employees.availabilityModeAnytime')}
                </button>
                <button
                  type="button"
                  className={form.availability_mode === 'windows' ? 'active' : ''}
                  onClick={() => setForm(f => ({ ...f, availability_mode: 'windows' }))}
                >
                  {t('employees.availabilityModeWindows')}
                </button>
              </div>
            </div>
            {form.availability_mode === 'windows' && (
              <div className="field">
                <p className="hint">{t('employees.availabilityHint')}</p>
                <div className="availability-editor">
                  {weekdayLabels.map((label, wd) => (
                    <div className="availability-day" key={wd}>
                      <div className="availability-day-header">
                        <span className="availability-day-label">{label}</span>
                        <button type="button" className="btn-secondary btn-small" onClick={() => addWindow(wd)}>
                          {t('employees.addWindowButton')}
                        </button>
                      </div>
                      {form.availability.filter(w => w.weekday === wd).map(w => (
                        <div className="availability-row" key={w._key}>
                          <div className="toolbar">
                            <input
                              type="time"
                              aria-label={t('employees.windowStartAria')}
                              value={w.start_time}
                              onChange={e => updateWindow(w._key, { start_time: e.target.value })}
                              required
                            />
                            <input
                              type="time"
                              aria-label={t('employees.windowEndAria')}
                              value={w.end_time}
                              onChange={e => updateWindow(w._key, { end_time: e.target.value })}
                              required
                            />
                            <button
                              type="button"
                              className="btn-secondary btn-small"
                              onClick={() => toggleWindowValidity(w._key)}
                            >
                              {w._expanded ? t('employees.hideValidityRangeButton') : t('employees.showValidityRangeButton')}
                            </button>
                            <button
                              type="button"
                              className="btn-danger btn-small"
                              title={t('employees.removeWindowTitle')}
                              onClick={() => removeWindow(w._key)}
                            >
                              ×
                            </button>
                          </div>
                          {w._expanded && (
                            <div className="toolbar mt-sm">
                              <div className="field">
                                <label htmlFor={`avail-from-${w._key}`}>{t('employees.validFromLabel')}</label>
                                <input
                                  id={`avail-from-${w._key}`}
                                  type="date"
                                  value={w.valid_from || ''}
                                  onChange={e => updateWindow(w._key, { valid_from: e.target.value || null })}
                                />
                              </div>
                              <div className="field">
                                <label htmlFor={`avail-until-${w._key}`}>{t('employees.validUntilLabel')}</label>
                                <input
                                  id={`avail-until-${w._key}`}
                                  type="date"
                                  value={w.valid_until || ''}
                                  onChange={e => updateWindow(w._key, { valid_until: e.target.value || null })}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Shown in both modes. Hiding it in 'windows' mode looked tidy, but
                unavailable_weekdays is still sent and is still a hard check in
                the scheduler, applied *before* the window check and able only to
                forbid, never to allow (see structurally_eligible() in
                scheduler.py): someone switched to windows mode kept an invisible
                "never Wednesdays" that no window could override, with no way to
                clear it from this form. The list is deliberately not wiped on the
                mode switch - silent data loss would be worse - so the fix is to
                make it visible and explain that it stacks on top of the windows. */}
            <div className="field">
              <label>{t('employees.notWorkingLabel')}</label>
              <div className="weekday-picker">
                {weekdayLabels.map((label, wd) => (
                  <button
                    type="button"
                    key={wd}
                    className={`weekday-chip ${form.unavailable_weekdays.includes(wd) ? 'selected' : ''}`}
                    onClick={() => toggleWeekday(wd)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {form.availability_mode === 'windows' && (
                <p className="hint">{t('employees.notWorkingWindowsHint')}</p>
              )}
            </div>
            {qualifications.length > 0 && (
              <div className="field">
                <label>{t('employees.qualificationsLabel')}</label>
                <p className="hint">{t('employees.qualificationsHint')}</p>
                {qualifications.map(q => {
                  const gehalten = form.qualifications.find(
                    x => x.qualification_id === q.id)
                  return (
                    <div key={q.id} className="toolbar">
                      <button
                        type="button"
                        className={`weekday-chip ${gehalten ? 'selected' : ''}`}
                        onClick={() => toggleQualification(q.id)}
                      >
                        {q.name}
                      </button>
                      {/* Das Ablaufdatum ist die eigentliche Hälfte: ein
                          Nachweis ohne Ablauf wird noch Jahre nach seinem Ende
                          beachtet. Leer heißt "läuft nicht ab" — das ist eine
                          Aussage, keine fehlende Angabe, und deshalb steht der
                          Hinweis oben. */}
                      {gehalten && (
                        <input
                          type="date"
                          aria-label={t('employees.validUntilAria', { name: q.name })}
                          value={gehalten.valid_until || ''}
                          onChange={e => setValidUntil(q.id, e.target.value || null)}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {shiftTypes.length > 0 && (
              <div className="field">
                <label>{t('employees.onlyShiftTypesLabel')}</label>
                <div className="weekday-picker">
                  {shiftTypes.map(st => (
                    <button
                      type="button"
                      key={st.id}
                      className={`weekday-chip ${form.allowed_shift_types.includes(st.id) ? 'selected' : ''}`}
                      onClick={() => toggleShiftType(st.id)}
                    >
                      {st.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="field">
              <label htmlFor="emp-date-off">{t('employees.freeDaysLabel')}</label>
              <div className="toolbar">
                <input id="emp-date-off" type="date" value={newDate} onChange={e => setNewDate(e.target.value)} />
                <button type="button" className="btn-secondary" onClick={addUnavailableDate}>{t('common.add')}</button>
              </div>
              {form.unavailable_dates.length > 0 && (
                <div className="item-meta mt-sm">
                  {form.unavailable_dates.map(d => (
                    <span key={d.date} className="badge">
                      {d.date}
                      <button type="button" className="badge-remove" onClick={() => removeUnavailableDate(d.date)}>×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="toolbar">
              <button type="submit">{form.id ? t('common.save') : t('common.create')}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>{t('common.cancel')}</button>
            </div>
          </form>
        </div>
      )}
    </>
  )
}

export default Employees
