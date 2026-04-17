import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { InfoIcon } from './InfoIcon'
import { SOLAR_TIER_INFO, WIND_TIER_INFO } from './optimiserConstants'

const PALETTE = ['#94a3b8', '#f59e0b', '#60a5fa', '#34d399', '#f97316', '#a78bfa', '#22d3ee', '#f87171']

const PROJECTION_TIERS = ['budget', 'mid', 'premium']

// Known technology keys emitted by the backend for each scenario.
const TECHS = [
  { key: 'solar', label: 'Solar', bg: '#fde68a', fg: '#92400e' },
  { key: 'wind', label: 'Wind', bg: '#bae6fd', fg: '#075985' },
  { key: 'insulation', label: 'Insulation', bg: '#bbf7d0', fg: '#14532d' },
]

function techsForSeries(s) {
  if (Array.isArray(s?.techs)) return s.techs
  // Back-compat: derive from id prefix `combo_<a>_<b>_<c>` if the backend didn't send `techs`.
  const id = String(s?.id || '')
  if (id === 'combo_baseline') return []
  if (id.startsWith('combo_')) return id.replace('combo_', '').split('_').filter(Boolean)
  return []
}

function TechBadges({ techs }) {
  if (!techs || techs.length === 0) {
    return <span className="tech-badge tech-badge-baseline">Grid only</span>
  }
  return (
    <span className="tech-badge-row">
      {TECHS.filter((t) => techs.includes(t.key)).map((t) => (
        <span
          key={t.key}
          className="tech-badge"
          style={{ background: t.bg, color: t.fg }}
        >
          {t.label}
        </span>
      ))}
    </span>
  )
}

function groupLabel(count) {
  if (count === 0) return 'Baseline'
  if (count === 1) return 'Individual technologies'
  if (count === 2) return 'Pairs of technologies'
  return 'All technologies combined'
}

