import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import SchedulePage from './pages/SchedulePage'
import Employees from './pages/Employees'
import ShiftTypes from './pages/ShiftTypes'
import Login from './pages/Login'
import Register from './pages/Register'
import Accounts from './pages/Accounts'
import SetPassword from './pages/SetPassword'
import Flash from './Flash'
import { api, UnauthorizedError } from './api'
import { useTranslation } from './i18n/context'
import './App.css'

function RequireAuth({ user, setupRequired, hrOnly = false, children }) {
  const location = useLocation()
  if (!user) {
    // On a brand new install there is nobody to log in as yet, so send the
    // first visitor to set up an account rather than to a login form.
    return (
      <Navigate
        to={setupRequired ? '/register' : '/login'}
        replace
        state={{ from: location.pathname }}
      />
    )
  }
  // Employee accounts only get the schedule; the API refuses the rest anyway.
  if (hrOnly && user.role !== 'hr') {
    return <Navigate to="/" replace />
  }
  return children
}

function LanguageToggle() {
  const { lang, setLang, t } = useTranslation()
  return (
    <div className="view-toggle" role="group" aria-label={t('nav.languageLabel')}>
      <button
        type="button"
        className={lang === 'de' ? 'active' : ''}
        onClick={() => setLang('de')}
      >
        DE
      </button>
      <button
        type="button"
        className={lang === 'en' ? 'active' : ''}
        onClick={() => setLang('en')}
      >
        EN
      </button>
    </div>
  )
}

function App() {
  const { t } = useTranslation()
  const [flash, setFlash] = useState(null)
  const [user, setUser] = useState(null)
  const [setupRequired, setSetupRequired] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)

  // Restores an existing session on load, and detects a fresh install that has
  // no accounts yet so the first visit lands on setup instead of a login wall.
  useEffect(() => {
    let cancelled = false
    api.get('/me')
      .then(me => {
        if (!cancelled) {
          setUser(me)
          setSetupRequired(false)
        }
      })
      .catch(err => {
        if (cancelled) return
        setUser(null)
        if (err instanceof UnauthorizedError) {
          setSetupRequired(Boolean(err.data?.setup_required))
        } else {
          // Couldn't even ask the server whether an account exists yet - a
          // network/config problem, not "no session". Leaving setupRequired
          // at its default here would silently make /register bounce back to
          // /login, which looks exactly like a dead link instead of what it
          // actually is: the app not being able to reach its API.
          setFlash({ type: 'error', text: err.message })
        }
      })
      .finally(() => {
        if (!cancelled) setCheckingSession(false)
      })
    return () => { cancelled = true }
  }, [])

  const isHr = user?.role === 'hr'

  function handleLoggedIn(loggedInUser) {
    setUser(loggedInUser)
    setSetupRequired(false)
  }

  async function handleLogout() {
    try {
      await api.post('/logout', {})
    } catch {
      // Clearing local state matters more than the response here.
    }
    setUser(null)
    setFlash({ type: 'success', text: t('nav.loggedOutFlash') })
  }

  return (
    <BrowserRouter>
      <div className="app">
        <div className="glow-bg" aria-hidden="true" />
        <nav className="navbar">
          <NavLink to="/" className="navbar-brand">{t('nav.brand')}</NavLink>
          <div className="navbar-right">
            {user ? (
              <>
                <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>{t('nav.schedule')}</NavLink>
                {isHr && (
                  <>
                    <NavLink to="/employees" className={({ isActive }) => isActive ? 'active' : ''}>{t('nav.employees')}</NavLink>
                    <NavLink to="/shift-types" className={({ isActive }) => isActive ? 'active' : ''}>{t('nav.shiftTypes')}</NavLink>
                    <NavLink to="/register" className={({ isActive }) => isActive ? 'active' : ''}>{t('nav.accounts')}</NavLink>
                  </>
                )}
                <button onClick={handleLogout}>{t('nav.logout', { username: user.username })}</button>
              </>
            ) : (
              <NavLink to="/login" className={({ isActive }) => isActive ? 'active' : ''}>{t('nav.login')}</NavLink>
            )}
            <LanguageToggle />
          </div>
        </nav>

        <Flash flash={flash} onClose={() => setFlash(null)} />

        <main className={`page ${user ? 'page-wide' : ''}`}>
          {checkingSession ? (
            <p className="hint">{t('common.loading')}</p>
          ) : (
            <Routes>
              <Route path="/" element={
                <RequireAuth user={user} setupRequired={setupRequired}>
                  <SchedulePage setFlash={setFlash} user={user} />
                </RequireAuth>
              } />
              <Route path="/employees" element={
                <RequireAuth user={user} setupRequired={setupRequired} hrOnly>
                  <Employees setFlash={setFlash} />
                </RequireAuth>
              } />
              <Route path="/shift-types" element={
                <RequireAuth user={user} setupRequired={setupRequired} hrOnly>
                  <ShiftTypes setFlash={setFlash} />
                </RequireAuth>
              } />
              {/* Public: the token from the invitation email is the credential. */}
              <Route path="/set-password" element={<SetPassword setFlash={setFlash} />} />
              <Route path="/login" element={
                user ? <Navigate to="/" replace />
                     : <Login onLoggedIn={handleLoggedIn} setFlash={setFlash} />
              } />
              <Route path="/register" element={
                // Open to everyone only while no account exists yet; afterwards
                // it becomes HR's account management screen.
                setupRequired
                  ? <Register isSetup currentUser={null} onLoggedIn={handleLoggedIn} setFlash={setFlash} />
                  : isHr
                    ? <Accounts currentUser={user} setFlash={setFlash} />
                    : <Navigate to={user ? '/' : '/login'} replace />
              } />
              <Route path="*" element={<Navigate to={user ? '/' : (setupRequired ? '/register' : '/login')} replace />} />
            </Routes>
          )}
        </main>
        <footer className="footer">
          <p>{t('nav.footer')}</p>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
