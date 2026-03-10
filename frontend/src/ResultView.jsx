export function ResultView({ result }) {
  const opt = result.optimization
  const best = result.recommended_tariff
  const years = result.optimize_over_years

  const tiles = [
    { value: opt.optimal_solar_kw, label: 'Solar (kW)' },
    { value: opt.optimal_wind_kw, label: 'Wind (kW)' },
    { value: opt.total_capacity_kw, label: 'Total capacity (kW)' },
    { value: Math.round(opt.annual_demand_kwh), label: 'Annual demand (kWh)' },
    { value: Math.round(opt.annual_generation_kwh), label: 'Annual generation (kWh)' },
    { value: Math.round(opt.annual_import_kwh), label: 'Import (kWh/yr)' },
    { value: Math.round(opt.annual_export_kwh), label: 'Export (kWh/yr)' },
    { value: `${opt.demand_met_from_generation_pct.toFixed(1)}%`, label: 'Demand from own gen' },
    { value: `£${Math.round(opt.capex)}`, label: 'Capex' },
    {
      value: opt.payback_solar_years != null ? `${opt.payback_solar_years} yr` : '—',
      label: 'Solar payback',
    },
    {
      value: opt.payback_wind_years != null ? `${opt.payback_wind_years} yr` : '—',
      label: 'Wind payback',
    },
  ]

  return (
    <>
      <div className="card">
        <h2>Recommended system</h2>
        <div className="result-grid">
          {tiles.map(({ value, label }) => (
            <div key={label} className="result-tile">
              <div className="value">{value}</div>
              <div className="label">{label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card recommended-tariff">
        <h2>Recommended tariff</h2>
        {best ? (
          <div>
            <div className="name">
              {best.supplier_name} — {best.tariff_name}
            </div>
            <div className="hint" style={{ marginTop: '0.5rem' }}>
              Unit rate {best.unit_rate_p_per_kwh}p/kWh · Standing charge {best.standing_charge_p_per_day}p/day
              {best.is_green && <span className="green"> · Green</span>}
            </div>
            <div style={{ marginTop: '0.5rem', fontWeight: 600 }}>
              Total cost over {years} years: £{result.total_cost_best_gbp.toFixed(2)}
            </div>
          </div>
        ) : (
          <p className="hint">No tariffs to compare.</p>
        )}
      </div>

      <div className="card">
        <h2>Tariff ranking (total cost over {years} years)</h2>
        <ul className="ranking-list">
          {(result.ranking || []).map((r) => (
            <li key={r.rank}>
              <span className="rank">#{r.rank}</span>
              <span>
                {r.tariff.supplier_name} — {r.tariff.tariff_name}
                {r.tariff.is_green && <span className="green"> ●</span>}
              </span>
              <span className="total">£{r.total_cost_gbp.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
