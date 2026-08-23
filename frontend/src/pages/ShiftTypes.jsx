import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

const emptyForm = {
  id: null,
  required: [],
  name: '',
  start_time: '08:00',
  end_time: '16:00',
  color: '#0d9488',
}

function ShiftTypes({ setFlash }) {
  const { t } = useTranslation()
  const [shiftTypes, setShiftTypes] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [qualifications, setQualifications] = useState([])
  const [newQualification, setNewQualification] = useState('')

  async function load() {
    try {
      const [types, nachweise] = await Promise.all([
        api.get('/shift-types'), api.get('/qualifications')])
      setShiftTypes(types)
      setQualifications(nachweise)
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
    setForm({
      id: st.id, name: st.name, start_time: st.start_time, end_time: st.end_time,
      color: st.color,
      required: (st.required_qualifications || []).map(q => q.qualification_id),
    })
    setShowForm(true)
  }

  async function submitForm(e) {
    e.preventDefault()
    const payload = { name: form.name, start_time: form.start_time, end_time: form.end_time, color: form.color }
    try {
      let ziel = form.id
      if (ziel) {
        await api.put(`/shift-types/${ziel}`, payload)
        setFlash({ type: 'success', text: t('shiftTypes.flashUpdated') })
      } else {
        ziel = (await api.post('/shift-types', payload)).id
        setFlash({ type: 'success', text: t('shiftTypes.flashCreated') })
      }
      // Eigene Route, wie bei den Mitarbeitern: die Anforderung ist eine
      // Liste, und sie in den Vorlagen-Rumpf zu falten machte die Vorlage
      // wieder zum Sammelbecken, das sie seit Etappe 5e nicht mehr ist.
      await api.put(`/shift-types/${ziel}/qualifications`,
                    { qualification_ids: form.required })
      setShowForm(false)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function addQualification(e) {
    e.preventDefault()
    try {
      await api.post('/qualifications', { name: newQualification })
      setNewQualification('')
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteQualification(id, name) {
    // Ausdrücklich benannt: der Nachweis verschwindet auch bei allen, die ihn
    // halten, und bei allen Schichten, die ihn verlangen. Eine Rückfrage, die
    // das verschweigt, ist keine.
    if (!confirm(t('shiftTypes.confirmDeleteQualification', { name }))) return
    try {
      await api.delete(`/qualifications/${id}`)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function toggleRequired(id) {
    setForm(f => ({
      ...f,
      required: f.required.includes(id)
        ? f.required.filter(x => x !== id)
        : [...f.required, id],
    }))
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
                    {(st.required_qualifications || []).map(q => (
                      <span key={q.qualification_id} className="badge">
                        {t('shiftTypes.requiresBadge', { name: q.name })}
                      </span>
                    ))}
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

      <div className="panel">
        <div className="panel-header">
          <h2>{t('shiftTypes.qualificationsTitle')}</h2>
        </div>
        <p className="hint">{t('shiftTypes.qualificationsHint')}</p>
        <form className="toolbar" onSubmit={addQualification}>
          <input
            value={newQualification}
            onChange={e => setNewQualification(e.target.value)}
            required
            aria-label={t('shiftTypes.qualificationNameAria')}
            placeholder={t('shiftTypes.qualificationPlaceholder')}
          />
          <button type="submit">{t('common.add')}</button>
        </form>
        {qualifications.length === 0 ? (
          <p className="empty-state">{t('shiftTypes.qualificationsEmpty')}</p>
        ) : (
          <ul className="item-list">
            {qualifications.map(q => (
              <li key={q.id} className="item-row">
                <span className="item-title">{q.name}</span>
                <div className="item-actions">
                  <button className="btn-danger btn-small"
                          onClick={() => deleteQualification(q.id, q.name)}>
                    {t('common.delete')}
                  </button>
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
            {qualifications.length > 0 && (
              <div className="field">
                <label>{t('shiftTypes.requiresLabel')}</label>
                <div className="weekday-picker">
                  {qualifications.map(q => (
                    <button
                      type="button"
                      key={q.id}
                      className={`weekday-chip ${form.required.includes(q.id) ? 'selected' : ''}`}
                      onClick={() => toggleRequired(q.id)}
                    >
                      {q.name}
                    </button>
                  ))}
                </div>
                <p className="hint">{t('shiftTypes.requiresHint')}</p>
              </div>
            )}
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
