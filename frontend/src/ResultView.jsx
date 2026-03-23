import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'

export function ResultView({ result }) {
  const opt = result.optimization
  const best = result.recommended_tariff
  const years = result.optimize_over_years
  const monthly = Array.isArray(result.monthly_balance) ? result.monthly_balance : []
  const baselineMonthly = Number(opt.annual_demand_before_adjustments_kwh || 0) / 12
  const adjustedMonthly = Number(opt.annual_demand_kwh || 0) / 12
  const chartData = monthly.map((m, idx) => ({
    month: m.month || ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][idx],
    solar_kwh: Number(m.solar_kwh || 0),
    wind_kwh: Number(m.wind_kwh || 0),
    demand_kwh: Number(m.demand_kwh || 0),
    usage_before_kwh: baselineMonthly,
    usage_after_kwh: Number(m.demand_kwh || adjustedMonthly || 0),
  }))

  const tiles = [
    { value: opt.optimal_solar_kw, label: 'Solar (kW)' },
    { value: opt.optimal_wind_kw, label: 'Wind (kW)' },
    { value: opt.total_capacity_kw, label: 'Total capacity (kW)' },
    { value: opt.annual_demand_kwh != null ? opt.annual_demand_kwh.toFixed(1) : '—', label: 'Annual demand (kWh)' },
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
    <div className="dashboard-grid">
      <div className="card dashboard-card dashboard-card-wide">
        <h2>Recommended system</h2>
        <div className="result-grid system-grid">
          {tiles.map(({ value, label }) => (
            <div key={label} className="result-tile">
              <div className="value">{value}</div>
              <div className="label">{label}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: '0.45rem' }}>
          <h2 style={{ marginBottom: '0.45rem' }}>Yearly profile: solar, wind, insulation and usage</h2>
          <p className="hint" style={{ marginBottom: '0.55rem' }}>
            Insulation R-value: {opt.insulation_r_value} · Heating fraction: {(opt.heating_fraction * 100).toFixed(0)}% · Heat pump COP: {opt.heat_pump_cop}
          </p>
          {chartData.length > 0 ? (
            <div style={{ width: '100%', height: 210 }}>
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 2 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="solar_kwh" name="Solar generation (kWh)" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="wind_kwh" name="Wind generation (kWh)" stroke="#60a5fa" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="usage_before_kwh" name="Usage before insulation (kWh)" stroke="#f87171" strokeWidth={2} strokeDasharray="6 3" dot={false} />
                  <Line type="monotone" dataKey="usage_after_kwh" name="Usage after insulation/HP (kWh)" stroke="#34d399" strokeWidth={2} strokeDasharray="4 2" dot={false} />
                  <Line type="monotone" dataKey="demand_kwh" name="Demand profile used by optimiser (kWh)" stroke="#a78bfa" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="hint">Monthly data unavailable for this run.</p>
          )}
        </div>
      </div>

      <div className="card recommended-tariff dashboard-card">
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

      <div className="card dashboard-card">
        <h2>Tariff ranking (total cost over {years} years)</h2>
        <ul className="ranking-list">
          {(result.ranking || []).map((r) => (
            <li key={r.rank} className={r.rank === 1 ? 'recommended-row' : ''}>
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

    </div>
  )
}
