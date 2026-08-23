import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import SwapRequests from './SwapRequests'
import { api } from '../api'

// Die Seite zeigt allen dieselbe Liste und blendet nur die Knöpfe ein, die der
// jeweils Lesende auch drücken darf. Die API entscheidet ohnehin selbst - aber
// ein Knopf, der zuverlässig 403 liefert, ist kein Knopf, sondern eine Falle.
// Genau das prüfen diese Tests, und die Gegenproben sind die eigentliche
// Arbeit: eine Seite, die gar keine Knöpfe zeigt, wäre sonst ebenfalls grün.

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

const ANNA = { id: 1, name: 'Anna' }
const BERTA = { id: 2, name: 'Berta' }

function antrag(abweichend = {}) {
  return {
    id: 7,
    status: 'pending',
    created_at: '2026-08-23 08:00:00',
    decided_at: null,
    requester: {
      employee_id: ANNA.id, name: 'Anna',
      shift: { id: 11, date: '2026-09-07', start_time: '06:00', end_time: '14:00',
               shift_type_name: 'Früh' },
    },
    partner: { employee_id: BERTA.id, name: 'Berta', shift: null },
    ...abweichend,
  }
}

async function zeigen(user, antraege = [antrag()]) {
  api.get.mockImplementation(pfad => {
    if (pfad === '/swap-requests') return Promise.resolve(antraege)
    if (pfad === '/colleagues') return Promise.resolve([ANNA, BERTA])
    return Promise.resolve({ assignments: [] })
  })
  await act(async () => {
    render(
      <LanguageProvider>
        <SwapRequests user={user} setFlash={() => {}} />
      </LanguageProvider>
    )
  })
}

describe('SwapRequests: wer welchen Knopf sieht', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('zeigt dem Tauschpartner Zustimmen und Ablehnen', async () => {
    await zeigen({ role: 'employee', employee_id: BERTA.id })

    expect(screen.getByRole('button', { name: 'Zustimmen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ablehnen' })).toBeInTheDocument()
  })

  it('zeigt dem Antragsteller nur Zurückziehen', async () => {
    await zeigen({ role: 'employee', employee_id: ANNA.id })

    expect(screen.getByRole('button', { name: 'Zurückziehen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zustimmen' })).not.toBeInTheDocument()
  })

  it('zeigt keinem Mitarbeiter den Genehmigen-Knopf', async () => {
    // Die Gegenprobe zum dritten Schritt: genehmigen darf nur die
    // Personalabteilung, weil das Arbeitszeitgesetz sich an den Arbeitgeber
    // richtet.
    await zeigen({ role: 'employee', employee_id: BERTA.id })

    expect(screen.queryByRole('button', { name: 'Genehmigen' })).not.toBeInTheDocument()
  })

  it('zeigt der Personalabteilung Genehmigen, aber gesperrt vor der Zustimmung', async () => {
    await zeigen({ role: 'hr', employee_id: null })

    expect(screen.getByRole('button', { name: 'Genehmigen' })).toBeDisabled()
  })

  it('gibt Genehmigen erst nach der Zustimmung frei', async () => {
    await zeigen({ role: 'hr', employee_id: null }, [antrag({
      status: 'accepted',
      partner: {
        employee_id: BERTA.id, name: 'Berta',
        shift: { id: 12, date: '2026-09-14', start_time: '06:00', end_time: '14:00',
                 shift_type_name: 'Früh' },
      },
    })])

    expect(screen.getByRole('button', { name: 'Genehmigen' })).toBeEnabled()
  })

  it('zeigt bei einem erledigten Antrag gar keine Knöpfe mehr', async () => {
    await zeigen({ role: 'hr', employee_id: null }, [antrag({ status: 'approved' })])

    expect(screen.queryByRole('button', { name: 'Genehmigen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nicht genehmigen' })).not.toBeInTheDocument()
  })

  it('nennt beide Seiten mit Namen und Zeiten', async () => {
    await zeigen({ role: 'hr', employee_id: null })

    expect(screen.getByText('Anna')).toBeInTheDocument()
    expect(screen.getByText(/2026-09-07/)).toBeInTheDocument()
  })
})
