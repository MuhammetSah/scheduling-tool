import { Component } from 'react'

/**
 * Catches a render error so one broken component does not take the page.
 *
 * Without it a throw anywhere below unmounts the whole tree and leaves a blank
 * white page: no message, no navigation, no hint that reloading would help.
 * For an employee looking up tomorrow's shift on a phone that is
 * indistinguishable from the tool being gone.
 *
 * A class, because that is the only thing React offers here -
 * componentDidCatch has no hook equivalent. The one place in this codebase
 * where the rule "components are functions" does not apply.
 *
 * Deliberately not wired to any reporting service: there is none, and a
 * boundary that pretends to send the error somewhere would be worse than one
 * that says plainly where the details are (the browser console).
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // The console is where a developer looks and where a user can be asked to
    // look; keeping the component stack is what makes the report usable.
    console.error('Unbehandelter Fehler in der Oberfläche:', error, info)
  }

  // Called by the "try again" button: clearing the error re-renders the
  // children, which is enough when the cause was transient (a half-loaded
  // response, a stale prop). If it throws again the boundary catches again -
  // no worse than before, and no reload needed to find out.
  handleRetry = () => {
    this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    // Plain strings rather than the translation hook: this must still render
    // when the failure is the language context itself, so both languages are
    // shown side by side instead of one being chosen by something that may be
    // the thing that broke.
    return (
      <div className="panel panel-narrow" role="alert">
        <h2>Die Seite konnte nicht angezeigt werden</h2>
        <p className="hint">
          Etwas ist beim Aufbau dieser Ansicht schiefgegangen. Ihre Daten sind
          davon nicht betroffen — der Fehler steckt in der Anzeige, nicht im
          Dienstplan.
        </p>
        <p className="hint" lang="en">
          Something went wrong while rendering this view. Your data is not
          affected — this is a display error, not a scheduling one.
        </p>
        <div className="toolbar">
          <button type="button" onClick={this.handleRetry}>
            Erneut versuchen / Try again
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => window.location.assign('/')}
          >
            Zum Dienstplan / To the schedule
          </button>
        </div>
        <p className="hint">
          Technische Angaben stehen in der Browser-Konsole
          {error.message ? `: ${error.message}` : '.'}
        </p>
      </div>
    )
  }
}

export default ErrorBoundary
