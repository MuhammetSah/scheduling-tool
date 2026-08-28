// Ohne feste Zeitzone bewiese dieser Test nichts: in UTC verhalten sich die
// fehlerhafte und die richtige Fassung gleich, und CI laeuft in UTC. Der
// Fehler zeigt sich erst oestlich von Greenwich - deshalb hier die Zone, in
// der der Betrieb steht. Node liest TZ bei der naechsten Datumsoperation neu,
// also muss diese Zeile vor jedem Date stehen, und damit vor den Importen.
process.env.TZ = 'Europe/Berlin'

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import AbsenceManager from './AbsenceManager'
import { LanguageProvider } from '../i18n/LanguageContext'
import { api } from '../api'

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

function renderManager() {
  return render(
    <LanguageProvider>
      <AbsenceManager employeeId={1} onChange={() => {}} setFlash={() => {}} />
    </LanguageProvider>
  )
}

describe('AbsenceManager: die Grenzen des Datumsfeldes', () => {
  // Der Fehler, um den es hier geht, war unsichtbar, solange der Rechner in
  // UTC lief. Er zeigt sich erst oestlich von Greenwich - und der Betrieb
  // steht in Deutschland.
  beforeEach(() => {
    api.get.mockResolvedValue([])
    // Nur die Uhr, nicht die Zeitgeber: die Abfragehilfen von Testing Library
    // warten ueber setTimeout, und ein eingefrorener Zeitgeber laesst sie
    // in den Timeout laufen.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-15T10:00:00'))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('erlaubt den ersten und den letzten Tag des laufenden Monats', async () => {
    // Vorher lieferte toISOString() auf lokaler Mitternacht den Vortag in UTC:
    // min stand auf dem 31. Juli, den der Server ablehnt, und max auf dem
    // 30. August - eine Krankmeldung fuer den 31. August liess sich ueber
    // dieses Formular gar nicht eintragen.
    await act(async () => { renderManager() })

    const feld = screen.getByLabelText(/datum/i)
    expect(feld.getAttribute('min')).toBe('2026-08-01')
    expect(feld.getAttribute('max')).toBe('2026-08-31')
  })

  it('trifft auch einen Monat mit 30 Tagen', async () => {
    vi.setSystemTime(new Date('2026-09-15T10:00:00'))
    await act(async () => { renderManager() })

    const feld = screen.getByLabelText(/datum/i)
    expect(feld.getAttribute('min')).toBe('2026-09-01')
    expect(feld.getAttribute('max')).toBe('2026-09-30')
  })
})
