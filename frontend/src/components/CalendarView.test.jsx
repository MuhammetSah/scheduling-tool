import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'
import CalendarView from './CalendarView'

// Gegenstueck zu ShiftCell.test.jsx fuer die Kalenderansicht: dieselbe
// Kollision, andere Komponente. Gruppiert wurde nach shift_type_id allein,
// die Ueberschrift kam aus slots[0] - vorlagenlose Bloecke landeten damit
// samt und sonders unter einer Zeitangabe, und ab Etappe 4 auch
// zugeschnittene Bloecke derselben Vorlage.

function assignment(id, shiftTypeId, start, end, name, slotIndex = 0) {
  return {
    id,
    date: '2026-09-01',
    shift_type_id: shiftTypeId,
    shift_type_name: shiftTypeId === null ? null : 'Frühschicht',
    shift_type_color: shiftTypeId === null ? null : '#123456',
    slot_index: slotIndex,
    employee_id: id * 10,
    employee_name: name,
    start_time: start,
    end_time: end,
    time_overridden: false,
  }
}

function renderCalendar(assignments, shiftTypes = []) {
  return render(
    <LanguageProvider>
      <CalendarView
        schedule={{ year: 2026, month: 9, assignments }}
        shiftTypes={shiftTypes}
        highlightEmployeeId={null}
      />
    </LanguageProvider>
  )
}

function ueberschriften(container) {
  return [...container.querySelectorAll('.calendar-shift-time')].map(el => el.textContent.trim())
}

describe('CalendarView mit mehreren Zeitpaaren an einem Tag', () => {
  it('gibt jedem vorlagenlosen Block seine eigene Zeitangabe', () => {
    const { container } = renderCalendar([
      assignment(1, null, '08:00', '12:00', 'Anna', 0),
      assignment(2, null, '16:00', '20:00', 'Ben', 1),
    ])

    expect(ueberschriften(container)).toEqual(['08:00–12:00', '16:00–20:00'])
  })

  it('trennt zugeschnittene Bloecke derselben Vorlage', () => {
    const { container } = renderCalendar(
      [
        assignment(1, 7, '06:00', '14:00', 'Anna', 0),
        assignment(2, 7, '08:00', '14:00', 'Ben', 1),
      ],
      [{ id: 7, name: 'Frühschicht' }]
    )

    expect(ueberschriften(container)).toEqual(['06:00–14:00', '08:00–14:00'])
  })

  it('fasst gleiche Zeiten derselben Vorlage weiterhin zusammen', () => {
    // Die Gegenprobe: der Normalfall darf nicht in Einzelzeilen zerfallen.
    const { container } = renderCalendar(
      [
        assignment(1, 7, '06:00', '14:00', 'Anna', 0),
        assignment(2, 7, '06:00', '14:00', 'Ben', 1),
      ],
      [{ id: 7, name: 'Frühschicht' }]
    )

    expect(ueberschriften(container)).toEqual(['06:00–14:00'])
    expect(container.querySelectorAll('.calendar-person')).toHaveLength(2)
  })
})
