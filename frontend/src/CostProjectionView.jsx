import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { InfoIcon } from './InfoIcon'
import { SOLAR_TIER_INFO, WIND_TIER_INFO, BATTERY_TIER_INFO } from './optimiserConstants'

const PROJECTION_TIERS = ['budget', 'mid', 'premium']
const BATTERY_PROJECTION_TIERS = ['none', 'budget', 'mid', 'premium']

// Canonical order used to build the combo scenario id sent by the backend:
//   combo_baseline, combo_solar, combo_solar_wind, combo_solar_wind_insulation,
//   combo_solar_battery, combo_solar_wind_insulation_battery, …
// Battery is only emitted by the backend when scenario_battery_kwh > 0 AND the
// combo already contains solar or wind, so we keep it last to match.
const TECH_ORDER = ['solar', 'wind', 'insulation', 'battery']

const TECHS = [
  { key: 'solar', label: 'Solar', hint: 'Rooftop PV', bg: '#fde68a', fg: '#92400e', line: '#f59e0b' },
  { key: 'wind', label: 'Wind', hint: 'Small wind turbine', bg: '#bae6fd', fg: '#075985', line: '#0ea5e9' },
  { key: 'insulation', label: 'Insulation', hint: 'Stronger fabric', bg: '#bbf7d0', fg: '#14532d', line: '#22c55e' },
  { key: 'battery', label: 'Battery', hint: 'Home battery storage', bg: '#ddd6fe', fg: '#3730a3', line: '#6366f1' },
]

const BASELINE_COLOUR = '#94a3b8'
const OVERLAY_COLOUR = '#2563eb'

function comboIdFor(techs) {
  const ordered = TECH_ORDER.filter((t) => techs.includes(t))
  if (ordered.length === 0) return 'combo_baseline'
  return 'combo_' + ordered.join('_')
}

function fmtGbp(n) {
  const v = Math.round(Number(n) || 0)
  const sign = v < 0 ? '-£' : '£'
  return sign + Math.abs(v).toLocaleString('en-GB')
}

function breakEvenYear(baseline, overlay) {
  if (!baseline || !overlay) return null
  const baseArr = baseline.cumulative_gbp || []
  const overArr = overlay.cumulative_gbp || []
  const n = Math.min(baseArr.length, overArr.length)
  for (let i = 0; i < n; i++) {
    if (Number(overArr[i]) <= Number(baseArr[i])) return i + 1
  }
  return null
}

function tariffLabelFor(entry) {
  const t = entry?.tariff || {}
  const supplier = t.supplier_name || '—'
  const name = t.tariff_name ? ` — ${t.tariff_name}` : ''
  const bill = Number(entry?.opex_per_year_gbp)
  const billStr = Number.isFinite(bill) ? ` · ${fmtGbp(bill)}/yr` : ''
  return `#${entry?.rank ?? '?'} ${supplier}${name}${billStr}`
}

function triggerProjectionPrint() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return
  const cls = 'printing-projection'
  document.body.classList.add(cls)
  const cleanup = () => {
    document.body.classList.remove(cls)
    window.removeEventListener('afterprint', cleanup)
  }
  window.addEventListener('afterprint', cleanup)
  // Slight delay so the class is applied before the print preview renders.
  window.setTimeout(() => {
    try {
      window.print()
    } finally {
      // Some browsers don't fire afterprint reliably; ensure cleanup.
      window.setTimeout(cleanup, 1500)
    }
  }, 50)
}

