import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { LanguageProvider } from '../i18n/LanguageContext'
import SchedulePage from './SchedulePage'
import { api } from '../api'

// Der erste Tag auf einer leeren Datenbank: mit einer Schichtart, aber ohne
// Bedarfsband erzeugt "Plan generieren" einen leeren Plan. Das Backend sagt
// seit Etappe 11, warum - und diese Meldung muss auch ankommen. Ohne sie sieht
// ein leerer Plan mit null Luecken aus wie ein voller Erfolg.

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), download: vi.fn() },
}))

const HR = { id: 1, username: 'hr', role: 'hr', employee_id: null }

function leererPlan(abweichend = {}) {
  return {
    id: 1, year: 2026, month: 11, status: 'draft', published_at: null,
    assignments: [], absences: [], unfilled_count: 0, scope: 'all',
    ...abweichend,
  }
}

async function zeigen(setFlash) {
  // Kein Plan vorhanden: fetchSchedule() unterscheidet ein echtes 404 von
  // jedem anderen Fehler (siehe api.js), also genau so nachgebildet.
  const nichtGefunden = Object.assign(new Error('kein Plan'), { status: 404 })
  api.get.mockImplementation(pfad => {
    if (pfad.startsWith('/schedules/')) return Promise.reject(nichtGefunden)
    // Eine Schichtart muss es geben: die Seite hat dafuer eine eigene
    // Vorpruefung und ruft die API sonst gar nicht erst. Fuer den Bedarf hat
    // sie keine - das ist genau die Luecke, die das Backend jetzt meldet.
    if (pfad === '/shift-types') {
      return Promise.resolve([{ id: 1, name: 'Tag', start_time: '08:00',
                                end_time: '16:00', color: '#3366cc',
                                required_qualifications: [] }])
    }
    // Eingerichtet: die Tafel "was noch fehlt" bleibt aus dem Weg, damit
    // diese Tests von den Meldungen handeln und nicht von ihr.
    if (pfad === '/setup-status') {
      return Promise.resolve({ ready: true, missing: [], notes: [] })
    }
    return Promise.resolve([])
  })
  await act(async () => {
    render(
      // Die Seite verlinkt seit Etappe 12 auf die fehlenden Einstellungen -
      // <Link> braucht einen Router darüber.
      <MemoryRouter>
        <LanguageProvider>
          <SchedulePage setFlash={setFlash} user={HR} />
        </LanguageProvider>
      </MemoryRouter>
    )
  })
}

async function generieren(setFlash, antwort) {
  await zeigen(setFlash)
  api.post.mockResolvedValue(antwort)
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /generieren/i }))
  })
}

describe('SchedulePage: der leere Plan sagt warum', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('zeigt den Hinweis, wenn kein Bedarf hinterlegt ist', async () => {
    const setFlash = vi.fn()

    await generieren(setFlash, leererPlan({
      notice: 'Es ist kein Bedarfsband hinterlegt — der Plan bleibt deshalb leer.',
    }))

    expect(setFlash).toHaveBeenCalledWith(expect.objectContaining({
      type: 'warning',
      text: expect.stringContaining('Bedarfsband'),
    }))
  })

  it('meldet ohne Hinweis weiterhin Erfolg', async () => {
    // Gegenprobe, und die wichtigste: eine Umsetzung, die immer warnt, waere
    // sonst ebenfalls gruen.
    const setFlash = vi.fn()

    await generieren(setFlash, leererPlan({ unfilled_count: 0 }))

    expect(setFlash).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }))
  })

  it('meldet Luecken weiterhin als Fehler', async () => {
    const setFlash = vi.fn()

    await generieren(setFlash, leererPlan({ unfilled_count: 3 }))

    expect(setFlash).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }))
  })
})

describe('SchedulePage: was noch fehlt', () => {
  // Seit Etappe 12 zeigt die Seite, was einen brauchbaren Plan noch
  // verhindert - aber nur, solange wirklich etwas fehlt. Eine Tafel, die immer
  // da ist, ist Moeblierung; eine, die verschwindet, ist eine Antwort.
  async function mitStand(stand, user = HR) {
    const nichtGefunden = Object.assign(new Error('kein Plan'), { status: 404 })
    api.get.mockImplementation(pfad => {
      if (pfad.startsWith('/schedules/')) return Promise.reject(nichtGefunden)
      if (pfad === '/setup-status') return Promise.resolve(stand)
      return Promise.resolve([])
    })
    await act(async () => {
      render(
        <MemoryRouter>
          <LanguageProvider>
            <SchedulePage setFlash={() => {}} user={user} />
          </LanguageProvider>
        </MemoryRouter>
      )
    })
  }

  beforeEach(() => { vi.clearAllMocks() })

  it('nennt, was fehlt, und wohin', async () => {
    await mitStand({
      ready: false,
      missing: [{ key: 'coverage_requirements', route: '/coverage-requirements',
                  text: 'Es ist noch kein Bedarfsband hinterlegt.' }],
      notes: [],
    })

    expect(screen.getByText(/kein Bedarfsband/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dorthin' }))
      .toHaveAttribute('href', '/coverage-requirements')
  })

  it('verschwindet, sobald nichts mehr fehlt', async () => {
    // Die Gegenprobe, und die wichtigste: eine Tafel, die bleibt, waere sonst
    // ebenfalls gruen.
    await mitStand({ ready: true, missing: [], notes: [] })

    expect(screen.queryByText(/Bevor der erste Plan/)).not.toBeInTheDocument()
  })

  it('zeigt Hinweise, ohne sie zu Maengeln zu machen', async () => {
    await mitStand({
      ready: true,
      missing: [],
      notes: [{ key: 'holiday_region', route: '/business-hours',
                text: 'Ohne Bundesland kennt das Werkzeug keine Feiertage.' }],
    })

    // Bereit heisst bereit: die Tafel bleibt aus, auch wenn Hinweise offen sind.
    expect(screen.queryByText(/Bevor der erste Plan/)).not.toBeInTheDocument()
  })

  it('zeigt einem Mitarbeiter nichts davon', async () => {
    // Was dem Betrieb fehlt, ist die Sache der Personalabteilung - und die API
    // lehnt die Route fuer Mitarbeiter ohnehin ab.
    await mitStand({ ready: false, missing: [{ key: 'employees', route: '/employees',
                                               text: 'Kein Mitarbeiter' }], notes: [] },
                    { id: 2, username: 'anna', role: 'employee', employee_id: 5 })

    expect(screen.queryByText(/Bevor der erste Plan/)).not.toBeInTheDocument()
  })
})
