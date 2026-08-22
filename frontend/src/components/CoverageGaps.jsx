import { useTranslation } from '../i18n/context'

// Same weekday + day.month format as ScheduleGrid's date column, just without
// the comma between them - the "{date}, {start}-{end}: ..." templates below
// supply their own separator after the date.
function formatGapDate(iso, weekdayLabels, dateLocale) {
  const d = new Date(`${iso}T00:00:00`)
  const weekdayIndex = (d.getDay() + 6) % 7 // JS: 0=Sunday -> ours: 0=Monday
  return `${weekdayLabels[weekdayIndex]} ${d.toLocaleDateString(dateLocale, { day: '2-digit', month: '2-digit' })}`
}

/** Renders GET /schedules/<year>/<month>'s coverage_gaps as a readable list
 * ("Di 17.03., 12:00-14:00: 1 Person fehlt") instead of just the unfilled
 * count badge SchedulePage already shows. Not rendered at all when there is
 * nothing to report - an employee's own-scope view never has this field. */
function CoverageGaps({ gaps }) {
  const { t, weekdayLabels, dateLocale } = useTranslation()

  if (!gaps || gaps.length === 0) return null

  return (
    <div className="coverage-gaps">
      <p className="coverage-gaps-title">{t('coverageGaps.title')}</p>
      <ul className="coverage-gaps-list">
        {gaps.map((gap, i) => (
          <li key={i}>
            {t(gap.missing === 1 ? 'coverageGaps.entrySingular' : 'coverageGaps.entryPlural', {
              date: formatGapDate(gap.date, weekdayLabels, dateLocale),
              start: gap.start_time,
              end: gap.end_time,
              n: gap.missing,
            })}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default CoverageGaps
