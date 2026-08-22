import { useTranslation } from '../i18n/context'

/** Renders GET /schedules/<year>/<month>'s average_hours: the employees whose
 * working time over the last 24 weeks breaks § 3's eight-hour average.
 *
 * Deliberately worded as a condition rather than a verdict. Ten-hour days are
 * lawful *if* the average holds; what this list says is that it currently does
 * not, which is a thing to fix in the coming weeks - not a rule the tool
 * caught someone breaking. Same shape as CoverageGaps next door, and likewise
 * absent entirely when there is nothing to report, which includes an
 * employee's own-scope view.
 */
function AverageHours({ entries }) {
  const { t } = useTranslation()

  if (!entries || entries.length === 0) return null

  return (
    <div className="coverage-gaps">
      <p className="coverage-gaps-title">{t('averageHours.title')}</p>
      <ul className="coverage-gaps-list">
        {entries.map(entry => (
          <li key={entry.employee_id}>
            {t('averageHours.entry', {
              name: entry.employee_name,
              average: entry.average_per_working_day,
              worked: entry.hours_worked,
              allowed: entry.hours_allowed,
            })}
          </li>
        ))}
      </ul>
      <p className="hint">{t('averageHours.hint')}</p>
    </div>
  )
}

export default AverageHours
