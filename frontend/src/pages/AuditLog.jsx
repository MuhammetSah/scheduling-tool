import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

/**
 * The change log: who touched what, and when.
 *
 * Deliberately raw. Each row is a request - method, path, status - not a
 * sentence, because that is what the log records: it says *that* something was
 * changed and by whom, not what it was changed to. Dressing it up as prose
 * would suggest a narrative the entries do not carry. The reason it stops
 * there is in the backend: a narrative log would have to store request bodies,
 * and those contain sick notes, which are health data under Art. 9 GDPR.
 */
function AuditLog({ setFlash }) {
  const { t, dateLocale } = useTranslation()
  const [entries, setEntries] = useState([])

  async function load() {
    try {
      setEntries(await api.get('/audit-log'))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the await inside load().
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function formatAt(at) {
    // Der Server schreibt naive UTC-Zeitstempel (siehe record_audit_entry) -
    // das Z macht daraus fuer den Browser wieder eine Zeitzone.
    const d = new Date(`${at.replace(' ', 'T')}Z`)
    return Number.isNaN(d.getTime()) ? at : d.toLocaleString(dateLocale)
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{t('auditLog.title')}</h2>
      </div>
      <p className="hint">{t('auditLog.hint')}</p>

      {entries.length === 0 ? (
        <p className="empty-state">{t('auditLog.empty')}</p>
      ) : (
        <div className="schedule-table-wrap">
          <table className="schedule-table">
            <thead>
              <tr>
                <th>{t('auditLog.atHeader')}</th>
                <th>{t('auditLog.userHeader')}</th>
                <th>{t('auditLog.actionHeader')}</th>
                <th>{t('auditLog.statusHeader')}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr key={i}>
                  <td>{formatAt(entry.at)}</td>
                  <td>{entry.username || t('auditLog.anonymous')}</td>
                  <td><code>{entry.method} {entry.path}</code></td>
                  <td className={entry.status >= 400 ? 'cell-times-overridden' : ''}>
                    {entry.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default AuditLog
