import { getStoredLang, DEFAULT_LANG } from './i18n/storage'
import { TRANSLATIONS } from './i18n/translations'

const API_URL = import.meta.env.VITE_API_URL

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
      },
      // Sends the session cookie; without it every guarded route answers 401.
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

  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
