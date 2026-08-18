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
  let hasFreeBlocks = false
  for (const a of schedule.assignments) {
    if (!byDate.has(a.date)) byDate.set(a.date, new Map())
    const byShift = byDate.get(a.date)
    if (!byShift.has(a.shift_type_id)) byShift.set(a.shift_type_id, [])
    byShift.get(a.shift_type_id).push(a)
    if (a.shift_type_id === null) hasFreeBlocks = true
  }
  const dates = [...byDate.keys()].sort()

  // A block without its own shift type (e.g. created directly via the API)
  // groups under the key null above like any other shift type would - give it
  // a column too, but only when the month actually has one, and always last
  // so the regular shift-type columns keep their usual order.
  const columns = hasFreeBlocks
    ? [...shiftTypes, { id: null, name: t('schedule.freeBlockColumn') }]
    : shiftTypes

  return (
    <div className="schedule-table-wrap">
      <table className="schedule-table">
        <thead>
          <tr>
            <th>{t('scheduleGrid.dateHeader')}</th>
            {columns.map(st => <th key={st.id ?? 'free-block'}>{st.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {dates.map(date => (
            <tr key={date} className={isWeekend(date) ? 'weekend' : ''}>
              <td className="date-cell">{formatDate(date)}</td>
              {columns.map(st => (
                <td key={st.id ?? 'free-block'}>
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
