import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import CoverageEditor from './CoverageEditor'
import { api } from '../api'

// The component talks to the backend exclusively through `api` - mocking the
// module (rather than e.g. stubbing fetch) keeps these tests focused on
// CoverageEditor's own logic, in particular firstOverlappingPair()'s
// half-open-interval rule (see the comment above it in CoverageEditor.jsx).
vi.mock('../api', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

// German button/label text, since the app defaults to 'de' (see
// i18n/storage.js's DEFAULT_LANG) and none of these tests switch language.
const ADD_BAND = '+ Band hinzufügen'
const REMOVE_BAND_TITLE = 'Dieses Band entfernen'
const START_LABEL = 'Von'
const END_LABEL = 'Bis'
const OVERLAP_WARNING = 'Diese Bänder überschneiden sich — bitte anpassen, bevor gespeichert werden kann.'
const SAVE_BUTTON = 'Speichern'

function makeBand(weekday, start_time, end_time, required_count = 1) {
  return { weekday, start_time, end_time, required_count }
}

// Renders inside act() and awaits it so the component's mount-only load()
// (an async function awaiting api.get()) has fully resolved and its
// setState applied before the test starts interacting - otherwise a later
// user action (e.g. addBand()) could be silently overwritten once the
// pending load() finally resolves and replaces the whole grouped state.
async function renderEditor(setFlash) {
  await act(async () => {
    render(
      <LanguageProvider>
        <CoverageEditor setFlash={setFlash} />
      </LanguageProvider>,
    )
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CoverageEditor overlap detection', () => {
  it('flags two bands on the same weekday that genuinely overlap', async () => {
    api.get.mockResolvedValue([
      makeBand(0, '08:00', '14:00'),
      makeBand(0, '12:00', '16:00'),
    ])
    await renderEditor(vi.fn())

    expect(await screen.findByText(OVERLAP_WARNING)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SAVE_BUTTON })).toBeDisabled()
  })

  // The counterpart to the overlap case above: firstOverlappingPair() uses a
  // half-open [start, end) comparison, so 08:00-12:00 and 12:00-16:00 must
  // NOT be reported as overlapping - they only touch at the boundary.
  it('does not flag two bands that only touch at the boundary', async () => {
    api.get.mockResolvedValue([
      makeBand(0, '08:00', '12:00'),
      makeBand(0, '12:00', '16:00'),
    ])
    await renderEditor(vi.fn())

    // Wait for the loaded bands to actually be on screen before asserting
    // their absence would otherwise pass trivially before the load lands.
    expect(await screen.findAllByLabelText(START_LABEL)).toHaveLength(2)
    expect(screen.queryByText(OVERLAP_WARNING)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: SAVE_BUTTON })).not.toBeDisabled()
  })
})

describe('CoverageEditor band list editing', () => {
  it('adds a band row and removes it again', async () => {
    api.get.mockResolvedValue([])
    await renderEditor(vi.fn())

    expect(screen.queryByLabelText(START_LABEL)).not.toBeInTheDocument()

    const addButtons = screen.getAllByRole('button', { name: ADD_BAND })
    fireEvent.click(addButtons[0]) // Monday's "add band" button

    const startInputs = await screen.findAllByLabelText(START_LABEL)
    expect(startInputs).toHaveLength(1)

    fireEvent.click(screen.getByTitle(REMOVE_BAND_TITLE))
    expect(screen.queryByLabelText(START_LABEL)).not.toBeInTheDocument()
  })
})

describe('CoverageEditor closed-day rejection', () => {
  // CoverageEditor itself has no notion of "closed" - that's business hours
  // data it never fetches. A band on a closed day is only ever rejected by
  // the backend (see backend/i18n.py's coverage_requirement_closed_day), and
  // the component's only job is to surface that rejection instead of
  // silently accepting it. This mirrors the real PUT /coverage-requirements
  // response for that case.
  it('surfaces a closed-day rejection from the backend as an error and keeps the band unsent', async () => {
    api.get.mockResolvedValue([])
    const setFlash = vi.fn()
    await renderEditor(setFlash)

    fireEvent.click(screen.getAllByRole('button', { name: ADD_BAND })[0])
    const [startInput] = await screen.findAllByLabelText(START_LABEL)
    const [endInput] = screen.getAllByLabelText(END_LABEL)
    fireEvent.change(startInput, { target: { value: '08:00' } })
    fireEvent.change(endInput, { target: { value: '09:00' } })

    const closedDayMessage = 'Am Mo ist geschlossen, dort ist kein Bedarfsband erlaubt (08:00–09:00)'
    api.put.mockRejectedValue(new Error(closedDayMessage))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: SAVE_BUTTON }))
    })

    expect(setFlash).toHaveBeenCalledWith({ type: 'error', text: closedDayMessage })
    expect(setFlash).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }))
    // The rejected band is still sitting in the form - nothing was silently
    // accepted or cleared out from under the user.
    expect(screen.getByLabelText(START_LABEL)).toHaveValue('08:00')
  })
})
