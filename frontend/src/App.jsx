import { useState, useEffect } from 'react'
import { usePostcodeLookup, fetchRecommend, fetchScrapeResults, fetchRunScrape, fetchScrapeStatus } from './api'
import { ResultView } from './ResultView'

export function App() {
  const [postcode, setPostcode] = useState('')
  const [latitude, setLatitude] = useState(null)
  const [longitude, setLongitude] = useState(null)
  const [annualConsumptionKwh, setAnnualConsumptionKwh] = useState('')
  const [scrapeLoaded, setScrapeLoaded] = useState(false)
  const [scrapeTariffCount, setScrapeTariffCount] = useState(null)
  const [scraping, setScraping] = useState(false)
  const [heatingFraction, setHeatingFraction] = useState(0.6)
  const [insulationRValue, setInsulationRValue] = useState(0)
  const [heatPumpCop, setHeatPumpCop] = useState(2.5)
  const [solarTier, setSolarTier] = useState('budget')
  const [windTier, setWindTier] = useState('budget')
  const [exportPricePerKwh, setExportPricePerKwh] = useState(0.05)
  const [optimizeOverYears, setOptimizeOverYears] = useState(5)
  const [preferGreen, setPreferGreen] = useState(false)

  const [postcodeStatus, lookupPostcode] = usePostcodeLookup(setLatitude, setLongitude)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (scrapeLoaded) {
      document.getElementById('demand-and-system')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [scrapeLoaded])

  const loadFromScrape = async () => {
    const trimmed = postcode.trim()
    if (!trimmed || trimmed.length < 5) {
      setError('Enter a postcode first')
      return
    }
    setError(null)
    setLoading(true)
    try {
      let data = await fetchScrapeResults(trimmed)
      const hasData = data && !data.no_saved_scrape && data.tariffs?.length > 0
      if (hasData) {
        setAnnualConsumptionKwh(data.annual_electricity_kwh ?? '')
        setLatitude(data.latitude ?? null)
        setLongitude(data.longitude ?? null)
        setScrapeTariffCount((data.tariffs && data.tariffs.length) || 0)
        setScrapeLoaded(true)
        return true
      }
      // No saved scrape: run scrape from the app, then load
      setScraping(true)
      try {
        await fetchRunScrape(trimmed)
      } catch (err) {
        setError(err.message || 'Could not start scrape')
        setScraping(false)
        setLoading(false)
        return false
      }
      // Poll until completed or failed (max ~3 minutes)
      const pollIntervalMs = 5000
      const maxWaitMs = 180000
      const start = Date.now()
      let success = false
      while (Date.now() - start < maxWaitMs) {
        const status = await fetchScrapeStatus(trimmed)
        if (status.status === 'completed') {
          data = await fetchScrapeResults(trimmed)
          if (data) {
            setAnnualConsumptionKwh(data.annual_electricity_kwh ?? '')
            setLatitude(data.latitude ?? null)
            setLongitude(data.longitude ?? null)
            setScrapeTariffCount((data.tariffs && data.tariffs.length) || 0)
            setScrapeLoaded(true)
            setError(null)
            success = true
          }
          break
        }
        if (status.status === 'failed') {
          setError(status.error || 'Scrape failed')
          break
        }
        await new Promise((r) => setTimeout(r, pollIntervalMs))
      }
      if (Date.now() - start >= maxWaitMs) {
        setError('Scrape is taking longer than expected. Try again in a few minutes.')
      }
      return success
    } catch {
      setError('Could not load scrape results')
      return false
    } finally {
      setLoading(false)
      setScraping(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    const trimmed = postcode.trim()
    if (!trimmed || trimmed.length < 5) {
      setError('Please enter a UK postcode.')
      return
    }
    setLoading(true)
    try {
      // If we don't have scrape data yet, run load/scrape first (then show options)
      if (!scrapeLoaded) {
        const loaded = await loadFromScrape()
        if (!loaded) return
      }
      setLoading(true)
      const usage = annualConsumptionKwh === '' || annualConsumptionKwh == null ? undefined : Number(annualConsumptionKwh)
      const data = await fetchRecommend({
        postcode: trimmed,
        latitude: latitude ?? undefined,
        longitude: longitude ?? undefined,
        annual_consumption_kwh: usage,
        heating_fraction: heatingFraction,
        insulation_r_value: insulationRValue,
        heat_pump_cop: heatPumpCop,
        solar_tier: solarTier,
        wind_tier: windTier,
        export_price_per_kwh: exportPricePerKwh,
        optimize_over_years: optimizeOverYears,
        prefer_green: preferGreen,
      })
      setResult(data)
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    } catch (err) {
      const msg = err.message || 'Request failed'
      if (msg.includes('No tariffs for this postcode') || msg.includes('run the tariff scraper first')) {
        setScrapeLoaded(false)
        setError('No tariff data for this postcode yet. Click “Load usage & tariffs from scrape” above and wait for the loading bar to finish (about 1–2 minutes if the scraper runs), then try “Get recommendation” again.')
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="wrap">
      <h1>PowerPlan</h1>
      <p className="tagline">Recommend energy technologies and tariffs from your location and usage. Enter your postcode and use data from your saved tariff scrape.</p>

      {(loading || scraping) && (
        <div className="scrape-loading scrape-loading-global" role="status" aria-live="polite">
          <p className="scrape-loading-label">
            {scraping ? 'Fetching tariff data… This usually takes 1–2 minutes.' : 'Loading…'}
          </p>
          <div className="scrape-progress" aria-hidden="true">
            <div className="scrape-progress-bar" />
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="card">
        <h2>Location & usage</h2>
        <div className="form-row col2">
          <div>
            <label htmlFor="postcode">UK postcode</label>
            <input
              type="text"
              id="postcode"
              value={postcode}
              onChange={(e) => {
                setPostcode(e.target.value)
                setScrapeLoaded(false)
                setScrapeTariffCount(null)
                setScraping(false)
              }}
              onBlur={() => lookupPostcode(postcode)}
              placeholder="e.g. BS1 1AA"
              autoComplete="off"
            />
            {postcodeStatus.message && (
              <div className={`postcode-status ${postcodeStatus.ok === true ? 'ok' : postcodeStatus.ok === false ? 'err' : ''}`}>
                {postcodeStatus.message}
              </div>
            )}
            <div className="hint">Location and weather are derived from this via the API.</div>
          </div>
          <div>
            <label htmlFor="annual_consumption_kwh">Annual electricity use (kWh)</label>
            <input
              type="number"
              id="annual_consumption_kwh"
              value={annualConsumptionKwh}
              onChange={(e) => setAnnualConsumptionKwh(e.target.value === '' ? '' : Number(e.target.value))}
              min={500}
              step={100}
              placeholder="Optional – from scrape if left blank"
            />
            <div className="hint">Optional. Leave blank to use usage from your saved scrape.</div>
          </div>
        </div>
        {postcode.trim().length >= 5 && (
          <div className="form-row">
            <button type="button" className="btn" onClick={loadFromScrape} disabled={loading}>
              {scraping ? 'Scraping… (1–2 min)' : loading ? 'Loading…' : 'Load usage & tariffs from scrape'}
            </button>
            {scrapeLoaded && (
              <span className="hint" style={{ marginLeft: '0.5rem', color: 'var(--accent)' }}>
                Using {scrapeTariffCount} tariffs from your saved scrape
              </span>
            )}
          </div>
        )}
        {!scrapeLoaded && postcode.trim().length >= 5 && (
          <p className="hint" style={{ marginTop: '1rem' }}>
            Click &quot;Load usage & tariffs from scrape&quot; above. Tariffs will load from saved data or the scraper will run for this postcode. Demand and system options will appear next.
          </p>
        )}
        {scrapeLoaded && (
          <>
            <div id="demand-and-system">
            <h2 style={{ marginTop: '1.25rem' }}>Demand adjustment</h2>
            <div className="form-row col3">
          <div>
            <label htmlFor="heating_fraction">Heating fraction (0–1)</label>
            <input
              type="number"
              id="heating_fraction"
              value={heatingFraction}
              onChange={(e) => setHeatingFraction(Number(e.target.value))}
              min={0}
              max={1}
              step={0.1}
            />
            <div className="hint">Share of demand that is space heating</div>
          </div>
          <div>
            <label htmlFor="insulation_r_value">Insulation R-value</label>
            <input
              type="number"
              id="insulation_r_value"
              value={insulationRValue}
              onChange={(e) => setInsulationRValue(Number(e.target.value))}
              min={0}
              step={0.5}
            />
            <div className="hint">0 = none; e.g. 5 for well insulated</div>
          </div>
          <div>
            <label htmlFor="heat_pump_cop">Heat pump COP</label>
            <select
              id="heat_pump_cop"
              value={heatPumpCop}
              onChange={(e) => setHeatPumpCop(Number(e.target.value))}
            >
              <option value={1}>1 (electric heating)</option>
              <option value={2.5}>2.5 (standard ASHP)</option>
              <option value={3.5}>3.5 (efficient ASHP)</option>
            </select>
          </div>
        </div>

        <h2 style={{ marginTop: '1.25rem' }}>System</h2>
        <div className="form-row col2">
          <div>
            <label htmlFor="solar_tier">Solar tier</label>
            <select id="solar_tier" value={solarTier} onChange={(e) => setSolarTier(e.target.value)}>
              <option value="budget">Budget</option>
              <option value="mid">Mid</option>
              <option value="premium">Premium</option>
            </select>
          </div>
          <div>
            <label htmlFor="wind_tier">Wind tier</label>
            <select id="wind_tier" value={windTier} onChange={(e) => setWindTier(e.target.value)}>
              <option value="budget">Budget</option>
              <option value="mid">Mid</option>
              <option value="premium">Premium</option>
            </select>
          </div>
        </div>
        <div className="form-row col3" style={{ marginTop: '1rem' }}>
          <div>
            <label htmlFor="export_price_per_kwh">Export price (£/kWh)</label>
            <input
              type="number"
              id="export_price_per_kwh"
              value={exportPricePerKwh}
              onChange={(e) => setExportPricePerKwh(Number(e.target.value))}
              step={0.01}
              min={0}
            />
          </div>
          <div>
            <label htmlFor="optimize_over_years">Optimise over (years)</label>
            <input
              type="number"
              id="optimize_over_years"
              value={optimizeOverYears}
              onChange={(e) => setOptimizeOverYears(Number(e.target.value))}
              min={1}
              max={20}
              step={1}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={preferGreen}
                onChange={(e) => setPreferGreen(e.target.checked)}
              />
              Prefer green tariffs
            </label>
          </div>
        </div>
        <div style={{ marginTop: '1.25rem' }}>
          <button type="submit" className="btn btn-block" disabled={loading}>
            {loading ? 'Calculating…' : 'Get recommendation'}
          </button>
        </div>
            </div>
          </>
        )}
      </form>

      {error && (
        <div className="error-msg" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div id="results">
          <ResultView result={result} />
        </div>
      )}
    </div>
  )
}

export default App
