import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

function Wirft({ soll }) {
  if (soll) throw new Error('kaputt')
  return <p>Der Dienstplan</p>
}

describe('ErrorBoundary', () => {
  // React schreibt einen gefangenen Fehler zusaetzlich selbst auf die Konsole.
  // Ohne das hier ist die Testausgabe unlesbar, und ein stiller Fehler waere
  // schlimmer als ein lauter: componentDidCatch loggt weiterhin, das wird
  // unten geprueft.
  let konsole
  beforeEach(() => { konsole = vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => { konsole.mockRestore() })

  it('zeigt die Kinder, solange nichts wirft', () => {
    render(<ErrorBoundary><Wirft soll={false} /></ErrorBoundary>)

    expect(screen.getByText('Der Dienstplan')).toBeInTheDocument()
  })

  it('faengt einen Fehler ab, statt die Seite leer zu lassen', () => {
    // Ohne Grenze verschwindet der ganze Baum: keine Meldung, keine
    // Navigation, kein Hinweis, dass Neuladen hilft. Auf einem Telefon ist das
    // von "das Werkzeug ist weg" nicht zu unterscheiden.
    render(<ErrorBoundary><Wirft soll /></ErrorBoundary>)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/nicht angezeigt werden/i)).toBeInTheDocument()
  })

  it('sagt in beiden Sprachen, dass die Daten nicht betroffen sind', () => {
    // Feste Zeichenketten statt der Uebersetzungshilfe: die Grenze muss auch
    // dann noch etwas anzeigen, wenn der Sprachkontext selbst der Fehler war.
    render(<ErrorBoundary><Wirft soll /></ErrorBoundary>)

    expect(screen.getByText(/Ihre Daten sind/)).toBeInTheDocument()
    expect(screen.getByText(/Your data is not affected/)).toBeInTheDocument()
  })

  it('protokolliert den Fehler weiterhin auf der Konsole', () => {
    render(<ErrorBoundary><Wirft soll /></ErrorBoundary>)

    expect(konsole).toHaveBeenCalledWith(
      expect.stringContaining('Unbehandelter Fehler'),
      expect.any(Error),
      expect.anything(),
    )
  })

  it('zeigt nach einem erneuten Versuch wieder die Kinder', () => {
    // Der Fall, fuer den die Schaltflaeche da ist: die Ursache war
    // voruebergehend (eine halb geladene Antwort, ein veralteter Wert). Ein
    // erneuter Aufbau genuegt dann, und niemand muss die Seite neu laden.
    const { rerender } = render(<ErrorBoundary><Wirft soll /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toBeInTheDocument()

    // Die Grenze haelt den Fehler fest: neue Kinder allein zeigen noch nichts.
    rerender(<ErrorBoundary><Wirft soll={false} /></ErrorBoundary>)
    expect(screen.queryByText('Der Dienstplan')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /erneut versuchen/i }))

    expect(screen.getByText('Der Dienstplan')).toBeInTheDocument()
  })
})
