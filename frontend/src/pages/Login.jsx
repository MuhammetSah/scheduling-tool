import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

function Login({ onLoggedIn, setFlash }) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const user = await api.post('/login', { username, password })
      onLoggedIn(user)
      setFlash({ type: 'success', text: t('login.welcomeBack', { username: user.username }) })
      navigate('/')
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel panel-narrow">
      <h2>{t('login.title')}</h2>
      <p className="hint">{t('login.subtitle')}</p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="login-username">{t('common.username')}</label>
          <input
            id="login-username"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">{t('common.password')}</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" disabled={busy}>{busy ? t('login.submitBusy') : t('login.submit')}</button>
      </form>
      <p className="hint mt-md">
        {t('login.noAccountPrefix')} <Link to="/register">{t('login.setupLink')}</Link>
      </p>
    </div>
  )
}

export default Login
