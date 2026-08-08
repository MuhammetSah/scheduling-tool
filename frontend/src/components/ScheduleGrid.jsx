import ShiftCell from './ShiftCell'
import { useTranslation } from '../i18n/context'

function isWeekend(iso) {
  const day = new Date(iso + 'T00:00:00').getDay()
  return day === 0 || day === 6
}

function ScheduleGrid({
  schedule,
  employees,
  shiftTypes,
  readOnly = false,
  onReassign,
  swapSelection,
  onToggleSwap,
  onSetTimes,
  onAddSlot,
  onRemoveSlot,
  onReportAbsence,
  setFlash,
}) {
  const { t, weekdayLabels, dateLocale } = useTranslation()

  function formatDate(iso) {
    const d = new Date(iso + 'T00:00:00')
    const weekdayIndex = (d.getDay() + 6) % 7 // JS: 0=Sunday -> ours: 0=Monday
    return `${weekdayLabels[weekdayIndex]}, ${d.toLocaleDateString(dateLocale, { day: '2-digit', month: '2-digit' })}`
  }

  const byDate = new Map()
  for (const a of schedule.assignments) {
    if (!byDate.has(a.date)) byDate.set(a.date, new Map())
    const byShift = byDate.get(a.date)
    if (!byShift.has(a.shift_type_id)) byShift.set(a.shift_type_id, [])
    byShift.get(a.shift_type_id).push(a)
  }
  const dates = [...byDate.keys()].sort()

  return (
    <div className="schedule-table-wrap">
      <table className="schedule-table">
        <thead>
          <tr>
            <th>{t('scheduleGrid.dateHeader')}</th>
            {shiftTypes.map(st => <th key={st.id}>{st.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {dates.map(date => (
            <tr key={date} className={isWeekend(date) ? 'weekend' : ''}>
              <td className="date-cell">{formatDate(date)}</td>
              {shiftTypes.map(st => (
                <td key={st.id}>
                  <ShiftCell
                    date={date}
                    shiftType={st}
                    slots={byDate.get(date).get(st.id) || []}
                    employees={employees}
                    readOnly={readOnly}
                    swapSelection={swapSelection}
                    onReassign={onReassign}
                    onToggleSwap={onToggleSwap}
                    onSetTimes={onSetTimes}
                    onAddSlot={onAddSlot}
                    onRemoveSlot={onRemoveSlot}
                    onReportAbsence={onReportAbsence}
                    setFlash={setFlash}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ScheduleGrid
