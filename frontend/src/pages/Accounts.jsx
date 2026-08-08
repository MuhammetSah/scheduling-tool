import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Register from './Register'
import { useTranslation } from '../i18n/context'

/**
 * HR's view of who can sign in. Deleting an account is the way to revoke a
 * login - and it is also the first step before an employee can be removed from
 * the roster, since a login without a roster entry could never show anything.
 */
function Accounts({ currentUser, setFlash }) {
  const { t } = useTranslation()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setAccounts(await api.get('/accounts'))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setLoading(false)
    }
  }, [setFlash])

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load() }, [load])

  async function resendInvitation(account) {
    try {
      const result = await api.post(`/accounts/${account.id}/invitation`, {})
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteAccount(account) {
    if (!confirm(t('accounts.confirmDelete', { username: account.username }))) return
    try {
      const result = await api.delete(`/accounts/${account.id}`)
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <>
      <div className="panel">
        <h2>{t('accounts.title')}</h2>
        <p className="hint">{t('accounts.hint')}</p>

        {loading ? (
          <p className="hint">{t('common.loading')}</p>
        ) : accounts.length === 0 ? (
          <p className="empty-state">{t('accounts.empty')}</p>
        ) : (
          <ul className="item-list">
            {accounts.map(account => (
              <li key={account.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">
                    {account.username}
                    {account.id === currentUser.id && <span className="badge">{t('accounts.youBadge')}</span>}
                  </span>
                  <div className="item-meta">
                    <span className="badge">
                      {account.role === 'hr' ? t('common.roleHr') : t('common.roleEmployee')}
                    </span>
                    {account.employee_name && (
                      <span className="badge">{t('accounts.linkedWith', { name: account.employee_name })}</span>
                    )}
                    {account.contact_email && <span className="badge">{account.contact_email}</span>}
                    {account.invitation_pending && (
                      <span className="badge badge-pending">{t('accounts.invitationPending')}</span>
                    )}
                    {!account.password_set && !account.invitation_pending && (
                      <span className="badge badge-inactive">{t('accounts.noPasswordSet')}</span>
                    )}
                  </div>
                </div>
                <div className="item-actions">
                  {account.contact_email && account.id !== currentUser.id && (
                    <button
                      className="btn-secondary btn-small"
                      title={t('accounts.resendTitle')}
                      onClick={() => resendInvitation(account)}
                    >
                      {account.password_set ? t('accounts.resetPassword') : t('accounts.resendInvite')}
                    </button>
                  )}
                  <button
                    className="btn-danger btn-small"
                    disabled={account.id === currentUser.id}
                    title={account.id === currentUser.id ? t('accounts.cannotDeleteSelf') : undefined}
                    onClick={() => deleteAccount(account)}
                  >
                    {t('common.delete')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Register currentUser={currentUser} isSetup={false} setFlash={setFlash} onAccountCreated={load} />
    </>
  )
}

export default Accounts
