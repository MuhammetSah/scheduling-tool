import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import ShiftCell from './ShiftCell'

// Bis Etappe 4 teilten sich alle Slots einer Zelle ein Zeitpaar, und die Zelle
// zeigte deshalb schlicht das des ersten. Zwei Dinge machen das jetzt falsch:
// die Spalte fuer vorlagenlose Bloecke sammelt saemtliche Bloecke des Datums
// ein, und ein zugeschnittener Block traegt zwar die shift_type_id seiner
// Vorlage, aber nicht deren Zeiten. In beiden Faellen stuende ueber Leuten,
// die 16:00-20:00 arbeiten, "08:00-12:00".

function slot(id, slotIndex, name, start, end) {
  return {
    id,
    slot_index: slotIndex,
    employee_id: id * 10,
    employee_name: name,
    start_time: start,
    end_time: end,
    assignment_time_set: true,
    time_overridden: false,
    default_start_time: start,
    default_end_time: end,
  }
}

function renderCell(slots, shiftType = { id: null, name: 'Dienst' }) {
  return render(
    <LanguageProvider>
      <ShiftCell
        date="2026-09-01"
        shiftType={shiftType}
        slots={slots}
        employees={[]}
        readOnly
        swapSelection={null}
        onReassign={() => {}}
        onToggleSwap={() => {}}
        onSetTimes={() => {}}
        onAddSlot={() => {}}
        onRemoveSlot={() => {}}
        onReportAbsence={() => {}}
        setFlash={() => {}}
      />
    </LanguageProvider>
  )
}

describe('ShiftCell mit mehreren Zeitpaaren', () => {
  const geteilterDienst = [
    slot(1, 0, 'Anna', '08:00', '12:00'),
    slot(2, 1, 'Ben', '16:00', '20:00'),
  ]

  // Geprueft wird gezielt die Ueberschrift (.cell-times), nicht irgendein
  // Vorkommen des Textes: eine Zuweisung mit eigener Zeit zeigt dieselbe
  // Zeitangabe zusaetzlich in ihrer Personenzeile, ein getByText faende also
  // auch dann zwei Treffer, wenn die Gruppierung gar nicht funktionierte.
  function ueberschriften(container) {
    return [...container.querySelectorAll('.cell-times')].map(el => el.textContent.trim())
  }

  it('zeigt beide Zeitpaare statt nur des ersten', () => {
    const { container } = renderCell(geteilterDienst)

    expect(ueberschriften(container)).toEqual(['08:00–12:00', '16:00–20:00'])
  })

  it('stellt jede Person unter ihr eigenes Zeitpaar', () => {
    const { container } = renderCell(geteilterDienst)

    const gruppen = container.querySelectorAll('.cell-time-group')
    expect(gruppen).toHaveLength(2)
    expect(gruppen[0].textContent).toContain('Anna')
    expect(gruppen[0].textContent).not.toContain('Ben')
    expect(gruppen[1].textContent).toContain('Ben')
    expect(gruppen[1].textContent).not.toContain('Anna')
  })

  it('fasst gleiche Zeiten weiterhin zu einer Gruppe zusammen', () => {
    // Die Gegenprobe: ohne sie waere eine Umsetzung gruen, die einfach jeden
    // Slot einzeln rendert - und der Normalfall "drei Leute in derselben
    // Fruehschicht" bekaeme drei identische Ueberschriften.
    const { container } = renderCell([
      slot(1, 0, 'Anna', '06:00', '14:00'),
      slot(2, 1, 'Ben', '06:00', '14:00'),
      slot(3, 2, 'Cem', '06:00', '14:00'),
    ])

    expect(container.querySelectorAll('.cell-time-group')).toHaveLength(1)
    expect(ueberschriften(container)).toEqual(['06:00–14:00'])
  })

  it('zugeschnittene Bloecke derselben Vorlage bekommen eigene Ueberschriften', () => {
    // Der Fall, den Etappe 4 neu erzeugt: zwei Bloecke mit derselben
    // shift_type_id, aber verschiedenen Zeiten, weil einer auf ein
    // Arbeitszeitfenster gekuerzt wurde.
    const { container } = renderCell(
      [slot(1, 0, 'Anna', '06:00', '14:00'), slot(2, 1, 'Ben', '08:00', '14:00')],
      { id: 7, name: 'Frühschicht' }
    )

    const gruppen = container.querySelectorAll('.cell-time-group')
    expect(gruppen).toHaveLength(2)
    expect(gruppen[0].textContent).toContain('06:00–14:00')
    expect(gruppen[1].textContent).toContain('08:00–14:00')
  })
})

