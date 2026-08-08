import { createContext, useContext } from 'react'

// Split out from LanguageContext.jsx (which owns the Provider component)
// purely because a file exporting both a component and a hook breaks React
// Fast Refresh - see the eslint react-refresh/only-export-components rule.
export const LanguageContext = createContext(null)

/** The translation function plus everything language-dependent a component
 * might need: t(), the current lang/setLang, and the weekday/month/absence
 * label sets (moved here from api.js, since they now vary at runtime). */
export function useTranslation() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useTranslation must be used within a LanguageProvider')
  return ctx
}
