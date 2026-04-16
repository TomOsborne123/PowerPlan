import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { InfoIcon } from './InfoIcon'
import { SOLAR_TIER_INFO, WIND_TIER_INFO } from './optimiserConstants'

const PALETTE = ['#f87171', '#60a5fa', '#f59e0b', '#34d399', '#a78bfa', '#22d3ee']

const PROJECTION_TIERS = ['budget', 'mid', 'premium']

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

  return (
    <div className="card">
      <h2>
        Cost projection
        <InfoIcon text="Each scenario builds on the last: baseline grid-only, then add solar, then add wind (keeping solar), then upgrade insulation. Cumulative £ uses the best tariff’s unit rate and standing charge." />
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

      <div className="form-row col2">
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
        <div>
          <label>Show steps</label>
          <div className="checkbox-group">
            {series.map((s) => (
              <label key={s.id} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedScenarioIds.includes(s.id)}
                  onChange={() => onToggleScenario(s.id)}
                />
                <span>{s.label}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <p className="hint">Updating projection…</p>
      ) : rows.length > 0 && shown.length > 0 ? (
        <>
          <p className="field-hint">
            Tariff basis: {projection?.tariff_label || 'selected tariff'} · Unit £{((projection?.unit_rate_p_per_kwh || 0) / 100).toFixed(3)}/kWh · Standing £{((projection?.standing_charge_p_per_day || 0) / 100).toFixed(3)}/day
          </p>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={rows} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" label={{ value: 'Year', position: 'insideBottomRight', offset: -4 }} />
                <YAxis tickFormatter={(v) => `£${Math.round(v)}`} />
                <Tooltip formatter={(v) => `£${Number(v).toFixed(2)}`} />
                <Legend />
                {shown.map((s, i) => (
                  <Line key={s.id} type="monotone" dataKey={s.id} name={s.label} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p className="hint">No projection data yet.</p>
      )}
    </div>
  )
}

