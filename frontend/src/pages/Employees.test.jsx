import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import Employees from './Employees'
import { api } from '../api'

// Ein abgelaufenes Arbeitszeitfenster stand in der Liste wie ein gueltiges.
// Der Generator wertet valid_from/valid_until aus und plant die Person an dem
// Tag nicht ein - die Liste behauptete also eine Verfuegbarkeit, die es nicht
// gab. Beides zu zeigen waere ehrlicher als nur eines, aber ein Abzeichen ohne
// Zeitraum ist kein Ort dafuer; die Bearbeitungsansicht zeigt die Grenzen.

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), download: vi.fn() },
}))

function fenster(abweichend = {}) {
  return {
    weekday: 0, start_time: '08:00', end_time: '16:00',
    valid_from: null, valid_until: null, ...abweichend,
  }
}

function person(availability) {
  return {
    id: 1, name: 'Anna', email: 'anna@example.com', active: true,
    max_shifts_per_month: null, weekly_hours: null, min_rest_hours: null,
    max_daily_hours: 10, availability_mode: 'windows', availability,
    unavailable_weekdays: [], unavailable_dates: [], allowed_shift_types: [],
  }
}

async function zeigen(availability) {
  api.get.mockImplementation(pfad => Promise.resolve(
    pfad === '/employees' ? [person(availability)] : []))
  await act(async () => {
    render(
      <LanguageProvider>
        <Employees setFlash={() => {}} />
      </LanguageProvider>
    )
  })
}

describe('Employees: Fenster-Abzeichen', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('zeigt ein Fenster ohne Grenzen', async () => {
    await zeigen([fenster()])

    expect(screen.getByText(/08:00–16:00/)).toBeInTheDocument()
  })

  it('zeigt ein abgelaufenes Fenster nicht', async () => {
    await zeigen([fenster({ valid_until: '2020-01-01' })])

    expect(screen.queryByText(/08:00–16:00/)).not.toBeInTheDocument()
  })

  it('zeigt ein noch nicht begonnenes Fenster nicht', async () => {
    await zeigen([fenster({ valid_from: '2099-01-01' })])

    expect(screen.queryByText(/08:00–16:00/)).not.toBeInTheDocument()
  })

  it('meldet, dass heute kein Fenster gilt, wenn alle abgelaufen sind', async () => {
    // Sonst steht die Person ohne Abzeichen da und liest sich wie jemand, bei
    // dem gerade nichts angezeigt wird - statt wie jemand, den der Generator
    // nicht einplanen kann.
    await zeigen([fenster({ valid_until: '2020-01-01' })])

    expect(screen.getByText(/Kein Fenster gilt heute|No window applies today/i))
      .toBeInTheDocument()
  })

  it('meldet "keine Fenster hinterlegt" nur, wenn wirklich keine da sind', async () => {
    // Gegenprobe: die beiden Meldungen duerfen nicht dieselbe werden. Wer
    // Fenster hinterlegt hat, die heute nicht greifen, muss eine Grenze
    // aendern - nicht ein Fenster anlegen.
    await zeigen([fenster({ valid_until: '2020-01-01' })])

    expect(screen.queryByText(/keine Fenster hinterlegt|no windows set/i))
      .not.toBeInTheDocument()
  })
})
