import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent, within } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import BusinessHours from './BusinessHours'
import { api } from '../api'

vi.mock('../api', () => ({
  api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

// German UI text, since the app defaults to 'de' (see i18n/storage.js's
// DEFAULT_LANG) and none of these tests switch language. 'Öffnet'/'Schließt'
// and 'Geschlossen' also appear in the exceptions form further down the
// page, which is exactly why every query below is scoped to Monday's own
// row via within(mondayRow) rather than screen.getByLabelText() directly.
const OPEN_LABEL = 'Öffnet'
const CLOSE_LABEL = 'Schließt'
const CLOSED_LABEL = 'Geschlossen'
const SAVE_BUTTON = 'Speichern'

function makeHours() {
  return Array.from({ length: 7 }, (_, weekday) => ({
    weekday, open_time: '09:00', close_time: '17:00', closed: false,
  }))
}

// Mount-only load() (see BusinessHours.jsx) is async - awaiting it inside
// act() lets the fetched hours settle into state before a test starts
// interacting with the rendered rows.
async function renderPage(setFlash) {
  await act(async () => {
    render(
      <LanguageProvider>
        <BusinessHours setFlash={setFlash} />
      </LanguageProvider>,
    )
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation(path => {
    if (path === '/business-hours') return Promise.resolve(makeHours())
    // /settings liefert ein Objekt, nicht eine Liste - der Unterschied faellt
    // sonst erst auf, wenn jemand einen Schluessel daraus liest.
    if (path === '/settings') return Promise.resolve({})
    return Promise.resolve([])
  })
})

describe('BusinessHours closed-day toggle', () => {
  it('hides the time fields for a closed day without losing their values', async () => {
    const setFlash = vi.fn()
    await renderPage(setFlash)

    const mondayRow = (await screen.findByText('Mo')).closest('.business-hours-row')
    expect(mondayRow).not.toBeNull()

    expect(within(mondayRow).getByLabelText(OPEN_LABEL)).toHaveValue('09:00')
    expect(within(mondayRow).getByLabelText(CLOSE_LABEL)).toHaveValue('17:00')

    fireEvent.click(within(mondayRow).getByLabelText(CLOSED_LABEL))

    // The fields disappear from the DOM entirely (they're conditionally
    // rendered, not just visually hidden) - see BusinessHours.jsx's
    // `{!row.closed && (...)}`.
    expect(within(mondayRow).queryByLabelText(OPEN_LABEL)).not.toBeInTheDocument()
    expect(within(mondayRow).queryByLabelText(CLOSE_LABEL)).not.toBeInTheDocument()

    api.put.mockResolvedValue(makeHours())
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: SAVE_BUTTON }))
    })

    // The actual proof of data retention: the submitted payload still
    // carries Monday's original 09:00-17:00 even though the inputs that
    // displayed them were unmounted - hiding a row's inputs must not lose
    // the values underneath, since the backend requires them regardless of
    // `closed` (see submitHours()'s own comment on exactly this point, and
    // replace_business_hours() on the backend side).
    expect(api.put).toHaveBeenCalledWith('/business-hours', expect.arrayContaining([
      { weekday: 0, open_time: '09:00', close_time: '17:00', closed: true },
    ]))
  })
})
