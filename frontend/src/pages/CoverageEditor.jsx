import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useTranslation } from '../i18n/context'

const HOUR_TICKS = [0, 6, 12, 18, 24]
const DAY_MINUTES = 24 * 60

function timeToMinutes(value) {
  const [h, m] = value.split(':').map(Number)
  return h * 60 + m
}

// Same midnight rule as backend/coverage_model.py's _band_range(): end_time
// <= start_time means the band crosses midnight, so its end is counted into
// the next day rather than treated as a (start > end) error.
function bandRangeMinutes(band) {
  const start = timeToMinutes(band.start_time)
  let end = timeToMinutes(band.end_time)
  if (end <= start) end += DAY_MINUTES
  return [start, end]
}

// Mirrors backend/coverage_model.py's first_overlapping_pair(): half-open
// [start, end) overlap (two bands that only touch do not overlap), each pair
// also compared one cycle earlier/later so a band that wraps past midnight is
// still checked against one starting the next morning. Kept in lockstep with
// the backend on purpose - this is the one place a second implementation of
// the rule is wanted, so the bar chart can flag a collision immediately
// instead of only after a rejected save, but the wording of a real rejection
// still comes from the backend's own message (see submitBands()).
function firstOverlappingPair(bands) {
  const ranges = bands.map(bandRangeMinutes)
  for (let i = 0; i < ranges.length; i++) {
    const [startI, endI] = ranges[i]
    for (let j = i + 1; j < ranges.length; j++) {
      const [startJ, endJ] = ranges[j]
      for (const shift of [-DAY_MINUTES, 0, DAY_MINUTES]) {
        if (startI < endJ + shift && startJ + shift < endI) {
          return [bands[i], bands[j]]
        }
      }
    }
  }
  return null
}

// One or two {left, width} percentage pairs for a band's bar on the day
// track. A band that crosses midnight (e.g. 20:00-06:00) is split into a
// segment running to the right edge and a second one continuing from the
// left edge, rather than drawn past the end of the track - the two segments
// share the same key prefix so they're still recognizable as one band.
function bandSegments(band) {
  const [start, end] = bandRangeMinutes(band)
  if (end <= DAY_MINUTES) {
    return [{ left: (start / DAY_MINUTES) * 100, width: ((end - start) / DAY_MINUTES) * 100 }]
  }
  return [
    { left: (start / DAY_MINUTES) * 100, width: ((DAY_MINUTES - start) / DAY_MINUTES) * 100 },
    { left: 0, width: ((end - DAY_MINUTES) / DAY_MINUTES) * 100 },
  ]
}

function hasValidTimes(band) {
  return Boolean(band.start_time && band.end_time)
}

function groupByWeekday(bands) {
  const grouped = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] }
  for (const b of bands) grouped[b.weekday].push(b)
  return grouped
}

