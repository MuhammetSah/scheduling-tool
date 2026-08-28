import { useTranslation } from '../i18n/context'

/** Renders GET /schedules/<year>/<month>'s qualification_shortfalls: the shift
 * types whose certificate holders are too few to fill their slots.
 *
 * Sits directly under CoverageGaps because it answers the question that list
 * provokes and cannot answer itself. "Two people missing" repeated across
 * every weekday, with half the roster visibly free, reads as a broken
 * generator; "the early shift needs a first-aider, and one of eight people is
 * one" turns the same screen into a decision - train somebody, or drop the
 * requirement.
 *
 * Only ever states the arithmetic the server could prove: more slots on a day
 * than there are people allowed to take them at all. Same shape and same
 * restraint as its two neighbours, and likewise absent when there is nothing
 * to report - which includes an employee's own-scope view.
 */
function QualificationShortfalls({ entries }) {
  const { t } = useTranslation()

  if (!entries || entries.length === 0) return null

  return (
    <div className="coverage-gaps">
      <p className="coverage-gaps-title">{t('qualificationShortfalls.title')}</p>
      <ul className="coverage-gaps-list">
        {entries.map(entry => (
          <li key={entry.shift_type_id}>
            {t('qualificationShortfalls.entry', {
              shiftType: entry.shift_type_name,
              qualifications: entry.qualifications.join(', '),
              eligible: entry.eligible,
              active: entry.active_employees,
              slots: entry.slots,
              days: entry.dates_affected,
            })}
          </li>
        ))}
      </ul>
      <p className="hint">{t('qualificationShortfalls.hint')}</p>
    </div>
  )
}

export default QualificationShortfalls
