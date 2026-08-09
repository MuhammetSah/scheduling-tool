// Where the bearer token from login/register is kept. Needed alongside the
// session cookie because Safari/WebKit's Intelligent Tracking Prevention
// drops cross-site cookies (frontend and API are on two different domains)
// even when they're correctly SameSite=None - see app.py's comment above
// AUTH_TOKEN_MAX_AGE_SECONDS for the full story. A plain module, like
// i18n/storage.js, so api.js (which can't use React state) can read it too.

const AUTH_TOKEN_STORAGE_KEY = 'schichtplan-auth-token'

export function getAuthToken() {
  if (typeof localStorage === 'undefined') return null
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
}

export function setAuthToken(token) {
  if (typeof localStorage === 'undefined' || !token) return
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export function clearAuthToken() {
  if (typeof localStorage === 'undefined') return
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}
