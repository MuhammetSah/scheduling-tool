import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

// Drei Schritte, und jeder gehört jemand anderem: der Antragsteller bietet
// eine eigene Schicht an und nennt eine Kollegin oder einen Kollegen, der
// Partner stimmt zu und wählt dabei selbst, welche seiner Schichten er dagegen
// gibt, die Personalabteilung genehmigt.
//
// Dass der Partner seine Schicht selbst wählt, ist keine Bequemlichkeit: ein
// Mitarbeiter sieht ausschließlich seine eigenen Schichten (Etappe 5f). Ihn
// eine fremde auswählen zu lassen hieße, ihm zuerst den Dienstplan aller
// anderen zu zeigen.
//
// Diese Seite zeigt allen dieselbe Liste und blendet nur die Knöpfe ein, die
// der jeweils Lesende auch drücken darf — die API entscheidet ohnehin selbst,
// aber ein Knopf, der zuverlässig 403 liefert, ist kein Knopf, sondern eine
// Falle.

const OFFEN = new Set(['pending', 'accepted'])

function Schicht({ shift, t, nochOffen }) {
  // Zwei verschiedene Sachverhalte, und beim Bauen zuerst zusammengeworfen:
  // solange niemand zugestimmt hat, ist die Gegenschicht noch nicht GEWÄHLT;
  // danach kann sie ENTFALLEN sein, weil die Zuweisung gelöscht wurde. Eine
  // Meldung für beides erzählt im ersten Fall etwas Falsches.
  if (!shift) {
    return (
      <span className="muted">
        {nochOffen ? t('swaps.shiftNotChosenYet') : t('swaps.shiftGone')}
      </span>
    )
  }
  const zeiten = shift.start_time && shift.end_time
    ? `${shift.start_time}–${shift.end_time}`
    : t('swaps.noTimes')
  return (
    <span>
      {shift.date} · {zeiten}
      {shift.shift_type_name ? ` · ${shift.shift_type_name}` : ''}
    </span>
  )
}

