import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

const emptyExceptionForm = {
  date: '',
  label: '',
  closed: false,
  open_time: '09:00',
  close_time: '17:00',
}

function BusinessHours({ setFlash }) {
  const { t, weekdayLabels, dateLocale } = useTranslation()
  // Always exactly seven rows, one per weekday - GET /business-hours
  // guarantees that, and PUT requires it back the same way (see app.py's
  // replace_business_hours()).
  const [hours, setHours] = useState([])
  const [exceptions, setExceptions] = useState([])
  const [excForm, setExcForm] = useState(emptyExceptionForm)
  // The federal state whose public holidays apply. Lives here because it is a
  // fact about the business as a whole, like the opening hours themselves.
  // Empty means none picked - the tool then knows no holidays at all, which is
  // a valid state and deliberately not defaulted to some state or other.
  const [regions, setRegions] = useState([])
  const [region, setRegion] = useState('')
  const [retentionMonths, setRetentionMonths] = useState('6')
  const [sundayWork, setSundayWork] = useState(false)
  const [savingSundayWork, setSavingSundayWork] = useState(false)

  async function load() {
    try {
      const [h, exc, moeglicheRegionen, settings] = await Promise.all([
        api.get('/business-hours'),
        api.get('/business-hours/exceptions'),
        api.get('/holiday-regions'),
        api.get('/settings'),
      ])
      setHours(h)
      setExceptions(exc)
      setRegions(moeglicheRegionen)
      setRegion(settings.holiday_region || '')
      setRetentionMonths(settings.retention_months || '6')
      setSundayWork(settings.sunday_work_permitted === 'yes')
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the awaits inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function updateHour(weekday, changes) {
    setHours(hs => hs.map(h => (h.weekday === weekday ? { ...h, ...changes } : h)))
  }

  async function submitHours(e) {
    e.preventDefault()
    // open_time/close_time are sent for every row, even a closed one - the
    // backend requires valid times regardless of the closed flag (see
    // replace_business_hours()), and hiding the inputs for a closed day only
    // hides them, it never clears the underlying state above.
    const payload = hours.map(h => ({
      weekday: h.weekday, open_time: h.open_time, close_time: h.close_time, closed: h.closed,
    }))
    try {
      setHours(await api.put('/business-hours', payload))
      setFlash({ type: 'success', text: t('businessHours.flashSaved') })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function submitException(e) {
    e.preventDefault()
    try {
      await api.post('/business-hours/exceptions', {
        date: excForm.date,
        label: excForm.label || null,
        closed: excForm.closed,
        open_time: excForm.closed ? null : excForm.open_time,
        close_time: excForm.closed ? null : excForm.close_time,
      })
      setExcForm(emptyExceptionForm)
      setFlash({ type: 'success', text: t('businessHours.flashExceptionCreated') })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function removeException(dateStr) {
    if (!confirm(t('businessHours.confirmDeleteException'))) return
    try {
      const result = await api.delete(`/business-hours/exceptions/${dateStr}`)
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Same weekday + day.month format as ScheduleGrid's date column, plus the year
  // since exceptions (unlike a single month's schedule) can span several years.
  function formatExceptionDate(iso) {
    const d = new Date(`${iso}T00:00:00`)
    const weekdayIndex = (d.getDay() + 6) % 7 // JS: 0=Sunday -> ours: 0=Monday
    return `${weekdayLabels[weekdayIndex]} ${d.toLocaleDateString(dateLocale, { day: '2-digit', month: '2-digit', year: 'numeric' })}`
  }

  async function saveRegion(code) {
    setRegion(code)
    try {
      await api.put('/settings', { holiday_region: code || null })
      setFlash({ type: 'success', text: t('businessHours.regionSaved') })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function saveSundayWork(erlaubt) {
    // Gesperrt, solange geschrieben wird. Zwei schnelle Klicks schickten sonst
    // zwei PUTs los, und käme das erste als zweites an, stünde in der
    // Datenbank "ja", während das Kreuzchen leer aussieht. Bei einer
    // Einstellung, die entscheidet, ob § 9 überhaupt gemeldet wird, ist das
    // die falsche Art von Kleinigkeit.
    setSavingSundayWork(true)
    setSundayWork(erlaubt)
    try {
      await api.put('/settings', { sunday_work_permitted: erlaubt ? 'yes' : null })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
      setSundayWork(!erlaubt)
    } finally {
      setSavingSundayWork(false)
    }
  }

  async function saveRetention(months) {
    setRetentionMonths(months)
    try {
      await api.put('/settings', { retention_months: months || null })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function purgeNow() {
    if (!confirm(t('retention.purgeConfirm'))) return
    try {
      const result = await api.post('/retention/purge', {})
      setFlash({
        type: 'success',
        text: t('retention.purged', {
          absences: result.removed.absences,
          marks: result.removed.assignment_absence_marks,
          entries: result.removed.audit_entries,
        }),
      })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>{t('sundayWork.title')}</h2>
        </div>
        <div className="field checkbox-field">
          <input
            id="sunday-work"
            type="checkbox"
            checked={sundayWork}
            disabled={savingSundayWork}
            onChange={e => saveSundayWork(e.target.checked)}
          />
          <label htmlFor="sunday-work">{t('sundayWork.label')}</label>
        </div>
        <p className="hint">{t('sundayWork.hint')}</p>
        <p className="hint">{t('sundayWork.stillApplies')}</p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>{t('retention.title')}</h2>
        </div>
        <div className="field">
          <label htmlFor="retention-months">{t('retention.monthsLabel')}</label>
          <input
            id="retention-months"
            type="number"
            min="1"
            value={retentionMonths}
            onChange={e => setRetentionMonths(e.target.value)}
            onBlur={e => saveRetention(e.target.value)}
          />
          <p className="hint">{t('retention.hint')}</p>
        </div>
        <div className="toolbar">
          <button type="button" className="btn-secondary" onClick={purgeNow}>
            {t('retention.purgeButton')}
          </button>
          <span className="hint">{t('retention.scheduleHint')}</span>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>{t('businessHours.regionTitle')}</h2>
        </div>
        <div className="field">
          <label htmlFor="holiday-region">{t('businessHours.regionLabel')}</label>
          <select id="holiday-region" value={region} onChange={e => saveRegion(e.target.value)}>
            <option value="">{t('businessHours.regionNone')}</option>
            {regions.map(r => <option key={r.code} value={r.code}>{r.name}</option>)}
          </select>
          <p className="hint">{t('businessHours.regionHint')}</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>{t('businessHours.title')}</h2>
        </div>
        <form onSubmit={submitHours}>
          <div className="business-hours-grid">
            {hours.map(row => (
              <div className="business-hours-row" key={row.weekday}>
                <span className="business-hours-day">{weekdayLabels[row.weekday]}</span>
                {!row.closed && (
                  <div className="business-hours-times">
                    <input
                      type="time"
                      aria-label={t('businessHours.openLabel')}
                      value={row.open_time}
                      onChange={e => updateHour(row.weekday, { open_time: e.target.value })}
                      required
                    />
                    <span className="business-hours-sep">–</span>
                    <input
                      type="time"
                      aria-label={t('businessHours.closeLabel')}
                      value={row.close_time}
                      onChange={e => updateHour(row.weekday, { close_time: e.target.value })}
                      required
                    />
                  </div>
                )}
                {/* No htmlFor/id here: the input is already nested inside the
                    label, which associates them implicitly. Adding an explicit
                    htmlFor pointing at the same nested input's id double-fires
                    the click in Chromium (once via the implicit nesting, once
                    via the explicit association), so the checkbox appears to
                    never toggle. */}
                <label className="business-hours-closed-toggle">
                  <input
                    type="checkbox"
                    checked={row.closed}
                    onChange={e => updateHour(row.weekday, { closed: e.target.checked })}
                  />
                  {t('businessHours.closedLabel')}
                </label>
              </div>
            ))}
          </div>
          <div className="toolbar mt-md">
            <button type="submit">{t('common.save')}</button>
          </div>
        </form>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>{t('businessHours.exceptionsTitle')}</h2>
        </div>
        <p className="hint">{t('businessHours.exceptionsHint')}</p>

        {exceptions.length === 0 ? (
          <p className="empty-state">{t('businessHours.exceptionsEmpty')}</p>
        ) : (
          <ul className="item-list">
            {exceptions.map(exc => (
              <li className="item-row" key={exc.date}>
                <div className="item-main">
                  <span className="item-title">
                    {formatExceptionDate(exc.date)}{exc.label ? ` — ${exc.label}` : ''}
                  </span>
                  <div className="item-meta">
                    {exc.closed ? (
                      <span className="badge badge-inactive">{t('businessHours.closedBadge')}</span>
                    ) : (
                      <span className="badge">{exc.open_time}–{exc.close_time}</span>
                    )}
                  </div>
                </div>
                <div className="item-actions">
                  <button className="btn-danger btn-small" onClick={() => removeException(exc.date)}>
                    {t('common.delete')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={submitException} className="mt-md">
          <div className="toolbar">
            <div className="field">
              <label htmlFor="exc-date">{t('common.date')}</label>
              <input
                id="exc-date"
                type="date"
                value={excForm.date}
                onChange={e => setExcForm(f => ({ ...f, date: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="exc-label">{t('businessHours.labelLabel')}</label>
              <input
                id="exc-label"
                value={excForm.label}
                onChange={e => setExcForm(f => ({ ...f, label: e.target.value }))}
                placeholder={t('businessHours.labelPlaceholder')}
              />
            </div>
            <div className="field checkbox-field">
              <input
                id="exc-closed"
                type="checkbox"
                checked={excForm.closed}
                onChange={e => setExcForm(f => ({ ...f, closed: e.target.checked }))}
              />
              <label htmlFor="exc-closed">{t('businessHours.closedLabel')}</label>
            </div>
          </div>
          {!excForm.closed && (
            <div className="toolbar">
              <div className="field">
                <label htmlFor="exc-open">{t('businessHours.openLabel')}</label>
                <input
                  id="exc-open"
                  type="time"
                  value={excForm.open_time}
                  onChange={e => setExcForm(f => ({ ...f, open_time: e.target.value }))}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="exc-close">{t('businessHours.closeLabel')}</label>
                <input
                  id="exc-close"
                  type="time"
                  value={excForm.close_time}
                  onChange={e => setExcForm(f => ({ ...f, close_time: e.target.value }))}
                  required
                />
              </div>
            </div>
          )}
          <button type="submit">{t('common.add')}</button>
        </form>
      </div>
    </>
  )
}

export default BusinessHours
