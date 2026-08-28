import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import QualificationShortfalls from './QualificationShortfalls'

const EINTRAG = {
  shift_type_id: 1,
  shift_type_name: 'Frühdienst',
  date: '2026-09-01',
  slots: 3,
  eligible: 1,
  unfilled: 2,
  active_employees: 8,
  qualifications: ['Ersthelfer'],
  dates_affected: 22,
}

function zeigen(entries) {
  return render(
    <LanguageProvider>
      <QualificationShortfalls entries={entries} />
    </LanguageProvider>
  )
}

describe('QualificationShortfalls', () => {
  it('nennt Schichtart, Nachweis und beide Zahlen', () => {
    zeigen([EINTRAG])

    const zeile = screen.getByText(/Frühdienst/)
    expect(zeile).toBeInTheDocument()
    expect(zeile.textContent).toMatch(/Ersthelfer/)
    expect(zeile.textContent).toMatch(/1 von 8/)
    expect(zeile.textContent).toMatch(/22 Tagen/)
  })

  it('nennt mehrere Nachweise in einer Aufzaehlung', () => {
    zeigen([{ ...EINTRAG, qualifications: ['Ersthelfer', 'Staplerschein'] }])

    expect(screen.getByText(/Ersthelfer, Staplerschein/)).toBeInTheDocument()
  })

  it('sagt dazu, dass die Zahl nur eine Obergrenze ist', () => {
    // Ohne diesen Satz liest sich "1 von 8" als Versprechen: einer geht
    // schon. Urlaub, feste Zeiten und Arbeitszeitgrenzen koennen die Zahl
    // nur kleiner machen, und genau das steht da.
    zeigen([EINTRAG])

    expect(screen.getByText(/nur kleiner sein/)).toBeInTheDocument()
  })

  it('rendert nichts, wenn es nichts zu melden gibt', () => {
    const { container } = zeigen([])

    expect(container).toBeEmptyDOMElement()
  })

  it('rendert nichts, wenn das Feld fehlt', () => {
    // Die Ansicht eines Mitarbeiters bekommt qualification_shortfalls gar
    // nicht - wen der Betrieb nicht besetzt bekommt, ist nicht ihre Sache.
    const { container } = zeigen(undefined)

    expect(container).toBeEmptyDOMElement()
  })
})