function CoverageEditor({ setFlash }) {
  const { t, weekdayLabels } = useTranslation()
  const [bandsByWeekday, setBandsByWeekday] = useState(groupByWeekday([]))
  // Local-only key for React list identity, stripped out again in
  // submitBands() before the payload goes to the API - same approach as
  // Employees.jsx's nextWindowKey for availability windows.
  const nextBandKey = useRef(0)

  async function load() {
    try {
      const bands = await api.get('/coverage-requirements')
      const grouped = groupByWeekday(bands)
      for (const wd of Object.keys(grouped)) {
        grouped[wd] = grouped[wd].map(b => ({ ...b, _key: `b${++nextBandKey.current}` }))
      }
      setBandsByWeekday(grouped)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function addBand(weekday) {
    setBandsByWeekday(g => ({
      ...g,
      [weekday]: [
        ...g[weekday],
        { _key: `b${++nextBandKey.current}`, weekday, start_time: '', end_time: '', required_count: 1 },
      ],
    }))
  }

  function updateBand(weekday, key, changes) {
    setBandsByWeekday(g => ({
      ...g,
      [weekday]: g[weekday].map(b => (b._key === key ? { ...b, ...changes } : b)),
    }))
  }

  function removeBand(weekday, key) {
    setBandsByWeekday(g => ({ ...g, [weekday]: g[weekday].filter(b => b._key !== key) }))
  }

  function setRequiredCount(weekday, key, value) {
    updateBand(weekday, key, { required_count: Math.max(0, Number(value) || 0) })
  }

  // Client-side mirror of the backend's overlap check, recomputed on every
  // render from the current form state - cheap enough at this scale and
  // keeps the warning always in sync with what's on screen.
  const overlapsByWeekday = {}
  for (const wd of Object.keys(bandsByWeekday)) {
    overlapsByWeekday[wd] = firstOverlappingPair(bandsByWeekday[wd].filter(hasValidTimes))
  }
  const hasAnyOverlap = Object.values(overlapsByWeekday).some(Boolean)

  function isOverlapping(weekday, key) {
    const pair = overlapsByWeekday[weekday]
    return Boolean(pair && (pair[0]._key === key || pair[1]._key === key))
  }

  async function submitBands(e) {
    e.preventDefault()
    // Drop rows the user added but never filled in - same reasoning as
    // Employees.jsx's availability filter: it only skips a row that carries
    // no data at all, it doesn't second-guess a filled-in one.
    const payload = Object.values(bandsByWeekday)
      .flat()
      .filter(hasValidTimes)
      .map(b => ({ weekday: b.weekday, start_time: b.start_time, end_time: b.end_time, required_count: b.required_count }))
    try {
      const bands = await api.put('/coverage-requirements', payload)
      const grouped = groupByWeekday(bands)
      for (const wd of Object.keys(grouped)) {
        grouped[wd] = grouped[wd].map(b => ({ ...b, _key: `b${++nextBandKey.current}` }))
      }
      setBandsByWeekday(grouped)
      setFlash({ type: 'success', text: t('coverageEditor.flashSaved') })
    } catch (err) {
      // Overlap-across-a-single-weekday is already caught above before this
      // ever fires; whatever does reach here (a band outside opening hours,
      // one on a closed day, ...) is reported in the backend's own words.
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{t('coverageEditor.title')}</h2>
      </div>
      <p className="hint">{t('coverageEditor.hint')}</p>

      <form onSubmit={submitBands}>
        <div className="coverage-editor">
          {weekdayLabels.map((label, wd) => (
            <div className="coverage-day" key={wd}>
              <div className="coverage-day-header">
                <span className="coverage-day-label">{label}</span>
                <button type="button" className="btn-secondary btn-small" onClick={() => addBand(wd)}>
                  {t('coverageEditor.addBandButton')}
                </button>
              </div>

              <div className="coverage-track">
                {HOUR_TICKS.map(hour => (
                  <span
                    key={hour}
                    className="coverage-tick"
                    style={{
                      left: `${(hour / 24) * 100}%`,
                      transform: hour === 0 ? 'translateX(0)' : hour === 24 ? 'translateX(-100%)' : 'translateX(-50%)',
                    }}
                  >
                    {hour}
                  </span>
                ))}
                {bandsByWeekday[wd].filter(hasValidTimes).flatMap(band =>
                  bandSegments(band).map((seg, i) => (
                    <div
                      key={`${band._key}-${i}`}
                      className={`coverage-bar${isOverlapping(wd, band._key) ? ' coverage-bar-overlap' : ''}`}
                      style={{ left: `${seg.left}%`, width: `${seg.width}%` }}
                      title={t('coverageEditor.tooltip', { start: band.start_time, end: band.end_time, n: band.required_count })}
                    />
                  ))
                )}
              </div>

              {overlapsByWeekday[wd] && (
                <p className="coverage-overlap-warning">{t('coverageEditor.overlapWarning')}</p>
              )}

              {bandsByWeekday[wd].map(band => (
                <div className="coverage-band-row toolbar" key={band._key}>
                  <input
                    type="time"
                    aria-label={t('coverageEditor.startAria')}
                    value={band.start_time}
                    onChange={e => updateBand(wd, band._key, { start_time: e.target.value })}
                    required
                  />
                  <input
                    type="time"
                    aria-label={t('coverageEditor.endAria')}
                    value={band.end_time}
                    onChange={e => updateBand(wd, band._key, { end_time: e.target.value })}
                    required
                  />
                  <input
                    type="number"
                    min="0"
                    aria-label={t('coverageEditor.countAria')}
                    value={band.required_count}
                    onChange={e => setRequiredCount(wd, band._key, e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="btn-danger btn-small"
                    title={t('coverageEditor.removeBandTitle')}
                    onClick={() => removeBand(wd, band._key)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="toolbar mt-md">
          <button type="submit" disabled={hasAnyOverlap}>{t('common.save')}</button>
        </div>
      </form>
    </div>
  )
}

export default CoverageEditor
