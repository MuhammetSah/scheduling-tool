import { useEffect, useMemo, useState } from 'react'
import { TRANSLATIONS } from './translations'
import { DEFAULT_LANG, LANG_STORAGE_KEY, SUPPORTED_LANGS, getStoredLang } from './storage'
import { LanguageContext } from './context'

function lookup(dict, key) {
  return key.split('.').reduce((value, segment) => value?.[segment], dict)
}

/** Wraps the app once, near the root - see main.jsx. */
export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(getStoredLang)

  useEffect(() => {
    localStorage.setItem(LANG_STORAGE_KEY, lang)
    // Helps assistive tech and the browser's own translate/spellcheck pick
    // the right language for the page.
    document.documentElement.lang = lang
  }, [lang])

  function setLang(next) {
    setLangState(SUPPORTED_LANGS.includes(next) ? next : DEFAULT_LANG)
  }

  // t() looks up a dot-separated key ('nav.schedule') in the current
  // language, falling back to German and then the key itself so a missing
  // translation renders as *something* rather than crashing or going blank.
  // `vars` fills in any {placeholder} tokens in the template.
  const t = useMemo(() => (key, vars) => {
    const template = lookup(TRANSLATIONS[lang], key) ?? lookup(TRANSLATIONS[DEFAULT_LANG], key) ?? key
    if (!vars) return template
    return Object.entries(vars).reduce(
      (text, [name, value]) => text.replaceAll(`{${name}}`, value),
      template,
    )
  }, [lang])

  const value = useMemo(() => ({
    lang,
    setLang,
    t,
    weekdayLabels: TRANSLATIONS[lang].weekdayLabels,
    weekdayNames: TRANSLATIONS[lang].weekdayNames,
    monthNames: TRANSLATIONS[lang].monthNames,
    absenceLabels: TRANSLATIONS[lang].absenceLabels,
    dateLocale: TRANSLATIONS[lang].dateLocale,
  }), [lang, t])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}
