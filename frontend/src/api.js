import { getStoredLang } from './i18n/storage'

const API_URL = import.meta.env.VITE_API_URL

/** Thrown when the API rejects a request because nobody is signed in. */
export class UnauthorizedError extends Error {}

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
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
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data?.message || `Request failed (${response.status})`
    if (response.status === 401) {
      const error = new UnauthorizedError(message)
      error.data = data
      throw error
    }
    throw new Error(message)
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
