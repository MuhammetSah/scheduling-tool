import { useEffect } from 'react'
import { useTranslation } from './i18n/context'

// Wie lange eine Erfolgsmeldung stehen bleibt. Fehler und Warnungen laufen
// nicht ab - siehe unten.
const AUTO_DISMISS_MS = 6000

/**
 * Die eine Meldezeile der Anwendung.
 *
 * Drei Dinge, die beim Durchgehen als Nutzer aufgefallen sind:
 *
 * **Fehler verschwanden von selbst.** Jede Meldung wurde nach vier Sekunden
 * ausgeblendet, auch "Der Tausch würde die Ruhezeit unterschreiten". Wer in
 * dem Moment woandershin sieht, hat danach nur eine Schaltfläche, die nichts
 * tat, und erfährt nirgends warum. Erfolg darf gehen — er sagt nur, dass
 * geschehen ist, was man wollte. Fehler und Warnungen bleiben stehen, bis
 * jemand sie wegklickt. (SwapRequests.jsx hatte sich davon bereits eine eigene
 * Ausnahme gebaut; das ist der Befund, nur an der falschen Stelle behoben.)
 *
 * **Es gab keinen Weg, sie zu schließen.** `onClose` existierte, aber nur der
 * Zeitgeber rief es auf. Eine Meldung, die bleibt, braucht eine Schaltfläche.
 *
 * **Ein Screenreader las sie nie vor.** Ein `div`, das mitten im Baum
 * auftaucht, ist für die Bildschirmausgabe ein Ereignis und für die
 * Sprachausgabe keines. `role="alert"` für Fehler (unterbricht), `role="status"`
 * für alles andere (wartet auf eine Pause) — der Unterschied ist genau der
 * zwischen "das musst du jetzt wissen" und "zur Kenntnis".
 */
function Flash({ flash, onClose }) {
  const { t } = useTranslation()
  const bleibtStehen = flash?.type === 'error' || flash?.type === 'warning'

  useEffect(() => {
    if (!flash || bleibtStehen) return
    const timer = setTimeout(() => {
      onClose()
    }, AUTO_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [flash, bleibtStehen, onClose])

  if (!flash) return null

  return (
    <div
      className={`flash flash-${flash.type}`}
      role={flash.type === 'error' ? 'alert' : 'status'}
      aria-live={flash.type === 'error' ? 'assertive' : 'polite'}
    >
      <span className="flash-text">{flash.text}</span>
      <button
        type="button"
        className="flash-close"
        onClick={onClose}
        aria-label={t('common.dismissMessage')}
      >
        ×
      </button>
    </div>
  )
}

export default Flash
