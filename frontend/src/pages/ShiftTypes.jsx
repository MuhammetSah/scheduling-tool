import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

const emptyForm = {
  id: null,
  name: '',
  start_time: '08:00',
  end_time: '16:00',
  color: '#0d9488',
  // Der Planer liest diese Zahlen seit Etappe 4 nicht mehr - Bedarf wird ueber
  // /coverage-requirements gepflegt. Sie bleiben trotzdem im Formular und im
  // Payload: das Backend speichert sie weiter, und sie beim Speichern
  // stillschweigend auf 0 zu setzen wuerde die Rueckfallebene zerstoeren, die
  // die Spec bis nach Etappe 4 ausdruecklich erhalten wissen will.
  requirements: [1, 1, 1, 1, 1, 1, 1],
}

function ShiftTypes({ setFlash }) {
  const { t } = useTranslation()
  const [shiftTypes, setShiftTypes] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)

  async function load() {
    try {
      setShiftTypes(await api.get('/shift-types'))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function startCreate() {
    setForm(emptyForm)
    setShowForm(true)
  }

  function startEdit(st) {
    setForm({ id: st.id, name: st.name, start_time: st.start_time, end_time: st.end_time, color: st.color, requirements: [...st.requirements] })
    setShowForm(true)
  }

  async function submitForm(e) {
    e.preventDefault()
    const payload = { name: form.name, start_time: form.start_time, end_time: form.end_time, color: form.color, requirements: form.requirements }
    try {
      if (form.id) {
        await api.put(`/shift-types/${form.id}`, payload)
        setFlash({ type: 'success', text: t('shiftTypes.flashUpdated') })
      } else {
        await api.post('/shift-types', payload)
        setFlash({ type: 'success', text: t('shiftTypes.flashCreated') })
      }
      setShowForm(false)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteShiftType(id) {
    if (!confirm(t('shiftTypes.confirmDelete'))) return
    try {
      const result = await api.delete(`/shift-types/${id}`)
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>{t('shiftTypes.title')}</h2>
          <button onClick={startCreate}>{t('shiftTypes.newButton')}</button>
        </div>

        {shiftTypes.length === 0 ? (
          <p className="empty-state">{t('shiftTypes.empty')}</p>
        ) : (
          <ul className="item-list">
            {shiftTypes.map(st => (
              <li key={st.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">
                    <span className="badge-dot" style={{ backgroundColor: st.color }} /> {st.name}
                  </span>
                  <div className="item-meta">
                    <span className="badge">{st.start_time}–{st.end_time}</span>
                  </div>
                </div>
                <div className="item-actions">
                  <button className="btn-secondary btn-small" onClick={() => startEdit(st)}>{t('common.edit')}</button>
                  <button className="btn-danger btn-small" onClick={() => deleteShiftType(st.id)}>{t('common.delete')}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showForm && (
        <div className="panel">
          <h3>{form.id ? t('shiftTypes.editTitle') : t('shiftTypes.newTitle')}</h3>
          <form onSubmit={submitForm}>
            <div className="field">
              <label htmlFor="st-name">{t('common.name')}</label>
              <input id="st-name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required placeholder={t('shiftTypes.namePlaceholder')} />
            </div>
            <div className="toolbar">
              <div className="field">
                <label htmlFor="st-start">{t('shiftTypes.startLabel')}</label>
                <input id="st-start" type="time" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} required />
              </div>
              <div className="field">
                <label htmlFor="st-end">{t('shiftTypes.endLabel')}</label>
                <input id="st-end" type="time" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} required />
              </div>
              <div className="field">
                <label htmlFor="st-color">{t('shiftTypes.colorLabel')}</label>
                <input id="st-color" type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} />
              </div>
            </div>
            <p className="hint">{t('shiftTypes.demandMovedHint')}</p>
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

export default ShiftTypes
