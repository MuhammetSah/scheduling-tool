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

async function zeigen() {
  api.get.mockResolvedValue([SCHICHTART])
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
