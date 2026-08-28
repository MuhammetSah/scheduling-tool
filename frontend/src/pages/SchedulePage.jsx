import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import ScheduleGrid from '../components/ScheduleGrid'
import CalendarView from '../components/CalendarView'
import Distribution from '../components/Distribution'
import CoverageGaps from '../components/CoverageGaps'
import AverageHours from '../components/AverageHours'
import AbsenceManager from '../components/AbsenceManager'
import { useTranslation } from '../i18n/context'

function currentMonthKey() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function SchedulePage({ setFlash, user }) {
  const { t, monthNames } = useTranslation()
  const [ym, setYm] = useState(currentMonthKey())
  const [schedule, setSchedule] = useState(null)
  const [employees, setEmployees] = useState([])
  const [shiftTypes, setShiftTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [setup, setSetup] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [swapSelection, setSwapSelection] = useState(null)
  const [view, setView] = useState('calendar')
  const [emptyMessage, setEmptyMessage] = useState('')
  // Off by default: evening out weekend duty specifically can cost a little of
  // the overall balance (see README), so it's an opt-in rather than always-on.
  const [weekendEquity, setWeekendEquity] = useState(false)

  const [year, month] = ym.split('-').map(Number)
  // Employee accounts read the plan; only HR may change it.
  const canEdit = user?.role === 'hr'

  async function loadStaticData() {
    try {
      // Shift types drive the columns for everyone, but the roster is HR-only -
      // an employee is shown their own shifts and never needs the staff list.
      const types = await api.get('/shift-types')
      setShiftTypes(types)
      if (user?.role === 'hr') {
        setEmployees(await api.get('/employees'))
        // Was dem Betrieb noch fehlt, bevor ein Plan entstehen kann. Nur für
        // HR: ein Mitarbeiter kann nichts davon ändern, und die API lehnt es
        // ohnehin ab.
        setSetup(await api.get('/setup-status'))
      }
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Liefert immer { data, message }: data ist der Plan oder null, message die
  // Auskunft des Servers, warum es keinen gibt.
  async function fetchSchedule() {
    try {
      return { data: await api.get(`/schedules/${year}/${month}`), message: '' }
    } catch (err) {
      // Nur ein echtes "kein Plan fuer diesen Monat" wird als null behandelt -
      // das ist ausschliesslich das 404, das GET /schedules/<year>/<month>
      // liefert (backend/app.py: no_schedule_generated_yet). Jeder andere
      // Fehlschlag (500, Netzwerkausfall, CORS) muss als Fehler sichtbar
      // werden: fiele er hier auch auf null, sähe die Seite "kein Plan fuer
      // diesen Monat" fuer einen Monat, der in Wirklichkeit einen hat -
      // generate() ueberspringt dann seine Rueckfrage vor dem Ueberschreiben
      // eines bestehenden Plans (siehe dort), und ohne Handkorrekturen
      // darauf hat auch der Server nichts, worauf er ein 409 stuetzen koennte.
      // Die Meldung wird zurueckgegeben statt hier gesetzt: seit dem
      // Veroeffentlichen-Workflow sind "es gibt keinen Plan" und "der Plan ist
      // noch nicht veroeffentlicht" zwei verschiedene Auskuenfte, und beide
      // kommen als 404. Gesetzt wird sie beim Aufrufer - diese Funktion wird
      // synchron aus einem Effekt heraus gerufen, und setState gehoert dort
      // in den .then()-Zweig.
      if (err.status === 404) return { data: null, message: err.message || '' }
      throw err
    }
  }

  async function setStatus(status) {
    try {
      setSchedule(await api.put(`/schedules/${year}/${month}/status`, { status }))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function publish() {
    setStatus('published')
  }

  function withdraw() {
    // Nachfragen: das Zurueckziehen nimmt allen die Sicht auf ihren Plan.
    if (!confirm(t('schedule.withdrawConfirm'))) return
    setStatus('draft')
  }

  async function refreshSchedule() {
    try {
      const { data, message } = await fetchSchedule()
      setSchedule(data)
      setEmptyMessage(message)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the await inside loadStaticData(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { loadStaticData() }, [])

  // Loading/warnings/selection are reset in handleMonthChange (the event that
  // causes them), so this effect only ever sets state inside .then()/.catch().
  useEffect(() => {
    let cancelled = false
    fetchSchedule()
      .then(({ data, message }) => {
        if (cancelled) return
        setSchedule(data)
        setEmptyMessage(message)
      })
      .catch(err => { if (!cancelled) setFlash({ type: 'error', text: err.message }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ym])

  function handleMonthChange(newYm) {
    setYm(newYm)
    setLoading(true)
    // Ohne das haengt bis zum Ende des Fetches oben noch der Plan des vorigen
    // Monats im State - ein Klick auf "Neu erzeugen" waehrend dieser Luecke
    // wuerde dann faelschlich gegen den alten Monat pruefen/generieren.
    setSchedule(null)
    setEmptyMessage('')
    setWarnings([])
    setSwapSelection(null)
  }

  // Der Parameter heißt bewusst nicht `confirm`: das würde window.confirm
  // innerhalb dieser Funktion verdecken, und genau die brauchen wir unten.
  async function generate(bestaetigt = false) {
    if (shiftTypes.length === 0) {
      setFlash({ type: 'error', text: t('schedule.needShiftTypeFlash') })
      return
    }
    // Zwei getrennte Rückfragen für zwei unterschiedliche Risiken, aber nie
    // beide auf einen Klick: Hat der geladene Plan Handkorrekturen, weiß das
    // hier nur der Server (der 409 unten trägt die genaue Anzahl) - diese
    // lokale Frage überspringen wir dann, sonst kämen zwei Dialoge
    // hintereinander. Hat er keine, kann der Server das nicht mehr melden
    // (nichts zu verlieren), also fragen wir hier vorab: ein bereits
    // erzeugter Plan wird sonst wortlos ersetzt, z. B. durch einen
    // versehentlichen Doppelklick.
    const hatHandkorrekturen = schedule?.assignments?.some(a => a.manually_edited)
    if (schedule && !hatHandkorrekturen && !window.confirm(t('schedule.confirmRegenerateExisting'))) {
      return
    }
    try {
      const data = await api.post('/schedules/generate', {
        year,
        month,
        weekend_weight: weekendEquity ? 5 : 0,
        ...(bestaetigt ? { confirm: true } : {}),
      })
      setSchedule(data)
      setWarnings([])
      // Der Hinweis geht vor: ein leerer Plan ohne Bedarfsband meldet null
      // Lücken und sähe sonst wie ein voller Erfolg aus.
      setFlash(data.notice
        ? { type: 'warning', text: data.notice }
        : {
            type: data.unfilled_count > 0 ? 'error' : 'success',
            text: data.unfilled_count > 0
              ? t('schedule.generatedWithGapsFlash', { n: data.unfilled_count })
              : t('schedule.generatedFullFlash'),
          })
    } catch (err) {
      // Der Plan enthält Handkorrekturen - einmal nachfragen, dann bestätigt
      // wiederholen. err.data trägt manually_edited_count aus der Antwort.
      if (err.data?.manually_edited_count) {
        const weiter = window.confirm(
          t('schedule.confirmRegenerate', { n: err.data.manually_edited_count }))
        return weiter ? generate(true) : undefined
      }
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function exportCsv() {
    try {
      await api.download(`/schedules/${year}/${month}/export.csv`,
                         `schichtplan-${year}-${String(month).padStart(2, '0')}.csv`)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function exportIcal() {
    // Die eigenen Schichten. HR sieht den ganzen Plan, laedt sich aber
    // sinnvollerweise seinen eigenen Kalender - fuer fremde gibt es die Route
    // ebenfalls, nur keinen Knopf dafuer.
    const employeeId = schedule?.linked_employee_id ?? user?.employee_id
    if (!employeeId) {
      setFlash({ type: 'error', text: t('schedule.icalNeedsEmployee') })
      return
    }
    try {
      await api.download(
        `/employees/${employeeId}/schedule.ics?year=${year}&month=${month}`,
        `schichtplan-${year}-${String(month).padStart(2, '0')}.ics`)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteSchedule() {
    if (!window.confirm(t('schedule.confirmDelete'))) return
    try {
      const result = await api.delete(`/schedules/${year}/${month}`)
      setSchedule(null)
      // Sonst stuende im leeren Zustand noch die Auskunft von vorhin - etwa
      // "noch nicht veroeffentlicht" fuer einen Plan, den es gar nicht mehr gibt.
      setEmptyMessage('')
      setFlash({ type: 'success', text: result.message })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // start_time/end_time are written on every PUT /assignments/<id> call - the
  // backend clears them to NULL when they're absent from the body, the same
  // "missing means empty" rule it applies to employee_id. So every caller of
  // reassign() must pass the time pair it wants kept, not just a new
  // employee: the assignment's current individual times to preserve them
  // across a plain reassignment, freshly edited values to change them, or
  // null/null to drop back to the shift's own hours. No defaults here on
  // purpose: a future two-argument call (`reassign(id, employeeId)`) would
  // silently wipe individual times instead of failing loudly, so
  // startTime/endTime are required - every call site must decide.
  async function reassign(assignmentId, employeeIdRaw, startTime, endTime, breakMinutes = null,
                          breakStart = null) {
    const employeeId = employeeIdRaw === '' ? null : Number(employeeIdRaw)
    try {
      // break_minutes travels with every call for the same reason the times
      // do: PUT /assignments/<id> writes the whole row, so leaving it out
      // clears it. null is not a loss here - it means "the legal minimum
      // again" - but it is still a silent change to what was stored.
      const result = await api.put(`/assignments/${assignmentId}`, {
        employee_id: employeeId,
        start_time: startTime,
        end_time: endTime,
        break_minutes: breakMinutes,
        // Wie die Zeiten und die Dauer: die Route schreibt die ganze Zeile,
        // ein ausgelassenes Feld wird geleert.
        break_start: breakStart,
      })
      setWarnings(result.warnings || [])
      await refreshSchedule()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function doSwap(idA, idB) {
    try {
      const result = await api.post('/assignments/swap', { assignment_id_a: idA, assignment_id_b: idB })
      setWarnings(result.warnings || [])
      await refreshSchedule()
      setFlash({ type: 'success', text: result.message })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function setTimes(date, shiftTypeId, startTime, endTime) {
    try {
      const result = await api.put(`/schedules/${year}/${month}/shift-times`, {
        date,
        shift_type_id: shiftTypeId,
        start_time: startTime,
        end_time: endTime,
      })
      await refreshSchedule()
      setFlash({ type: 'success', text: result.message })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function addSlot(date, shiftTypeId) {
    try {
      await api.post(`/schedules/${year}/${month}/slots`, { date, shift_type_id: shiftTypeId })
      await refreshSchedule()
      setFlash({ type: 'success', text: t('schedule.slotAddedFlash') })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function removeSlot(assignmentId) {
    try {
      const result = await api.delete(`/assignments/${assignmentId}`)
      await refreshSchedule()
      setFlash({ type: 'success', text: result.message })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // HR logging an absence on someone's behalf (e.g. they called in sick and
  // don't use self-service) - same endpoint the employee's own AbsenceManager
  // calls, just without the current-month restriction that only applies there.
  async function reportAbsence(employeeId, dateStr, type) {
    try {
      const result = await api.post(`/employees/${employeeId}/absences`, { date: dateStr, type })
      await refreshSchedule()
      setFlash({
        type: 'success',
        text: result.freed_assignment_ids.length > 0
          ? t('schedule.absenceReportedFreedFlash')
          : t('schedule.absenceReportedFlash'),
      })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function toggleSwapSelect(assignmentId) {
    if (swapSelection === assignmentId) {
      setSwapSelection(null)
    } else if (swapSelection === null) {
      setSwapSelection(assignmentId)
    } else {
      doSwap(swapSelection, assignmentId)
      setSwapSelection(null)
    }
  }

  return (
    <>
      {/* Nur solange wirklich etwas fehlt. Eine Tafel, die immer da ist, ist
          Möblierung; eine, die verschwindet, ist eine Antwort. Die Hinweise
          (Bundesland) stehen daneben, nicht darin — sie verhindern nichts. */}
      {canEdit && setup && (!setup.ready || setup.notes.length > 0) && (
        <div className="panel">
          {!setup.ready && (
            <>
              <div className="panel-header">
                <h2>{t('setup.title')}</h2>
              </div>
              <p className="hint">{t('setup.intro')}</p>
              <ul className="item-list">
                {setup.missing.map(eintrag => (
                  <li key={eintrag.key} className="item-row">
                    <span className="item-main">{eintrag.text}</span>
                    <div className="item-actions">
                      <Link className="btn-secondary btn-small" to={eintrag.route}>
                        {t('setup.goThere')}
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {/* Die Hinweise überleben das Fertigwerden. Sie hingen bisher
              innerhalb derselben Bedingung wie die Mängelliste und
              verschwanden mit ihr — ausgerechnet in dem Moment, in dem sie
              zählen: „für vier von vier Mitarbeitenden sind keine
              Wochenstunden hinterlegt" ist die Auskunft, die man beim ersten
              fertigen Plan braucht, nicht die, die man vorher kurz sieht.
              Ein Mangel verschwindet, wenn er behoben ist; ein Hinweis
              verschwindet, wenn er nicht mehr zutrifft — und das entscheidet
              der Server, nicht diese Bedingung. */}
          {setup.notes.length > 0 && (
            <p className="hint">
              {setup.notes.map(hinweis => hinweis.text).join(' ')}
            </p>
          )}
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <h2>{t('schedule.title')}</h2>
          <div className="toolbar">
            <div className="field">
              <label htmlFor="month-picker">{t('schedule.monthLabel')}</label>
              <input id="month-picker" type="month" value={ym} onChange={e => handleMonthChange(e.target.value)} />
            </div>
            {canEdit && (
              <>
                <div className="field checkbox-field">
                  <input
                    id="weekend-equity"
                    type="checkbox"
                    checked={weekendEquity}
                    onChange={e => setWeekendEquity(e.target.checked)}
                  />
                  <label htmlFor="weekend-equity" title={t('schedule.weekendEquityTitle')}>
                    {t('schedule.weekendEquityLabel')}
                  </label>
                </div>
                {/* generate() darf hier nicht direkt als Handler stehen: onClick
                    reicht das Klick-Event durch, das als erstes Argument sonst
                    `bestaetigt` waer und faelschlich als "confirm: true" zaehlt. */}
                <button onClick={() => generate()} disabled={loading}>{schedule ? t('schedule.regenerateButton') : t('schedule.generateButton')}</button>
                {schedule && <button type="button" className="btn-secondary" onClick={exportCsv}>{t('schedule.exportCsvButton')}</button>}
                {schedule && <button type="button" className="btn-danger" onClick={deleteSchedule}>{t('schedule.deleteButton')}</button>}
              </>
            )}
          </div>
        </div>

        {schedule && (
          <div className="toolbar">
            {/* aria-pressed, nicht nur die Klasse "active": welche Seite
                gewaehlt ist, stand bisher ausschliesslich in der Farbe. Eine
                Sprachausgabe las hier zwei gleichwertige Schaltflaechen vor,
                ohne zu sagen, welche gerade gilt - und ohne role/aria-label
                nicht einmal, dass sie zusammengehoeren. */}
            <div className="view-toggle" role="group" aria-label={t('schedule.viewToggleLabel')}>
              <button
                type="button"
                aria-pressed={view === 'calendar'}
                className={view === 'calendar' ? 'active' : ''}
                onClick={() => setView('calendar')}
              >
                {t('schedule.calendarView')}
              </button>
              <button
                type="button"
                aria-pressed={view === 'table'}
                className={view === 'table' ? 'active' : ''}
                onClick={() => setView('table')}
              >
                {t('schedule.tableView')}
              </button>
            </div>
          </div>
        )}

        {loading && <p className="hint">{t('common.loading')}</p>}

        {!loading && !schedule && (
          <p className="empty-state">
            {emptyMessage || (
              <>
                {t('schedule.noScheduleYet', { month: monthNames[month - 1], year })}
                {!canEdit && t('schedule.noScheduleEmployeeHint')}
              </>
            )}
          </p>
        )}

        {!loading && schedule && (
          <>
            {canEdit && (
              <div className="schedule-publish">
                <span className={`badge ${schedule.status === 'published' ? '' : 'badge-pending'}`}>
                  {schedule.status === 'published'
                    ? t('schedule.publishedBadge')
                    : t('schedule.draftBadge')}
                </span>
                {schedule.status === 'published' ? (
                  <button type="button" className="btn-secondary btn-small" onClick={withdraw}>
                    {t('schedule.withdrawButton')}
                  </button>
                ) : (
                  <button type="button" className="btn-small" onClick={publish}>
                    {t('schedule.publishButton')}
                  </button>
                )}
                <span className="hint">
                  {schedule.status === 'published'
                    ? t('schedule.publishedHint')
                    : t('schedule.draftHint')}
                </span>
              </div>
            )}

            <div className="schedule-summary">
              {/* Nur bei veroeffentlichtem Plan: der Export liefert einen
                  Entwurf ohnehin nicht aus, und ein Knopf, der verlaesslich
                  einen Fehler erzeugt, ist schlechter als keiner. */}
              {user?.employee_id && schedule.status === 'published' && (
                <button type="button" className="btn-secondary btn-small" onClick={exportIcal}>
                  {t('schedule.exportIcalButton')}
                </button>
              )}
              <span className="badge">
                {schedule.scope === 'own'
                  ? t('schedule.ownShiftsBadge', { n: schedule.assignments.length })
                  : t('schedule.totalShiftsBadge', { n: schedule.assignments.length })}
              </span>
              {schedule.scope !== 'own' && (
                schedule.unfilled_count > 0 ? (
                  <span className="badge badge-inactive">{t('schedule.unfilledBadge', { n: schedule.unfilled_count })}</span>
                ) : (
                  <span className="badge">{t('schedule.fullyStaffedBadge')}</span>
                )
              )}
              {schedule.distribution && (
                <>
                  <span className="badge">{t('schedule.spreadBadge', { n: schedule.distribution.spread })}</span>
                  <span className="badge">{t('schedule.weekendSpreadBadge', { n: schedule.distribution.weekend_spread })}</span>
                </>
              )}
            </div>

            {schedule.distribution && <Distribution distribution={schedule.distribution} />}

            {schedule.coverage_gaps && <CoverageGaps gaps={schedule.coverage_gaps} />}
            {schedule.average_hours && <AverageHours entries={schedule.average_hours} />}

            {warnings.length > 0 && (
              <div className="warning-list">
                {t('schedule.lastChangeWarningsTitle')}
                <ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </div>
            )}

            {schedule.scope === 'own' && (
              <p className="hint">{t('schedule.ownShiftsHint', { month: monthNames[month - 1], year })}</p>
            )}

            {view === 'table' && canEdit && (
              <p className="hint">
                {t('schedule.tableHintBase')}
                {swapSelection && t('schedule.tableHintSwapSelected')}.
              </p>
            )}

            {view === 'calendar' ? (
              <div className="calendar-wrap">
                <CalendarView
                  schedule={schedule}
                  shiftTypes={shiftTypes}
                  highlightEmployeeId={user?.employee_id ?? null}
                />
              </div>
            ) : (
              <ScheduleGrid
                schedule={schedule}
                employees={employees}
                shiftTypes={shiftTypes}
                readOnly={!canEdit}
                onReassign={reassign}
                swapSelection={swapSelection}
                onToggleSwap={toggleSwapSelect}
                onSetTimes={setTimes}
                onAddSlot={addSlot}
                onRemoveSlot={removeSlot}
                onReportAbsence={reportAbsence}
                setFlash={setFlash}
              />
            )}
          </>
        )}
      </div>

      {/* Self-service only makes sense for the month it's actually restricted
          to server-side - showing it while browsing a different month would
          be misleading, since it can never act on that month anyway.

          Aber wortlos zu verschwinden ist die andere Hälfte des Fehlers: wer
          einen Monat weiterblättert, sieht die Tafel weggehen und liest das
          als Fehler der Seite, nicht als Regel. Deshalb steht an ihrer Stelle
          eine Zeile, die sagt, warum sie fort ist und wie sie wiederkommt. */}
      {user?.employee_id && (
        ym === currentMonthKey() ? (
          <AbsenceManager employeeId={user.employee_id} onChange={refreshSchedule} setFlash={setFlash} />
        ) : (
          <div className="panel">
            <h3>{t('absences.title')}</h3>
            <p className="hint">
              {t('absences.otherMonthHint')}{' '}
              <button type="button" className="btn-secondary btn-small"
                      onClick={() => handleMonthChange(currentMonthKey())}>
                {t('absences.backToCurrentMonth')}
              </button>
            </p>
          </div>
        )
      )}
    </>
  )
}

export default SchedulePage
