import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import ShiftTypes from './ShiftTypes'
import { api } from '../api'

// Seit Etappe 4 plant der Generator aus den Bedarfsbaendern
// (coverage_requirements), nicht mehr aus den Wochentagszahlen der Schichtart.
// Die Felder stehen zu lassen hiesse, ein Formular anzubieten, das Eingaben
// annimmt und verwirft - genau das Muster, das im Handoff als Fallstrick 12
// steht. Die Schichtart bleibt Vorlage: Name, Zeiten, Farbe.

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

const SCHICHTART = {
  id: 1,
  name: 'Frühschicht',
  start_time: '06:00',
  end_time: '14:00',
  color: '#3366cc',
}

async function zeigen(nachweise = []) {
  // Nach Pfad, nicht pauschal: seit Etappe 10 laedt die Seite zusaetzlich den
  // Nachweiskatalog, und eine Zusage, die auf jeden Pfad dieselbe Liste
  // liefert, zeigte die Schichtarten ein zweites Mal als Nachweise an.
  api.get.mockImplementation(pfad => Promise.resolve(
    pfad === '/qualifications' ? nachweise : [SCHICHTART]))
  let ergebnis
  await act(async () => {
    ergebnis = render(
      <LanguageProvider>
        <ShiftTypes setFlash={() => {}} />
      </LanguageProvider>
    )
  })
  return ergebnis
}

describe('ShiftTypes ohne Bedarfszahlen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('zeigt die Wochentagszahlen nicht mehr in der Liste', async () => {
    await zeigen()

    expect(screen.queryByText(/Mo: 3/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Sa: 0/)).not.toBeInTheDocument()
  })

  it('zeigt Zeiten und Namen weiterhin', async () => {
    // Die Gegenprobe: ohne sie waere eine Umsetzung gruen, die die ganze
    // Liste nicht mehr rendert.
    await zeigen()

    expect(screen.getByText('Frühschicht')).toBeInTheDocument()
    expect(screen.getByText('06:00–14:00')).toBeInTheDocument()
  })

  it('nennt im Formular den Ort, an dem der Bedarf jetzt gepflegt wird', async () => {
    // Der Hinweis steht dort, wo jemand das verschwundene Feld suchen wuerde.
    await zeigen()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Neue Schichtart/i }))
    })

    expect(screen.getByText(/Bedarf/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Mo$/)).not.toBeInTheDocument()
  })
})

describe('ShiftTypes mit Nachweisen', () => {
  // Seit Etappe 10 kann eine Schichtart einen Nachweis verlangen. Die
  // Anforderung gehoert zur Arbeit, nicht zur Person - das Gegenstueck zu
  // allowed_shift_types, das umgekehrt an der Person haengt.
  const NACHWEIS = { id: 7, name: 'Ersthelfer' }

  beforeEach(() => { vi.clearAllMocks() })

  it('zeigt den Katalog', async () => {
    await zeigen([NACHWEIS])

    expect(screen.getByText('Ersthelfer')).toBeInTheDocument()
  })

  it('meldet einen leeren Katalog, statt ihn zu verschweigen', async () => {
    await zeigen([])

    expect(screen.getByText(/Noch keine Nachweise/)).toBeInTheDocument()
  })

  it('zeigt an der Schichtart, was sie verlangt', async () => {
    api.get.mockImplementation(pfad => Promise.resolve(
      pfad === '/qualifications'
        ? [NACHWEIS]
        : [{ ...SCHICHTART, required_qualifications: [{ qualification_id: 7, name: 'Ersthelfer' }] }]))
    await act(async () => {
      render(
        <LanguageProvider>
          <ShiftTypes setFlash={() => {}} />
        </LanguageProvider>
      )
    })

    expect(screen.getByText(/braucht Ersthelfer/)).toBeInTheDocument()
  })

  it('zeigt ohne Anforderung kein Abzeichen', async () => {
    // Gegenprobe: sonst stuende an jeder Schichtart etwas, und die eine mit
    // einer echten Anforderung ginge darin unter.
    await zeigen([NACHWEIS])

    expect(screen.queryByText(/braucht /)).not.toBeInTheDocument()
  })
})
