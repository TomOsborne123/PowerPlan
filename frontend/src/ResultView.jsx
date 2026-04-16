import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { InfoIcon } from './InfoIcon'

export function ResultView({ result, optimiserControls }) {
  const opt = result.optimization
  const best = result.recommended_tariff
  const years = result.optimize_over_years
  const monthly = Array.isArray(result.monthly_balance) ? result.monthly_balance : []

  function TariffName({ tariff }) {
    const text = `${tariff?.supplier_name || '—'} — ${tariff?.tariff_name || ''}`.trim()
    return <span className="tariff-name-cell" title={text}>{text}</span>
  }

  function typicalMonthlyWeights() {
    // winter_factor peaks in January (month 0) and bottoms in July (month 6)
    const winterFactor = Array.from({ length: 12 }, (_, m) => 0.5 + 0.5 * Math.cos((2.0 * Math.PI * (m / 12.0))))
    // Sharper winter peak for the heating component.
    const heatingRaw = winterFactor.map((wf) => 0.05 + 0.95 * Math.pow(wf, 1.5))
    const nonHeatingRaw = winterFactor.map((wf) => 0.08 + 0.12 * wf)

    const heatingSum = heatingRaw.reduce((a, b) => a + b, 0) || 1
    const nonHeatingSum = nonHeatingRaw.reduce((a, b) => a + b, 0) || 1

    const heatingWeights = heatingRaw.map((x) => x / heatingSum)
    const nonHeatingWeights = nonHeatingRaw.map((x) => x / nonHeatingSum)
    return { nonHeatingWeights, heatingWeights }
  }

  const { nonHeatingWeights, heatingWeights } = typicalMonthlyWeights()

  const totalBefore = Number(opt.annual_demand_before_adjustments_kwh || 0)
  const heatingFraction = Number(opt.heating_fraction || 0)
  const heatingBeforeKwh = totalBefore * heatingFraction
  const nonHeatingBeforeKwh = totalBefore - heatingBeforeKwh

  // After insulation only (thermal demand). This should differ from optimiser demand (electricity after heat-pump COP).
  const totalAfter = Number(opt.annual_demand_after_insulation_kwh || 0)
  const heatingAfterInsulationKwh = Number(opt.heating_demand_after_insulation_kwh || 0)
  const nonHeatingAfterKwh = totalAfter - heatingAfterInsulationKwh

  const chartData = monthly.map((m, idx) => ({
    month: m.month || ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][idx],
    solar_kwh: Number(m.solar_kwh || 0),
    wind_kwh: Number(m.wind_kwh || 0),
    demand_kwh: Number(m.demand_kwh || 0),
    usage_before_kwh: (nonHeatingBeforeKwh * nonHeatingWeights[idx]) + (heatingBeforeKwh * heatingWeights[idx]),
    usage_after_kwh: (nonHeatingAfterKwh * nonHeatingWeights[idx]) + (heatingAfterInsulationKwh * heatingWeights[idx]),
  }))

  function CustomTooltip({ active, payload, label }) {
    if (!active || !payload || payload.length === 0) return null

    const orderedNames = ['Solar', 'Wind', 'Usage', 'Heating with adjusted insulation', 'Net electricity demand']
    const normalized = payload
      .map((p) => {
        const v = typeof p?.value === 'number' ? p.value : Number(p?.value)
        const name = p?.name || p?.dataKey || '—'
        return { name, value: v }
      })
      .filter((x) => Number.isFinite(x.value))

    // Sort so tooltip order stays consistent.
    normalized.sort((a, b) => {
      const ai = orderedNames.indexOf(a.name)
      const bi = orderedNames.indexOf(b.name)
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
    })

    return (
      <div className="custom-hover-tooltip" role="status" aria-live="polite">
        <div className="custom-hover-title">{label ? String(label) : 'Hover values'}</div>
        <div className="custom-hover-stack">
          {normalized.map((p) => (
            <div key={p.name} className="custom-hover-row">
              <span className="custom-hover-name">{p.name}</span>
              <span className="custom-hover-sep">:</span>
              <span className="custom-hover-value">{p.value.toFixed(2)} kWh (this month)</span>
            </div>
          ))}
          {normalized.length === 0 ? <div className="custom-hover-value">—</div> : null}
        </div>
      </div>
    )
  }

  const tiles = [
    { value: opt.optimal_solar_kw, label: 'Solar (kW)', info: 'Optimal solar capacity selected by the optimiser.' },
    { value: opt.optimal_wind_kw, label: 'Wind (kW)', info: 'Optimal wind capacity selected by the optimiser.' },
    { value: opt.total_capacity_kw, label: 'Total capacity (kW)', info: 'Solar + wind capacities added together.' },
    { value: opt.annual_demand_kwh != null ? opt.annual_demand_kwh.toFixed(1) : '—', label: 'Annual demand (kWh)', info: 'Annual electricity demand used for optimisation.' },
    { value: Math.round(opt.annual_generation_kwh), label: 'Annual generation (kWh)', info: 'Total annual generation from the chosen solar + wind sizes.' },
    { value: Math.round(opt.annual_import_kwh), label: 'Import (kWh/yr)', info: 'Annual energy imported from the grid.' },
    { value: Math.round(opt.annual_export_kwh), label: 'Export (kWh/yr)', info: 'Annual energy exported to the grid.' },
    { value: `${opt.demand_met_from_generation_pct.toFixed(1)}%`, label: 'Demand from own gen', info: 'Percentage of your demand met by on-site solar + wind.' },
    { value: `£${Math.round(opt.capex)}`, label: 'Capex', info: 'Total upfront cost (solar + wind) from the selected tier assumptions.' },
    { value: opt.payback_solar_years != null ? `${opt.payback_solar_years} yr` : '—', label: 'Solar payback', info: 'Estimated years to recover solar capex from savings/revenue.' },
    { value: opt.payback_wind_years != null ? `${opt.payback_wind_years} yr` : '—', label: 'Wind payback', info: 'Estimated years to recover wind capex from savings/revenue.' },
  ]

  const annualTotalInclCapexFor = (r) => {
    // `total_cost_gbp` is capex + opex over the optimisation horizon.
    // Convert it to an annual average so it's comparable on a £/yr basis.
    const total = Number(r?.total_cost_gbp)
    const y = Number(years)
    if (!Number.isFinite(total) || !Number.isFinite(y) || y <= 0) return null
    return total / y
  }

  const annualBillFor = (r) => {
    const v = Number(r?.opex_per_year_gbp)
    return Number.isFinite(v) ? v : null
  }

  const unitRateForTariff = (tariff) => {
    const v = Number(tariff?.unit_rate_p_per_kwh ?? tariff?.unit_rate)
    if (!Number.isFinite(v)) return '—'
    return `${(v / 100).toFixed(3)}`
  }

  const standingChargeForTariff = (tariff) => {
    const v = Number(tariff?.standing_charge_p_per_day ?? tariff?.standing_charge_day)
    if (!Number.isFinite(v)) return '—'
    return `${(v / 100).toFixed(3)}`
  }

  return (
    <div className="dashboard-layout">
      <div className="dashboard-left">
        <div className="card dashboard-card dashboard-card-wide">
          <h2>
            System
            <InfoIcon text="Optimal solar/wind sizing and resulting annual totals." />
          </h2>
          <div className="result-grid system-grid">
            {tiles.map(({ value, label, info }) => (
              <div key={label} className="result-tile">
                <div className="value">{value}</div>
                <div className="label">
                  <span className="tile-label">{label}</span>
                  <InfoIcon text={info} />
                </div>
              </div>
            ))}
          </div>

          <details className="ranking-menu" open>
            <summary>Graph ▾</summary>
            <p className="field-hint" style={{ marginTop: 0 }}>
              Each point is energy for that calendar month (kWh/month). Summary tiles above are full-year totals (kWh/yr or £/yr).
            </p>
            <div className="graph-metric-notes">
              <span className="graph-metric">
                Solar <InfoIcon text="Electricity generated in that month from the optimiser-chosen solar capacity (not an annual figure)." />
              </span>
              <span className="graph-metric">
                Wind <InfoIcon text="Electricity generated in that month from the optimiser-chosen wind capacity (not an annual figure)." />
              </span>
              <span className="graph-metric">
                Usage <InfoIcon text="Estimated electricity use in that month from your baseline annual demand and a typical UK seasonal split (before insulation / heat-pump adjustments)." />
              </span>
              <span className="graph-metric">
                Heating with adjusted insulation <InfoIcon text="Estimated monthly heating demand after the selected insulation level has reduced heat loss, before any heat-pump efficiency adjustment." />
              </span>
              <span className="graph-metric">
                Net electricity demand <InfoIcon text="Estimated monthly electricity demand after insulation and heat-pump effects are applied. This is the final demand the model compares against solar and wind generation." />
              </span>
            </div>
            <div className="chart-legend" aria-label="Graph legend">
              <span className="chart-legend-item">
                <span className="chart-legend-line solar" aria-hidden="true" />
                Solar
              </span>
              <span className="chart-legend-item">
                <span className="chart-legend-line wind" aria-hidden="true" />
                Wind
              </span>
              <span className="chart-legend-item">
                <span className="chart-legend-line usage" aria-hidden="true" />
                Usage
              </span>
              <span className="chart-legend-item">
                <span className="chart-legend-line thermal" aria-hidden="true" />
                Heating with adjusted insulation
              </span>
              <span className="chart-legend-item">
                <span className="chart-legend-line demand" aria-hidden="true" />
                Net electricity demand
              </span>
            </div>
            {chartData.length > 0 ? (
              <div style={{ width: '100%', height: 170 }}>
                <ResponsiveContainer>
                  <LineChart data={chartData} margin={{ top: 6, right: 12, left: 4, bottom: 2 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis
                      width={44}
                      label={{ value: 'kWh / month', angle: -90, position: 'insideLeft', offset: 10, style: { textAnchor: 'middle', fontSize: 11 } }}
                    />
                    <Tooltip content={(props) => <CustomTooltip {...props} />} />
                    <Line type="monotone" dataKey="solar_kwh" name="Solar" stroke="#f59e0b" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="wind_kwh" name="Wind" stroke="#60a5fa" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="usage_before_kwh" name="Usage" stroke="#f87171" strokeWidth={2} strokeDasharray="6 3" dot={false} />
                    <Line type="monotone" dataKey="usage_after_kwh" name="Heating with adjusted insulation" stroke="#34d399" strokeWidth={2} strokeDasharray="4 2" dot={false} />
                    <Line type="monotone" dataKey="demand_kwh" name="Net electricity demand" stroke="#a78bfa" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="hint">No monthly data.</p>
            )}
          </details>

          {optimiserControls ? (
            <div className="optimiser-inline">
              <div className="optimiser-controls">{optimiserControls}</div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="dashboard-right">
        <div className="card dashboard-card">
          <h2>
            Tariffs
            <InfoIcon text="Tariff ranking scored using the optimiser's solar/wind import/export and the chosen export price." />
          </h2>
          {best ? (
            <ul className="ranking-list ranking-list-compact">
              <li className="ranking-header" aria-hidden="true">
                <span className="rank">#</span>
                <span>Tariff</span>
                <span className="unit">Unit (£/kWh)</span>
                <span className="standing">Standing (£/day)</span>
                <span className="bill">Bill (£/yr)</span>
                <span className="total">Total incl capex (£/yr)</span>
              </li>
              {result.ranking && result.ranking[0] ? (
                <li className="recommended-row">
                  <span className="rank">#1</span>
                  <span className="tariff-name-wrap">
                    <TariffName tariff={result.ranking[0].tariff} />
                    {result.ranking[0].tariff.is_green && <span className="green"> ●</span>}
                  </span>
                  <span className="unit">{unitRateForTariff(result.ranking[0].tariff)}</span>
                  <span className="standing">{standingChargeForTariff(result.ranking[0].tariff)}</span>
                  <span className="bill">
                    {annualBillFor(result.ranking[0]) != null ? `£${annualBillFor(result.ranking[0]).toFixed(2)}` : '—'}
                  </span>
                  <span className="total">
                    {annualTotalInclCapexFor(result.ranking[0]) != null ? `£${annualTotalInclCapexFor(result.ranking[0]).toFixed(2)}` : '—'}
                  </span>
                </li>
              ) : (
                <li className="recommended-row">
                  <span className="rank">#1</span>
                  <span className="tariff-name-wrap">
                    <TariffName tariff={best} />
                    {best.is_green && <span className="green"> ●</span>}
                  </span>
                  <span className="unit">{unitRateForTariff(best)}</span>
                  <span className="standing">{standingChargeForTariff(best)}</span>
                  <span className="bill">—</span>
                  <span className="total">—</span>
                </li>
              )}
            </ul>
          ) : (
            <p className="hint">No tariffs.</p>
          )}

          <details className="ranking-menu" open={true}>
            <summary>Tariff ranking ▾</summary>
            <ul className="ranking-list ranking-list-compact">
              <li className="ranking-header" aria-hidden="true">
                <span className="rank">#</span>
                <span>Tariff</span>
                <span className="unit">Unit (£/kWh)</span>
                <span className="standing">Standing (£/day)</span>
                <span className="bill">Bill (£/yr)</span>
                <span className="total">Total incl capex (£/yr)</span>
              </li>
              {(result.ranking || []).slice(1).map((r) => (
                <li key={r.rank} className="">
                  <span className="rank">#{r.rank}</span>
                  <span className="tariff-name-wrap">
                    <TariffName tariff={r.tariff} />
                    {r.tariff.is_green && <span className="green"> ●</span>}
                  </span>
                  <span className="unit">{unitRateForTariff(r.tariff)}</span>
                  <span className="standing">{standingChargeForTariff(r.tariff)}</span>
                  <span className="bill">
                    {annualBillFor(r) != null ? `£${annualBillFor(r).toFixed(2)}` : '—'}
                  </span>
                  <span className="total">
                    {annualTotalInclCapexFor(r) != null ? `£${annualTotalInclCapexFor(r).toFixed(2)}` : '—'}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>
    </div>
  )
}