describe('ShiftCell mit Ruhepausen', () => {
  // Seit Etappe 5a traegt eine Zuweisung eine Ruhepause. break_minutes ist der
  // gesetzte Wert (oder null), effective_break_minutes der wirksame - bei null
  // die gesetzliche Mindestpause nach Paragraph 4 ArbZG.
  function mitPause(gesetzt, wirksam) {
    return [{ ...slot(1, 0, 'Anna', '08:00', '16:00'),
              break_minutes: gesetzt, effective_break_minutes: wirksam }]
  }

  it('zeigt eine abweichende Pause an', () => {
    renderCell(mitPause(60, 60))

    expect(screen.getByText(/60/)).toBeInTheDocument()
  })

  it('zeigt auch die gesetzliche Pause an', () => {
    // Frueher ausgeblendet, mit der Begruendung, sonst staende auf jeder Zeile
    // dieselbe Zahl. Sie steht dort nicht: die gesetzliche Pause haengt an der
    // Spanne, und derselbe Tag traegt oft einen Achteinhalb-Stunden-Block mit
    // dreissig Minuten neben einem Vierstundenblock ohne. Sie wegzulassen
    // hiess, die Zeit, die vom Dienst abgeht, nirgends zu zeigen - und der
    // Plan ist fuer die Belegschaft die einzige Stelle, an der der eigene
    // Dienst ueberhaupt auftaucht.
    const { container } = renderCell(mitPause(null, 30))

    const pause = container.querySelector('.slot-break')
    expect(pause).not.toBeNull()
    expect(pause.textContent).toContain('30')
    // Und sie bleibt als die gesetzliche erkennbar, statt wie eine
    // Entscheidung auszusehen, die jemand getroffen hat.
    expect(pause.classList.contains('slot-break-deviating')).toBe(false)
  })

  it('hebt eine abweichende Pause von der gesetzlichen ab', () => {
    const { container } = renderCell(mitPause(45, 45))

    expect(container.querySelector('.slot-break').classList
      .contains('slot-break-deviating')).toBe(true)
  })

  it('zeigt bei einem Block ohne gesetzliche Pause nichts an', () => {
    // Vier Stunden verlangen keine - eine "0 Min. Pause" daneben waere eine
    // Angabe ueber nichts.
    const { container } = renderCell(mitPause(null, 0))

    expect(container.querySelector('.slot-break')).toBeNull()
  })

  it('zeigt eine ausdrueckliche Null als Abweichung', () => {
    // Die Gegenprobe zur Zurueckhaltung: 0 ist eine Aussage ("dieser Block
    // laeuft ohne Pause") und muss sichtbar sein, obwohl sie falsy ist.
    const { container } = renderCell(mitPause(0, 0))

    expect(container.querySelector('.slot-break')).not.toBeNull()
  })
})

describe('ShiftCell mit der Lage der Ruhepause', () => {
  // Seit Etappe 9 traegt eine Zuweisung nicht nur die Dauer der Pause, sondern
  // ihre Lage: Paragraph 4 Satz 3 ArbZG erlaubt hoechstens sechs Stunden am
  // Stueck, und ohne Uhrzeit laesst sich der Satz gar nicht pruefen.
  function mitLage(lage) {
    return [{ ...slot(1, 0, 'Anna', '08:00', '16:00'),
              break_minutes: 30, effective_break_minutes: 30, break_start: lage }]
  }

  it('zeigt die Lage neben der Dauer', () => {
    renderCell(mitLage('12:00'))

    expect(screen.getByText(/12:00/)).toBeInTheDocument()
  })

  it('zeigt ohne Lage nur die Dauer', () => {
    // Gegenprobe: die Lage ist freiwillig. Fuer jeden Block, den dieses Tool
    // bauen kann, gibt es immer eine zulaessige - eine fehlende Angabe ist
    // deshalb kein Mangel, den die Zelle anmahnen muesste.
    const { container } = renderCell(mitLage(null))

    expect(container.querySelector('.slot-break')).not.toBeNull()
    expect(screen.queryByText(/ab /)).not.toBeInTheDocument()
  })
})
