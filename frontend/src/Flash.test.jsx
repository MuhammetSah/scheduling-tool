import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import Flash from './Flash'
import { LanguageProvider } from './i18n/LanguageContext'

function zeige(flash, onClose = () => {}) {
  return render(
    <LanguageProvider>
      <Flash flash={flash} onClose={onClose} />
    </LanguageProvider>
  )
}

describe('Flash', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('blendet eine Erfolgsmeldung nach einer Weile aus', () => {
    const schliessen = vi.fn()
    zeige({ type: 'success', text: 'Plan erzeugt' }, schliessen)

    act(() => { vi.advanceTimersByTime(10000) })

    expect(schliessen).toHaveBeenCalled()
  })

  it('laesst einen Fehler stehen', () => {
    // Der Befund, um den es geht: "Der Tausch würde die Ruhezeit
    // unterschreiten" verschwand nach vier Sekunden. Wer in dem Moment
    // woandershin sieht, hat danach nur eine Schaltflaeche, die nichts tat.
    const schliessen = vi.fn()
    zeige({ type: 'error', text: 'Ruhezeit unterschritten' }, schliessen)

    act(() => { vi.advanceTimersByTime(60000) })

    expect(schliessen).not.toHaveBeenCalled()
    expect(screen.getByText('Ruhezeit unterschritten')).toBeInTheDocument()
  })

  it('laesst auch eine Warnung stehen', () => {
    const schliessen = vi.fn()
    zeige({ type: 'warning', text: 'Steht noch im Plan' }, schliessen)

    act(() => { vi.advanceTimersByTime(60000) })

    expect(schliessen).not.toHaveBeenCalled()
  })

  it('laesst sich von Hand schliessen', () => {
    // Vorher rief nur der Zeitgeber onClose auf - eine Meldung, die bleibt,
    // braucht eine Schaltflaeche.
    const schliessen = vi.fn()
    zeige({ type: 'error', text: 'Ruhezeit unterschritten' }, schliessen)

    fireEvent.click(screen.getByRole('button', { name: /schließen/i }))

    expect(schliessen).toHaveBeenCalled()
  })

  it('meldet einen Fehler der Sprachausgabe als Fehler', () => {
    // Ein div, das mitten im Baum auftaucht, ist fuer die Bildschirmausgabe
    // ein Ereignis und fuer die Sprachausgabe keines.
    zeige({ type: 'error', text: 'Ruhezeit unterschritten' })

    const meldung = screen.getByRole('alert')
    expect(meldung).toHaveAttribute('aria-live', 'assertive')
  })

  it('meldet einen Erfolg zurueckhaltender', () => {
    zeige({ type: 'success', text: 'Plan erzeugt' })

    const meldung = screen.getByRole('status')
    expect(meldung).toHaveAttribute('aria-live', 'polite')
  })

  it('zeigt nichts, wenn es nichts zu melden gibt', () => {
    const { container } = zeige(null)

    expect(container).toBeEmptyDOMElement()
  })
})
