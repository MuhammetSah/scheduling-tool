import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import AverageHours from './AverageHours'

const EINTRAG = {
  employee_id: 1,
  employee_name: 'Anna',
  hours_worked: 1300,
  hours_allowed: 1152,
  average_per_working_day: 9.0,
}

function zeigen(entries) {
  return render(
    <LanguageProvider>
      <AverageHours entries={entries} />
    </LanguageProvider>
  )
}

describe('AverageHours', () => {
  it('nennt Name, Schnitt und die beiden Stundenzahlen', () => {
    zeigen([EINTRAG])

    expect(screen.getByText(/Anna/)).toBeInTheDocument()
    expect(screen.getByText(/9/)).toBeInTheDocument()
    expect(screen.getByText(/1152/)).toBeInTheDocument()
  })

  it('rendert nichts, wenn niemand ueber der Grenze liegt', () => {
    // Dieselbe Zurueckhaltung wie CoverageGaps: eine leere Ueberschrift ueber
    // einer leeren Liste waere schlechter als gar nichts.
    const { container } = zeigen([])

    expect(container).toBeEmptyDOMElement()
  })

  it('rendert nichts, wenn das Feld fehlt', () => {
    // Die Ansicht eines Mitarbeiters bekommt average_hours gar nicht - sie
    // sieht nur die eigenen Schichten.
    const { container } = zeigen(undefined)

    expect(container).toBeEmptyDOMElement()
  })

  it('sagt, dass zehn Stunden zulaessig sind, wenn der Schnitt stimmt', () => {
    // Die Formulierung ist Absicht: die Liste meldet eine Bedingung, die
    // gerade nicht erfuellt ist, kein ertapptes Vergehen.
    zeigen([EINTRAG])

    expect(screen.getByText(/zulässig/)).toBeInTheDocument()
  })
})
