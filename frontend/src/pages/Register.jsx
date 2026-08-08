import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

/**
 * Used twice: to create the very first account on a fresh install, and by a
 * signed-in user to add a colleague. `isSetup` tells the two apart so the
 * wording matches what the person is actually doing.
 */
function Register({ isSetup, currentUser, onLoggedIn, setFlash, onAccountCreated }) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('employee')
  const [employeeId, setEmployeeId] = useState('')
  const [employees, setEmployees] = useState([])
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  // Every account created by somebody else is invited, so the creator never
  // picks the password. Only the very first account sets one here.
  const invitesByEmail = Boolean(currentUser)
  const selectedEmployee = employees.find(e => String(e.id) === String(employeeId))
  // For an employee account the address is normally the one on the roster
  // entry, but HR can type/correct it right here too (see the email field
  // below) - only genuinely missing on both sides blocks the invitation.
  const employeeMissingEmail = role === 'employee' && selectedEmployee && !selectedEmployee.email && !email
  const invitationTarget = role === 'employee' ? (email || selectedEmployee?.email) : email

  function selectEmployee(id) {
    setEmployeeId(id)
    // Show whatever address is already on file for the newly picked person,
    // rather than leaving a previous selection's typed address showing.
    const emp = employees.find(e => String(e.id) === id)
    setEmail(emp?.email || '')
  }

  // Only HR can link a new read-only account to a roster entry.
  useEffect(() => {
    if (!currentUser) return
    let cancelled = false
    api.get('/employees')
      .then(list => { if (!cancelled) setEmployees(list) })
      .catch(() => { /* the link is optional, so a failure here is not fatal */ })
    return () => { cancelled = true }
  }, [currentUser])

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      // Employee accounts never receive a password here - they are invited by
      // email and choose their own, so HR cannot know it.
      const payload = invitesByEmail ? { username } : { username, password }
      if (email) payload.email = email
      if (currentUser) {
        payload.role = role
        if (role === 'employee' && employeeId) {
          payload.employee_id = Number(employeeId)
        }
      }
      const user = await api.post('/register', payload)
      if (currentUser) {
        // An existing user stays signed in as themselves after adding someone.
        setFlash({
          type: 'success',
          text: user.invitation_email
            ? (user.invitation_sent
                ? t('register.flashInvited', { email: user.invitation_email })
                : t('register.flashInvitedLogged', { email: user.invitation_email }))
            : t('register.flashCreatedNoInvite', { username: user.username }),
        })
        setUsername('')
        setPassword('')
        setEmail('')
        setEmployeeId('')
        onAccountCreated?.()
      } else {
        onLoggedIn(user)
        setFlash({ type: 'success', text: t('register.flashSetupWelcome', { username: user.username }) })
        navigate('/')
      }
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`panel ${currentUser ? '' : 'panel-narrow'}`}>
      <h2>{currentUser ? t('register.titleAddColleague') : t('register.titleSetup')}</h2>
      <p className="hint">
        {currentUser ? t('register.hintAddColleague') : t('register.hintSetup')}
      </p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="register-username">{t('common.username')}</label>
          <input
            id="register-username"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </div>
        {!invitesByEmail && (
          <div className="field">
            <label htmlFor="register-password">{t('common.password')}</label>
            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
            <p className="hint">{t('common.minPasswordHint')}</p>
          </div>
        )}
        {!currentUser && (
          <div className="field">
            <label htmlFor="setup-email">{t('register.emailOptionalLabel')}</label>
            <input
              id="setup-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <p className="hint">{t('register.emailOptionalHint')}</p>
          </div>
        )}
        {currentUser && (
          <>
            <div className="field">
              <label htmlFor="register-role">{t('register.roleLabel')}</label>
              <select id="register-role" value={role} onChange={e => setRole(e.target.value)}>
                <option value="employee">{t('register.roleEmployeeOption')}</option>
                <option value="hr">{t('register.roleHrOption')}</option>
              </select>
            </div>
            {role === 'employee' && (
              <>
                <div className="field">
                  <label htmlFor="register-employee">{t('register.linkEmployeeLabel')}</label>
                  <select
                    id="register-employee"
                    value={employeeId}
                    onChange={e => selectEmployee(e.target.value)}
                    required
                  >
                    <option value="">{t('common.pleaseSelect')}</option>
                    {employees.map(emp => (
                      <option key={emp.id} value={emp.id}>{emp.name}</option>
                    ))}
                  </select>
                  <p className="hint">{t('register.linkEmployeeHint')}</p>
                </div>
                {employeeId && (
                  <div className="field">
                    <label htmlFor="register-employee-email">{t('register.employeeEmailLabel')}</label>
                    <input
                      id="register-employee-email"
                      type="email"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      required
                    />
                    <p className="hint">{t('register.employeeEmailHint')}</p>
                  </div>
                )}
              </>
            )}
            {role === 'hr' && (
              <div className="field">
                <label htmlFor="register-email">{t('register.hrEmailLabel')}</label>
                <input
                  id="register-email"
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                />
                <p className="hint">{t('register.hrEmailHint')}</p>
              </div>
            )}
            <div className="field">
              {employeeMissingEmail ? (
                <p className="warning-list">
                  {t('register.employeeMissingEmailWarning', { name: selectedEmployee.name })}
                </p>
              ) : (
                <p className="hint">
                  {t('register.noPasswordPrefix')}{' '}
                  {invitationTarget
                    ? <>{t('register.invitationAtTarget')} <strong>{invitationTarget}</strong></>
                    : t('register.invitationByEmail')}
                  {' '}{t('register.noPasswordSuffix')}
                </p>
              )}
            </div>
          </>
        )}
        <button type="submit" disabled={busy || employeeMissingEmail}>
          {busy ? t('common.savingEllipsis') : (invitesByEmail ? t('register.submitInvite') : t('register.submitSetup'))}
        </button>
      </form>
      {!currentUser && !isSetup && (
        <p className="hint mt-md">
          {t('register.alreadyRegisteredPrefix')} <Link to="/login">{t('common.toLogin')}</Link>
        </p>
      )}
    </div>
  )
}

export default Register