export function CostProjectionView({
  projection,
  maxYears,
  onYearsChange,
  selectedTechs,
  onToggleTech,
  projectionSolarTier,
  projectionWindTier,
  projectionBatteryTier,
  onProjectionSolarTier,
  onProjectionWindTier,
  onProjectionBatteryTier,
  tariffOptions = [],
  selectedTariffRank,
  onSelectTariffRank,
  loading = false,
}) {
  const years = Array.isArray(projection?.years) ? projection.years : []
  const series = Array.isArray(projection?.series) ? projection.series : []
  const seriesById = Object.fromEntries(series.map((s) => [s.id, s]))

  const baseline = seriesById.combo_baseline || null
  const overlayId = comboIdFor(selectedTechs)
  const hasOverlay = overlayId !== 'combo_baseline'
  const overlay = hasOverlay ? seriesById[overlayId] : null

  const rows = years.map((y, idx) => {
    const row = { year: y }
    if (baseline) row.baseline = Number(baseline.cumulative_gbp?.[idx] ?? 0)
    if (overlay) row.overlay = Number(overlay.cumulative_gbp?.[idx] ?? 0)
    return row
  })

  const finalBaseline = baseline?.cumulative_gbp?.[baseline.cumulative_gbp.length - 1]
  const finalOverlay = overlay?.cumulative_gbp?.[overlay.cumulative_gbp.length - 1]
  const totalDelta = overlay && baseline ? Number(finalOverlay) - Number(finalBaseline) : null
  const savesMoney = totalDelta != null && totalDelta < 0
  const breakEven = hasOverlay ? breakEvenYear(baseline, overlay) : null

  const overlayLabel = overlay?.label || (hasOverlay ? 'Your upgrade plan' : 'Baseline')

  const validTariffs = Array.isArray(tariffOptions)
    ? tariffOptions.filter((entry) => entry && entry.tariff)
    : []
  const hasTariffPicker = validTariffs.length > 0 && typeof onSelectTariffRank === 'function'

  return (
    <div className="card projection-print-target">
      <div className="projection-card-header">
        <h2 style={{ marginBottom: 0 }}>
          Cost projection
          <InfoIcon text="Start with the baseline (grid only). Toggle upgrades below to overlay a single 'your plan' line showing cumulative £ over time with that combination of technologies." />
        </h2>
        <button
          type="button"
          className="btn btn-sm projection-export-btn no-print"
          onClick={triggerProjectionPrint}
          disabled={loading || !baseline}
          title="Save the cost projection card as a PDF using your browser's print dialog (choose 'Save as PDF')."
        >
          Export to PDF
        </button>
      </div>

      {hasTariffPicker && (
        <div className="form-row no-print">
          <div>
            <label htmlFor="projection_tariff">
              Tariff to plot
              <InfoIcon text="Re-runs the projection using the selected tariff's unit rate and standing charge. Useful for comparing how upgrades pay back under different tariffs." />
            </label>
            <select
              id="projection_tariff"
              value={selectedTariffRank ?? validTariffs[0]?.rank}
              onChange={(e) => onSelectTariffRank(Number(e.target.value))}
              className="projection-tariff-select"
            >
              {validTariffs.map((entry) => (
                <option key={entry.rank} value={entry.rank}>
                  {tariffLabelFor(entry)}
                </option>
              ))}
            </select>
            <p className="field-hint">
              Defaults to the optimiser's #1 ranked tariff. Pick any other to see how the same upgrade plan changes its payback story.
            </p>
          </div>
        </div>
      )}

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
          <label htmlFor="projection_battery_tier">
            Projection battery kit tier
            <InfoIcon text="Battery cost band used when 'Battery' is added as a projection upgrade. Choose 'No battery' to remove storage from this view." />
          </label>
          <select
            id="projection_battery_tier"
            value={projectionBatteryTier || 'none'}
            onChange={(e) => onProjectionBatteryTier && onProjectionBatteryTier(e.target.value)}
          >
            {BATTERY_PROJECTION_TIERS.map((id) => (
              <option key={id} value={id}>
                {BATTERY_TIER_INFO[id]?.label || id}
              </option>
            ))}
          </select>
        </div>
        <div />
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
          <label className="block-label" style={{ marginBottom: '0.5rem' }}>
            Upgrades to overlay on the baseline
            <InfoIcon text="Tap a technology to add it to your plan. The chart always shows the baseline (grid only) in grey and overlays a single blue line for the combination you pick." />
          </label>

          <div className="tech-toggle-row">
            {TECHS.map((t) => {
              if (t.key === 'battery' && (projectionBatteryTier === 'none' || !projectionBatteryTier)) {
                return null
              }
              const active = selectedTechs.includes(t.key)
              const hasGen = selectedTechs.includes('solar') || selectedTechs.includes('wind')
              const disabled = t.key === 'battery' && !hasGen
              const scenario = seriesById['combo_' + t.key]
              const delta = scenario && baseline
                ? Number(scenario.cumulative_gbp?.[scenario.cumulative_gbp.length - 1] ?? 0)
                  - Number(baseline.cumulative_gbp?.[baseline.cumulative_gbp.length - 1] ?? 0)
                : null
              return (
                <button
                  type="button"
                  key={t.key}
                  className={`tech-toggle ${active ? 'active' : ''}`}
                  onClick={() => !disabled && onToggleTech(t.key)}
                  disabled={disabled}
                  style={active
                    ? { borderColor: t.line, background: t.bg, color: t.fg }
                    : undefined}
                  aria-pressed={active}
                  title={disabled ? 'Add solar or wind first to model a battery upgrade.' : undefined}
                >
                  <span className="tech-toggle-title">{t.label}</span>
                  <span className="tech-toggle-hint">
                    {disabled ? 'Needs solar or wind' : t.hint}
                  </span>
                  {delta != null ? (
                    <span className={`tech-toggle-delta ${delta < 0 ? 'saves' : 'costs'}`}>
                      {delta < 0 ? 'Saves ' : 'Costs '}
                      {fmtGbp(Math.abs(delta))} over {maxYears}y on its own
                    </span>
                  ) : null}
                </button>
              )
            })}
          </div>

          {hasOverlay && (
            <button
              type="button"
              className="btn btn-sm tech-toggle-reset"
              onClick={() => selectedTechs.forEach((t) => onToggleTech(t))}
            >
              Reset to baseline
            </button>
          )}
        </div>
      </div>

      {(baseline || overlay) && (
        <div className="projection-summary">
          <div className="projection-summary-col">
            <span className="projection-summary-label">Baseline (grid only)</span>
            <span className="projection-summary-value">
              {fmtGbp(finalBaseline)} <small>over {maxYears}y</small>
            </span>
            <span className="projection-summary-sub">
              Capex {fmtGbp(baseline?.capex_gbp)} · Running {fmtGbp(baseline?.annual_running_gbp)}/yr
            </span>
          </div>
          <div className="projection-summary-arrow" aria-hidden="true">→</div>
          <div className="projection-summary-col">
            <span className="projection-summary-label">
              {hasOverlay ? 'Your plan' : 'No upgrades selected'}
            </span>
            <span className="projection-summary-value" style={{ color: hasOverlay ? OVERLAY_COLOUR : undefined }}>
              {overlay ? fmtGbp(finalOverlay) : '—'} {overlay ? <small>over {maxYears}y</small> : null}
            </span>
            <span className="projection-summary-sub">
              {overlay
                ? <>Capex {fmtGbp(overlay.capex_gbp)} · Running {fmtGbp(overlay.annual_running_gbp)}/yr</>
                : 'Tap a technology above to overlay a plan.'}
            </span>
          </div>
          {overlay && (
            <div className={`projection-summary-delta ${savesMoney ? 'saves' : 'costs'}`}>
              <span className="projection-summary-delta-value">
                {savesMoney ? 'Saves ' : 'Costs '}
                {fmtGbp(Math.abs(totalDelta || 0))}
              </span>
              <span className="projection-summary-delta-sub">
                total over {maxYears}y{breakEven ? ` · break-even year ${breakEven}` : savesMoney ? '' : ' (no break-even in window)'}
              </span>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <p className="hint">Updating projection…</p>
      ) : rows.length > 0 && baseline ? (
        <>
          <p className="field-hint">
            Tariff basis: {projection?.tariff_label || 'selected tariff'} · Unit £{((projection?.unit_rate_p_per_kwh || 0) / 100).toFixed(3)}/kWh · Standing £{((projection?.standing_charge_p_per_day || 0) / 100).toFixed(3)}/day
          </p>
          <div style={{ width: '100%', height: 390 }}>
            <ResponsiveContainer>
              <LineChart data={rows} margin={{ top: 12, right: 16, left: 22, bottom: 42 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="year"
                  tick={{ fontSize: 12 }}
                  height={56}
                  label={{ value: 'Year', position: 'bottom', offset: 18, style: { fontSize: 14, fontWeight: 600 } }}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v) => `£${Math.round(v)}`}
                  label={{ value: 'Cumulative cost (£)', angle: -90, position: 'left', offset: 8, style: { textAnchor: 'middle', fontSize: 14, fontWeight: 600 } }}
                />
                <Tooltip formatter={(v) => `£${Number(v).toFixed(2)}`} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="baseline"
                  name={baseline.label}
                  stroke={BASELINE_COLOUR}
                  strokeDasharray="4 4"
                  strokeWidth={2}
                  dot={false}
                />
                {overlay && (
                  <Line
                    type="monotone"
                    dataKey="overlay"
                    name={overlayLabel}
                    stroke={OVERLAY_COLOUR}
                    strokeWidth={3}
                    dot={false}
                  />
                )}
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