export function CostProjectionView({
  projection,
  maxYears,
  onYearsChange,
  selectedScenarioIds,
  onToggleScenario,
  projectionSolarTier,
  projectionWindTier,
  onProjectionSolarTier,
  onProjectionWindTier,
  loading = false,
}) {
  const years = Array.isArray(projection?.years) ? projection.years : []
  const series = Array.isArray(projection?.series) ? projection.series : []
  const shown = series.filter((s) => selectedScenarioIds.includes(s.id))
  const rows = years.map((y, idx) => {
    const row = { year: y }
    shown.forEach((s) => { row[s.id] = Number(s.cumulative_gbp?.[idx] ?? 0) })
    return row
  })

  // Group scenarios by number of technologies for a clearer checklist (baseline → individual → pairs → all).
  const grouped = series.reduce((acc, s) => {
    const count = techsForSeries(s).length
    if (!acc[count]) acc[count] = []
    acc[count].push(s)
    return acc
  }, {})
  const groupKeys = Object.keys(grouped).map(Number).sort((a, b) => a - b)

  // Preserve series colours across chart + legend by indexing into the full series list.
  const colourForId = (id) => {
    const idx = series.findIndex((s) => s.id === id)
    return PALETTE[(idx < 0 ? 0 : idx) % PALETTE.length]
  }

  const selectAll = () => {
    series.forEach((s) => {
      if (!selectedScenarioIds.includes(s.id)) onToggleScenario(s.id)
    })
  }
  const clearAll = () => {
    series.forEach((s) => {
      if (selectedScenarioIds.includes(s.id)) onToggleScenario(s.id)
    })
  }

  return (
    <div className="card">
      <h2>
        Cost projection
        <InfoIcon text="Compare cumulative £ cost over time across every combination of Solar, Wind and Insulation. Year 0 starts at each scenario's capex; each year adds net running cost using the best tariff's unit rate, standing charge, and your chosen export price." />
      </h2>

      <div className="form-row col2">
        <div>
          <label htmlFor="projection_solar_tier">
            Projection solar kit tier
            <InfoIcon text="Budget / mid / premium here only changes modelled capex and yield for the fixed projection sizes — not the main optimiser step." />
          </label>
          <select
            id="projection_solar_tier"
            value={projectionSolarTier}
            onChange={(e) => onProjectionSolarTier(e.target.value)}
          >
            {PROJECTION_TIERS.map((id) => (
              <option key={id} value={id}>
                {SOLAR_TIER_INFO[id]?.label || id}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="projection_wind_tier">
            Projection wind kit tier
            <InfoIcon text="Same as solar: projection-only equipment band; independent of the optimiser wind tier." />
          </label>
          <select
            id="projection_wind_tier"
            value={projectionWindTier}
            onChange={(e) => onProjectionWindTier(e.target.value)}
          >
            {PROJECTION_TIERS.map((id) => (
              <option key={id} value={id}>
                {WIND_TIER_INFO[id]?.label || id}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-row">
        <div>
          <label htmlFor="projection_years">Projection time horizon ({maxYears} years)</label>
          <input
            id="projection_years"
            type="range"
            min={1}
            max={20}
            step={1}
            value={maxYears}
            onChange={(e) => onYearsChange(Number(e.target.value))}
          />
          <p className="field-hint">Longer horizons make capex-heavy options look better if annual bills are much lower.</p>
        </div>
      </div>

      <div className="form-row">
        <div>
          <div className="scenario-select-header">
            <label style={{ margin: 0 }}>
              Scenarios to show
              <InfoIcon text="Tick any combination of upgrades to plot. Each scenario keeps your chosen heat pump setting and tariff; only Solar / Wind / Insulation change across lines." />
            </label>
            <div className="scenario-select-actions">
              <button type="button" className="btn btn-sm" onClick={selectAll} disabled={!series.length}>Select all</button>
              <button type="button" className="btn btn-sm" onClick={clearAll} disabled={!series.length}>Clear</button>
            </div>
          </div>

          {groupKeys.length === 0 ? (
            <p className="hint">Scenarios will appear here once the projection loads.</p>
          ) : (
            <div className="scenario-groups">
              {groupKeys.map((count) => (
                <div key={count} className="scenario-group">
                  <p className="scenario-group-title">{groupLabel(count)}</p>
                  <div className="scenario-grid">
                    {grouped[count].map((s) => {
                      const techs = techsForSeries(s)
                      const checked = selectedScenarioIds.includes(s.id)
                      const colour = colourForId(s.id)
                      return (
                        <label key={s.id} className={`scenario-card ${checked ? 'checked' : ''}`}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => onToggleScenario(s.id)}
                          />
                          <span className="scenario-swatch" style={{ background: checked ? colour : 'transparent', borderColor: colour }} />
                          <span className="scenario-card-body">
                            <span className="scenario-card-title">{s.label}</span>
                            <TechBadges techs={techs} />
                            <span className="scenario-card-stats">
                              <span>Capex £{Math.round(s.capex_gbp || 0).toLocaleString('en-GB')}</span>
                              <span>/yr £{Math.round(s.annual_running_gbp || 0).toLocaleString('en-GB')}</span>
                            </span>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <p className="hint">Updating projection…</p>
      ) : rows.length > 0 && shown.length > 0 ? (
        <>
          <p className="field-hint">
            Tariff basis: {projection?.tariff_label || 'selected tariff'} · Unit £{((projection?.unit_rate_p_per_kwh || 0) / 100).toFixed(3)}/kWh · Standing £{((projection?.standing_charge_p_per_day || 0) / 100).toFixed(3)}/day
          </p>
          <div style={{ width: '100%', height: 360 }}>
            <ResponsiveContainer>
              <LineChart data={rows} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" label={{ value: 'Year', position: 'insideBottomRight', offset: -4 }} />
                <YAxis tickFormatter={(v) => `£${Math.round(v)}`} />
                <Tooltip formatter={(v) => `£${Number(v).toFixed(2)}`} />
                <Legend />
                {shown.map((s) => (
                  <Line
                    key={s.id}
                    type="monotone"
                    dataKey={s.id}
                    name={s.label}
                    stroke={colourForId(s.id)}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p className="hint">
          {shown.length === 0 && series.length > 0
            ? 'Tick at least one scenario above to see the projection.'
            : 'No projection data yet.'}
        </p>
      )}
    </div>
  )
}
