// Shared between LanguageContext.jsx (the React side) and api.js (a plain
// module that can't consume React context) so both agree on where the
// chosen language lives and what counts as a valid value.

export const LANG_STORAGE_KEY = 'schichtplan-lang'
export const DEFAULT_LANG = 'de'
export const SUPPORTED_LANGS = ['de', 'en']

export function getStoredLang() {
  if (typeof localStorage === 'undefined') return DEFAULT_LANG
  const stored = localStorage.getItem(LANG_STORAGE_KEY)
  return SUPPORTED_LANGS.includes(stored) ? stored : DEFAULT_LANG
}
