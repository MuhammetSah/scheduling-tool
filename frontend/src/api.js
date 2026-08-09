import { getStoredLang, DEFAULT_LANG } from './i18n/storage'
import { TRANSLATIONS } from './i18n/translations'
import { getAuthToken, setAuthToken, clearAuthToken } from './auth'

// .replace() rather than a bare passthrough: a VITE_API_URL with a trailing
// slash (an easy typo - e.g. pasted straight from a browser's address bar)
// combined with every call site's leading-slash path (request('/me') below)
// produced a double slash, e.g. https://host//me. Browsers refuse to follow
// a redirect on a CORS preflight, and Werkzeug's routing issues exactly that
// redirect to merge the doubled slash - so every single request failed at
// the network level, indistinguishably from a CORS/host misconfiguration.
// backend/mailer.py's build_invitation() already guards APP_BASE_URL the
// same way; this mirrors it on the frontend side.
const API_URL = import.meta.env.VITE_API_URL?.replace(/\/+$/, '')

/** Thrown when the API rejects a request because nobody is signed in. */
export class UnauthorizedError extends Error {}

// A plain module, not a component, so it can't use useTranslation() - this
// mirrors that hook's {placeholder} substitution against the same
// dictionary, just triggered from getStoredLang() directly.
function apiMessage(key, vars) {
  const lang = getStoredLang()
  const template = TRANSLATIONS[lang]?.api?.[key] ?? TRANSLATIONS[DEFAULT_LANG].api[key]
  if (!vars) return template
  return Object.entries(vars).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), template)
}

async function request(path, options = {}) {
  // Without this the app would silently call a *relative* "undefined/..."
  // URL - which, behind a SPA rewrite like frontend/vercel.json's, gets
  // served the frontend's own index.html with a 200 status instead of ever
  // reaching a backend. That used to fail completely silently (see below);
  // failing loudly here is what actually surfaces a missing/forgotten
  // VITE_API_URL instead of every request just quietly doing nothing.
  if (!API_URL) {
    throw new Error(apiMessage('missingApiUrl'))
  }

  // Belt-and-suspenders alongside the session cookie below: Safari/WebKit's
  // Intelligent Tracking Prevention drops cross-site cookies even when
  // they're correctly configured, since the frontend and this API are on two
  // different domains. A bearer token isn't a cookie, so ITP has no opinion
  // about it - see backend/app.py's AUTH_TOKEN_MAX_AGE_SECONDS comment for
  // the full story. auth.js is the only other file that touches this token.
  const token = getAuthToken()

  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        // Read directly from storage rather than through React context - this
        // is a plain module, not a component, so it can't use useTranslation().
        // LanguageContext writes to the same key on every change, so this is
        // always the language the user currently has selected.
        'X-Lang': getStoredLang(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      // Sends the session cookie; without it every guarded route answers 401.
      // Still worth sending even though it isn't the only auth channel
      // anymore - it's what makes same-site/local-dev usage work without a
      // token at all.
      credentials: 'include',
      ...options,
    })
  } catch {
    // fetch() itself rejected - DNS failure, connection refused, CORS block,
    // etc. - meaning the backend never answered at all, not just with an
    // error status. Previously this surfaced as a generic, uncategorized
    // error that callers checking `instanceof UnauthorizedError` silently
    // treated as "no session" instead of "couldn't find out" - see App.jsx's
    // initial /me check for where that mattered.
    throw new Error(apiMessage('unreachable', { url: API_URL }))
  }

  let data = null
  let parseFailed = false
  try {
    data = await response.json()
  } catch {
    parseFailed = true
  }

  if (!response.ok) {
    const message = data?.message || `Request failed (${response.status})`
    if (response.status === 401) {
      // Whatever token we were sending didn't work (missing, expired, or the
      // account behind it is gone) - drop it rather than keep resending a
      // dead credential on every request until the next login.
      clearAuthToken()
      const error = new UnauthorizedError(message)
      error.data = data
      throw error
    }
    throw new Error(message)
  }

  if (parseFailed) {
    // A *successful* status that isn't JSON is not this API - almost always
    // a misconfigured VITE_API_URL landing back on this frontend's own
    // static host (see the SPA-rewrite note above), not a real 2xx from Flask.
    throw new Error(apiMessage('unexpectedResponse'))
  }

  // Only /login and /register's first-account path ever set this, but
  // checking here - rather than in every caller - means neither can forget to.
  if (data?.auth_token) {
    setAuthToken(data.auth_token)
  }

  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
