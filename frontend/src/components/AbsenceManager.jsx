import { useEffect, useState } from 'react'
import { api } from '../api'

const TYPE_LABELS = { sick: 'Krank', vacation: 'Urlaub' }

function currentMonthRange() {
  const now = new Date()
  const iso = d => d.toISOString().slice(0, 10)
  return {
    min: iso(new Date(now.getFullYear(), now.getMonth(), 1)),
    max: iso(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  }
}

/**
 * Self-service sick/vacation reporting for an employee's own account, for the
 * current month only (the server enforces the same restriction, so this is
 * just matching UX, not the actual guard).
 *
 * Deliberately decoupled from the generated schedule - it fetches its own
 * data and must work even before HR has generated this month's plan yet,
 * e.g. to pre-report a vacation day.
 */
function AbsenceManager({ employeeId, onChange, setFlash }) {
  const [absences, setAbsences] = useState([])
  const [loading, setLoading] = useState(true)
  const [date, setDate] = useState('')
  const [type, setType] = useState('sick')
  const [busy, setBusy] = useState(false)
  const { min, max } = currentMonthRange()

  async function load() {
    try {
      setAbsences(await api.get(`/employees/${employeeId}/absences`))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setLoading(false)
    }
  }

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  async function submit(e) {
    e.preventDefault()
    if (!date) return
    setBusy(true)
    try {
      const result = await api.post(`/employees/${employeeId}/absences`, { date, type })
      setFlash({
        type: 'success',
        text: result.freed_assignment_ids.length > 0
          ? `${TYPE_LABELS[type]} für ${date} eingetragen. Die Schicht an diesem Tag ist jetzt wieder frei.`
          : `${TYPE_LABELS[type]} für ${date} eingetragen.`,
      })
      setDate('')
      await load()
      onChange?.()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function cancel(entry) {
    if (!confirm(`${TYPE_LABELS[entry.type] || entry.type} für ${entry.date} wirklich zurücknehmen?`)) return
    try {
      await api.delete(`/employees/${employeeId}/absences/${entry.date}`)
      setFlash({ type: 'success', text: 'Eintrag entfernt.' })
      await load()
      onChange?.()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <div className="panel">
      <h3>Krank / Urlaub melden</h3>
      <p className="hint">
        Gilt nur für den laufenden Monat. Eine an diesem Tag bereits verplante Schicht wird automatisch
        freigegeben, damit die Personalabteilung eine Vertretung finden kann.
      </p>
      <form onSubmit={submit} className="toolbar">
        <div className="field">
          <label htmlFor="absence-date">Datum</label>
          <input
            id="absence-date"
            type="date"
            min={min}
            max={max}
            value={date}
            onChange={e => setDate(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="absence-type">Grund</label>
          <select id="absence-type" value={type} onChange={e => setType(e.target.value)}>
            <option value="sick">Krank</option>
            <option value="vacation">Urlaub</option>
          </select>
        </div>
        <button type="submit" disabled={busy}>{busy ? 'Speichern …' : 'Eintragen'}</button>
      </form>

      {!loading && absences.length > 0 && (
        <div className="item-meta mt-sm">
          {absences.map(a => (
            <span key={a.date} className="badge">
              {a.date} · {TYPE_LABELS[a.type] || a.type}
              <button type="button" className="badge-remove" onClick={() => cancel(a)}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default AbsenceManager
