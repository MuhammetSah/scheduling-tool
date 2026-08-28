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

    // Ueber die zugaengliche Bezeichnung statt ueber title: der Knopf traegt
    // ein blosses "×", und ohne aria-label liest ein Screenreader genau das
    // vor. Der Test findet ihn jetzt auf demselben Weg wie jemand, der ihn
    // nicht sehen kann.
    fireEvent.click(screen.getByRole('button', { name: REMOVE_BAND_TITLE }))
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

// ---------- Einen Tag auf andere Wochentage uebertragen ----------
//
// Mo-Fr fuenfmal von Hand einzugeben ist fuenfmal die Gelegenheit, sich zu
// vertippen. Die Faelle hier sind die, bei denen eine Kopierfunktion
// erfahrungsgemaess falsch gebaut wird: sie haengt an, statt zu ersetzen; sie
// kopiert die Wochentagsnummer der Quelle mit; sie fragt nicht nach, bevor sie
// etwas ueberschreibt; oder sie bietet sich auf einem leeren Tag an und raeumt
// dann die Ziele leer.

const COPY_BUTTON = 'Übertragen'
const COPY_APPLY = 'Übernehmen'
const COPY_WORKDAYS = 'Mo–Fr'

async function oeffneUebertragung(setFlash = vi.fn()) {
  await renderEditor(setFlash)
  fireEvent.click(screen.getAllByRole('button', { name: COPY_BUTTON })[0])
  return setFlash
}

describe('CoverageEditor: Übertragen auf andere Wochentage', () => {
  it('bietet Übertragen nur an, wo es etwas zu übertragen gibt', async () => {
    api.get.mockResolvedValue([makeBand(0, '08:00', '16:00', 2)])
    await renderEditor(vi.fn())

    // Genau ein Montag hat Bänder, also genau ein Knopf.
    expect(screen.getAllByRole('button', { name: COPY_BUTTON })).toHaveLength(1)
  })

  it('überträgt die Bänder auf die gewählten Tage', async () => {
    api.get.mockResolvedValue([makeBand(0, '08:00', '16:00', 3)])
    await oeffneUebertragung()

    fireEvent.click(screen.getByRole('button', { name: COPY_WORKDAYS }))
    fireEvent.click(screen.getByRole('button', { name: COPY_APPLY }))

    // Montag plus Di-Fr: fünf Zeilen mit denselben Zeiten.
    expect(screen.getAllByLabelText('Von').filter(f => f.value === '08:00')).toHaveLength(5)
    expect(screen.getAllByLabelText('Benötigte Anzahl').filter(f => f.value === '3')).toHaveLength(5)
  })

  it('ersetzt vorhandene Bänder, statt sie zu ergänzen', async () => {
    // Anhängen erzeugte auf dem Dienstag sofort eine Überschneidung - also
    // genau den Zustand, den der Speichern-Knopf sperrt.
    api.get.mockResolvedValue([
      makeBand(0, '08:00', '16:00'),
      makeBand(1, '10:00', '12:00'),
    ])
    window.confirm = vi.fn(() => true)
    await oeffneUebertragung()

    fireEvent.click(screen.getByRole('button', { name: COPY_WORKDAYS }))
    fireEvent.click(screen.getByRole('button', { name: COPY_APPLY }))

    expect(screen.queryAllByDisplayValue('10:00')).toHaveLength(0)
    expect(screen.queryByText(OVERLAP_WARNING)).toBeNull()
    expect(screen.getByRole('button', { name: SAVE_BUTTON })).not.toBeDisabled()
  })

  it('fragt nach, bevor belegte Tage überschrieben werden', async () => {
    api.get.mockResolvedValue([
      makeBand(0, '08:00', '16:00'),
      makeBand(1, '10:00', '12:00'),
    ])
    window.confirm = vi.fn(() => false)
    await oeffneUebertragung()

    fireEvent.click(screen.getByRole('button', { name: COPY_WORKDAYS }))
    fireEvent.click(screen.getByRole('button', { name: COPY_APPLY }))

    expect(window.confirm).toHaveBeenCalled()
    // Abgelehnt heisst unveraendert - der Dienstag behaelt sein eigenes Band.
    expect(screen.getAllByDisplayValue('10:00')).toHaveLength(1)
  })

  it('fragt nicht nach, wenn alle Zieltage leer sind', async () => {
    // Eine Rückfrage, die auch bei leeren Tagen kommt, wird weggeklickt, ohne
    // gelesen zu werden - und dann auch die, auf die es ankommt.
    api.get.mockResolvedValue([makeBand(0, '08:00', '16:00')])
    window.confirm = vi.fn(() => true)
    await oeffneUebertragung()

    fireEvent.click(screen.getByRole('button', { name: COPY_WORKDAYS }))
    fireEvent.click(screen.getByRole('button', { name: COPY_APPLY }))

    expect(window.confirm).not.toHaveBeenCalled()
  })

  it('schreibt beim Speichern den Zieltag, nicht den der Quelle', async () => {
    // Der Fehler, der beim Kopieren am leichtesten passiert: das Objekt wird
    // übernommen, aber `weekday` zeigt weiter auf den Montag.
    api.get.mockResolvedValue([makeBand(0, '08:00', '16:00', 2)])
    api.put.mockResolvedValue([])
    await oeffneUebertragung()

    fireEvent.click(screen.getByRole('button', { name: COPY_WORKDAYS }))
    fireEvent.click(screen.getByRole('button', { name: COPY_APPLY }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: SAVE_BUTTON }))
    })

    const gesendet = api.put.mock.calls[0][1]
    expect([...new Set(gesendet.map(b => b.weekday))].sort()).toEqual([0, 1, 2, 3, 4])
  })

  it('macht ohne gewählten Zieltag nichts', async () => {
    api.get.mockResolvedValue([makeBand(0, '08:00', '16:00')])
    await oeffneUebertragung()

    expect(screen.getByRole('button', { name: COPY_APPLY })).toBeDisabled()
  })
})