function SwapRequests({ user, setFlash }) {
  const { t } = useTranslation()
  const [requests, setRequests] = useState([])
  const [myShifts, setMyShifts] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [chosenShift, setChosenShift] = useState({})
  const [colleagues, setColleagues] = useState([])
  const [offer, setOffer] = useState({ assignmentId: '', partnerId: '' })
  const [blockers, setBlockers] = useState({})

  async function laden() {
    try {
      // Dieser und der kommende Monat. Getauscht wird fast immer nach vorn,
      // und am Monatsende stünde sonst gar nichts zur Auswahl. Weiter zu
      // gehen hieße, die Monatsgrenze des ganzen Werkzeugs hier einseitig
      // aufzuweichen — ein 404 heißt schlicht "für den Monat gibt es keinen
      // Plan" und ist kein Fehler.
      const heute = new Date()
      const monate = [
        [heute.getFullYear(), heute.getMonth() + 1],
        [heute.getMonth() === 11 ? heute.getFullYear() + 1 : heute.getFullYear(),
         heute.getMonth() === 11 ? 1 : heute.getMonth() + 2],
      ]
      const [antraege, kollegen, ...plaene] = await Promise.all([
        api.get('/swap-requests'),
        api.get('/colleagues').catch(() => []),
        ...monate.map(([j, m]) => api.get(`/schedules/${j}/${m}`).catch(() => null)),
      ])
      setRequests(antraege)
      setColleagues(kollegen.filter(k => k.id !== user?.employee_id))
      setMyShifts(plaene.flatMap(plan =>
        (plan?.assignments || []).filter(a => a.employee_id === user?.employee_id)))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setLoading(false)
    }
  }

  // Mount-only fetch; setState happens after the await inside laden().
  // Dieselbe Form wie in AuditLog.jsx - siehe den Kommentar dort.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { laden() }, [])

  async function setzeStand(id, status, myAssignmentId = undefined) {
    setBusy(id)
    try {
      const result = await api.put(`/swap-requests/${id}/status`,
                                   myAssignmentId ? { status, my_assignment_id: myAssignmentId }
                                                  : { status })
      setBlockers(b => ({ ...b, [id]: undefined }))
      const erledigt = t('swaps.done', { status: t(`swaps.status.${status}`) })
      // Die Hinweise hängen an dieselbe Meldung, statt eine zweite zu setzen:
      // zwei setFlash() nacheinander zeigen nur die letzte, und das wäre
      // ausgerechnet die, ohne die niemand weiß, dass es geklappt hat.
      setFlash(result.warnings?.length
        ? { type: 'warning', text: `${erledigt} ${result.warnings.join(' · ')}` }
        : { type: 'success', text: erledigt })
      await laden()
    } catch (err) {
      // Die Ablehnung aus Rechtsgründen bleibt am Antrag stehen, statt als
      // Flash-Meldung nach vier Sekunden zu verschwinden. Beim Prüfen im
      // Browser aufgefallen: wer den Hinweis verpasst, sieht danach nur noch
      // einen Antrag, der sich nicht bewegt, und erfährt nirgends warum.
      const gruende = err.data?.blockers
      if (gruende?.length) {
        setBlockers(b => ({ ...b, [id]: { message: err.message, gruende } }))
      } else {
        setFlash({ type: 'error', text: err.message })
      }
    } finally {
      setBusy(null)
    }
  }

  async function antragStellen(event) {
    event.preventDefault()
    setBusy('neu')
    try {
      await api.post('/swap-requests', {
        my_assignment_id: Number(offer.assignmentId),
        partner_employee_id: Number(offer.partnerId),
      })
      setOffer({ assignmentId: '', partnerId: '' })
      setFlash({ type: 'success', text: t('swaps.requested') })
      await laden()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(null)
    }
  }

  const istHr = user?.role === 'hr'
  const meineId = user?.employee_id ?? null

  if (loading) return <p className="muted">{t('common.loading')}</p>

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{t('swaps.title')}</h2>
      </div>
      <p className="hint">{t('swaps.hint')}</p>

      {myShifts.length > 0 && (
        <form className="toolbar" onSubmit={antragStellen}>
          {/* aria-label statt eines sichtbaren Labels, wie im Bedarfseditor:
              die erste Option benennt das Feld bereits, ein zweites Mal
              danebengeschrieben wäre Rauschen - aber ein Screenreader liest
              die Option erst nach der Auswahl vor. */}
          <select aria-label={t('swaps.myShift')} required value={offer.assignmentId}
                  onChange={e => setOffer(o => ({ ...o, assignmentId: e.target.value }))}>
            <option value="">{t('swaps.myShift')}</option>
            {myShifts.map(s => (
              <option key={s.id} value={s.id}>
                {s.date} · {s.start_time}–{s.end_time}
              </option>
            ))}
          </select>
          <select aria-label={t('swaps.partner')} required value={offer.partnerId}
                  onChange={e => setOffer(o => ({ ...o, partnerId: e.target.value }))}>
            <option value="">{t('swaps.partner')}</option>
            {colleagues.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
          <button type="submit" disabled={busy === 'neu'}>{t('swaps.request')}</button>
        </form>
      )}

      {requests.length === 0 && <p className="muted">{t('swaps.empty')}</p>}

      {requests.map(antrag => {
        const binPartner = meineId !== null && meineId === antrag.partner.employee_id
        const binAntragsteller = meineId !== null && meineId === antrag.requester.employee_id
        const offen = OFFEN.has(antrag.status)
        return (
          <div key={antrag.id} className="list-row">
            <div>
              <strong>{antrag.requester.name}</strong>{' '}
              <Schicht shift={antrag.requester.shift} t={t} />
              {' ⇄ '}
              <strong>{antrag.partner.name}</strong>{' '}
              <Schicht shift={antrag.partner.shift} t={t}
                       nochOffen={antrag.status === 'pending'} />
              <div>
                <span className={`badge badge-${antrag.status}`}>
                  {t(`swaps.status.${antrag.status}`)}
                </span>
              </div>
              {blockers[antrag.id] && (
                <div className="flash flash-error" role="alert">
                  <strong>{blockers[antrag.id].message}</strong>
                  <ul>
                    {blockers[antrag.id].gruende.map((grund, i) => <li key={i}>{grund}</li>)}
                  </ul>
                </div>
              )}
            </div>
            <div className="toolbar">
              {offen && antrag.status === 'pending' && binPartner && (
                <>
                  <select
                    aria-label={t('swaps.chooseOwnShift')}
                    value={chosenShift[antrag.id] || ''}
                    onChange={e => setChosenShift(s => ({ ...s, [antrag.id]: e.target.value }))}
                  >
                    <option value="">{t('swaps.chooseOwnShift')}</option>
                    {myShifts.map(s => (
                      <option key={s.id} value={s.id}>
                        {s.date} · {s.start_time}–{s.end_time}
                      </option>
                    ))}
                  </select>
                  <button type="button"
                          disabled={busy === antrag.id || !chosenShift[antrag.id]}
                          onClick={() => setzeStand(antrag.id, 'accepted',
                                                    Number(chosenShift[antrag.id]))}>
                    {t('swaps.accept')}
                  </button>
                  <button type="button" className="btn-secondary" disabled={busy === antrag.id}
                          onClick={() => setzeStand(antrag.id, 'declined')}>
                    {t('swaps.decline')}
                  </button>
                </>
              )}
              {offen && antrag.status === 'pending' && binAntragsteller && (
                <button type="button" className="btn-secondary" disabled={busy === antrag.id}
                        onClick={() => setzeStand(antrag.id, 'withdrawn')}>
                  {t('swaps.withdraw')}
                </button>
              )}
              {offen && istHr && (
                <>
                  <button type="button" disabled={busy === antrag.id || antrag.status !== 'accepted'}
                          title={antrag.status !== 'accepted' ? t('swaps.needsConsent') : undefined}
                          onClick={() => setzeStand(antrag.id, 'approved')}>
                    {t('swaps.approve')}
                  </button>
                  <button type="button" className="btn-danger" disabled={busy === antrag.id}
                          onClick={() => setzeStand(antrag.id, 'rejected')}>
                    {t('swaps.reject')}
                  </button>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default SwapRequests
