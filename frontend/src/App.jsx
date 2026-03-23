import { useState, useEffect, useRef } from 'react'
import { usePostcodeLookup, fetchRecommend, fetchScrapeResults, fetchRunScrape, fetchScrapeStatus } from './api'
import { ResultView } from './ResultView'
import { ScrapeGlobe } from './ScrapeGlobe'

export function App() {
  const [postcode, setPostcode] = useState('')
  const [latitude, setLatitude] = useState(null)
  const [longitude, setLongitude] = useState(null)
  const [annualConsumptionKwh, setAnnualConsumptionKwh] = useState('')
  const [scrapeLoaded, setScrapeLoaded] = useState(false)
  const [scrapeTariffCount, setScrapeTariffCount] = useState(null)
  const [scrapeTariffs, setScrapeTariffs] = useState([])
  const [scraping, setScraping] = useState(false)
  const [heatingFraction, setHeatingFraction] = useState(0.6)
  const [insulationRValue, setInsulationRValue] = useState(0)
  const [heatPumpCop, setHeatPumpCop] = useState(2.5)
  const [solarTier, setSolarTier] = useState('budget')
  const [windTier, setWindTier] = useState('budget')
  const [exportPricePerKwh, setExportPricePerKwh] = useState(0.05)
  const [optimizeOverYears, setOptimizeOverYears] = useState(5)
  const [preferGreen, setPreferGreen] = useState(false)
  const [homeOrBusiness, setHomeOrBusiness] = useState('home')
  const [solarCapacityPct, setSolarCapacityPct] = useState(0)
  const [windCapacityPct, setWindCapacityPct] = useState(0)
  const [demandPct, setDemandPct] = useState(0)
  const [exportPricePct, setExportPricePct] = useState(0)
  const [globeSpinning, setGlobeSpinning] = useState(false)
  const [globeLanded, setGlobeLanded] = useState(false)

  const [postcodeStatus, lookupPostcode] = usePostcodeLookup(setLatitude, setLongitude)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const debounceRef = useRef(null)
  const requestSeqRef = useRef(0)

  useEffect(() => {
    if (scrapeLoaded) {
      document.getElementById('demand-and-system')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [scrapeLoaded])

  const normalizePostcode = (p) => (p || '').toUpperCase().replace(/\s+/g, '')
  const isOutwardOnlyPostcode = (norm) => /^[A-Z]{1,2}\d{1,2}[A-Z]?$/.test(norm)
  const isFullPostcode = (norm) => /^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$/.test(norm)
  const normalizedPostcode = normalizePostcode(postcode)
  const postcodeInputValid = normalizedPostcode && (isOutwardOnlyPostcode(normalizedPostcode) || isFullPostcode(normalizedPostcode))
  const postcodeGeocodable = normalizedPostcode && isFullPostcode(normalizedPostcode)
  const hasCoords = Number.isFinite(latitude) && Number.isFinite(longitude)

  const loadFromScrape = async (triggeredByEnter = false) => {
    const norm = normalizePostcode(postcode)
    if (!norm || !(isOutwardOnlyPostcode(norm) || isFullPostcode(norm))) {
      setError('Enter a postcode area (e.g. BS39) or full postcode (e.g. BS1 1AA).')
      return
    }
    const geocodable = isFullPostcode(norm)
    if (triggeredByEnter) {
      setGlobeLanded(false)
      setGlobeSpinning(true)
    }
    // Immediately resolve postcode coordinates (when available) so the globe can pin location right away.
    if (geocodable) {
      try {
        await lookupPostcode(norm)
      } catch {
        // Non-fatal: scrape flow can still continue and may provide coordinates later.
      }
    }
    setError(null)
    setLoading(true)
    try {
      let data = await fetchScrapeResults(norm)
      const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000
      const searchDate = data?.search_date ? new Date(data.search_date) : null
      const isStale = !searchDate || (Date.now() - searchDate.getTime() > ONE_WEEK_MS)
      const hasData = data && !data.no_saved_scrape && data.tariffs?.length > 0 && !isStale
      if (hasData) {
        // Preserve user-entered usage (including decimals). Only hydrate from scrape when empty.
        setAnnualConsumptionKwh((prev) => (prev === '' || prev == null ? (data.annual_electricity_kwh ?? '') : prev))
        setLatitude(data.latitude ?? null)
        setLongitude(data.longitude ?? null)
        setScrapeTariffCount((data.tariffs && data.tariffs.length) || 0)
        setScrapeTariffs(Array.isArray(data.tariffs) ? data.tariffs : [])
        setScrapeLoaded(true)
        if (triggeredByEnter) {
          setGlobeSpinning(false)
          setGlobeLanded(true)
        }
        return true
      }
      // No saved scrape or data older than 1 week: run scrape from the app, then load
      setScraping(true)
      try {
        await fetchRunScrape(norm, homeOrBusiness)
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
        const status = await fetchScrapeStatus(norm)
        if (status.status === 'completed') {
          data = await fetchScrapeResults(norm)
          if (data) {
            // Preserve user-entered usage (including decimals). Only hydrate from scrape when empty.
            setAnnualConsumptionKwh((prev) => (prev === '' || prev == null ? (data.annual_electricity_kwh ?? '') : prev))
            setLatitude(data.latitude ?? null)
            setLongitude(data.longitude ?? null)
            setScrapeTariffCount((data.tariffs && data.tariffs.length) || 0)
            setScrapeTariffs(Array.isArray(data.tariffs) ? data.tariffs : [])
            setScrapeLoaded(true)
            setError(null)
            success = true
            if (triggeredByEnter) {
              setGlobeSpinning(false)
              setGlobeLanded(true)
            }
          }
          break
        }
        if (status.status === 'failed') {
          setError(status.error || 'Scrape failed')
          if (triggeredByEnter) {
            setGlobeSpinning(false)
            setGlobeLanded(false)
          }
          break
        }
        await new Promise((r) => setTimeout(r, pollIntervalMs))
      }
      if (Date.now() - start >= maxWaitMs) {
        setError('Scrape is taking longer than expected. Try again in a few minutes.')
        if (triggeredByEnter) {
          setGlobeSpinning(false)
          setGlobeLanded(false)
        }
      }
      return success
    } catch {
      setError('Could not load scrape results')
      if (triggeredByEnter) {
        setGlobeSpinning(false)
        setGlobeLanded(false)
      }
      return false
    } finally {
      setLoading(false)
      setScraping(false)
    }
  }

  const runRecommendation = async ({ ensureScrape = false, clearPreviousResult = false, showErrors = true, background = false } = {}) => {
    const norm = normalizePostcode(postcode)
    if (!norm || !(isOutwardOnlyPostcode(norm) || isFullPostcode(norm))) {
      if (showErrors) setError('Please enter a postcode area (e.g. BS39) or a full postcode (e.g. BS1 1AA).')
      return false
    }
    if (clearPreviousResult) setResult(null)
    setError(null)
    if (background) setRefreshing(true)
    else setLoading(true)
    const reqId = ++requestSeqRef.current
    try {
      if (ensureScrape && !scrapeLoaded) {
        const loaded = await loadFromScrape(true)
        if (!loaded) return false
      }
      if (!scrapeLoaded) {
        if (showErrors) setError('Load scrape data first for this postcode.')
        return false
      }
      const usageRaw = (annualConsumptionKwh ?? '').toString().trim()
      const usageBase = usageRaw === '' ? undefined : Number(usageRaw.replace(',', '.'))
      const usage = usageBase == null ? undefined : Math.max(0, usageBase * (1 + demandPct / 100))
      if (usageRaw !== '' && (!Number.isFinite(usage) || usage < 0)) {
        if (showErrors) setError('Annual electricity use must be a valid non-negative number (floats allowed, e.g. 3527.5).')
        return false
      }
      const solarMaxKw = Math.max(0, 20 * (1 + solarCapacityPct / 100))
      const windMaxKw = Math.max(0, 10 * (1 + windCapacityPct / 100))
      const exportPrice = Math.max(0, exportPricePerKwh * (1 + exportPricePct / 100))
      const data = await fetchRecommend({
        postcode: norm,
        latitude: latitude ?? undefined,
        longitude: longitude ?? undefined,
        annual_consumption_kwh: usage,
        tariffs: scrapeTariffs?.length ? scrapeTariffs : undefined,
        heating_fraction: heatingFraction,
        insulation_r_value: insulationRValue,
        heat_pump_cop: heatPumpCop,
        solar_tier: solarTier,
        wind_tier: windTier,
        export_price_per_kwh: exportPrice,
        solar_max_kw: solarMaxKw,
        wind_max_kw: windMaxKw,
        optimize_over_years: optimizeOverYears,
        prefer_green: preferGreen,
      })
      if (reqId !== requestSeqRef.current) return false
      setResult(data)
      return true
    } catch (err) {
      if (reqId !== requestSeqRef.current) return false
      const msg = err.message || 'Request failed'
      if (showErrors) {
        if (msg.includes('No tariffs for this postcode') || msg.includes('run the tariff scraper first')) {
          setScrapeLoaded(false)
          setError('No tariff data for this postcode yet. Click “Load usage & tariffs from scrape” above and wait for the loading bar to finish (about 1–2 minutes if the scraper runs), then try “Get recommendation” again.')
        } else {
          setError(msg)
        }
      }
      return false
    } finally {
      if (reqId === requestSeqRef.current) {
        if (background) setRefreshing(false)
        else setLoading(false)
      }
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const ok = await runRecommendation({ ensureScrape: true, clearPreviousResult: true, showErrors: true })
    if (ok) {
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }

  // Live-update optimisation output when sliders/inputs change after initial result is shown.
  useEffect(() => {
    if (!scrapeLoaded || !result || loading || scraping || refreshing) return
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      runRecommendation({ ensureScrape: false, clearPreviousResult: false, showErrors: false, background: true })
    }, 350)
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [
    solarCapacityPct,
    windCapacityPct,
    demandPct,
    exportPricePct,
    heatingFraction,
    insulationRValue,
    heatPumpCop,
    solarTier,
    windTier,
    exportPricePerKwh,
    optimizeOverYears,
    preferGreen,
    annualConsumptionKwh,
    scrapeLoaded,
    loading,
    scraping,
    refreshing,
  ])

  return (
    <div className="wrap">
      <h1>PowerPlan</h1>
      <p className="tagline">Recommend energy technologies and tariffs from your location and usage. Enter your postcode and use data from your saved tariff scrape.</p>

      {(loading || scraping) && (
        <div className="scrape-loading scrape-loading-global" role="status" aria-live="polite">
          <p className="scrape-loading-label">
            {scraping ? 'Fetching tariff data… This usually takes 1–2 minutes.' : 'Loading…'}
          </p>
          {scraping && (
            <div className="scrape-globe-wrap">
              <div className="scrape-globe">
                <ScrapeGlobe latitude={latitude} longitude={longitude} spinning={globeSpinning && !globeLanded} />
              </div>
              <div className="hint">
                {hasCoords
                  ? `Pinpointing your location at ${Number(latitude).toFixed(3)}, ${Number(longitude).toFixed(3)} while scraping…`
                  : 'Pinpoint animation will appear once location coordinates are available…'}
              </div>
            </div>
          )}
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
                setScrapeTariffs([])
                setScraping(false)
                setGlobeSpinning(false)
                setGlobeLanded(false)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  loadFromScrape(true)
                }
              }}
              onBlur={() => {
                if (postcodeGeocodable) lookupPostcode(normalizedPostcode)
              }}
              placeholder="e.g. BS1 1AA"
              autoComplete="off"
            />
            {postcodeStatus.message && (
              <div className={`postcode-status ${postcodeStatus.ok === true ? 'ok' : postcodeStatus.ok === false ? 'err' : ''}`}>
                {postcodeStatus.message}
              </div>
            )}
            <div className="hint">Location and weather are derived from this via the API. Press Enter to load tariff data (from database or run a new scrape).</div>
          </div>
          <div>
            <label htmlFor="annual_consumption_kwh">Annual electricity use (kWh)</label>
            <input
              type="text"
              id="annual_consumption_kwh"
              value={annualConsumptionKwh}
              onChange={(e) => setAnnualConsumptionKwh(e.target.value)}
              inputMode="decimal"
              spellCheck={false}
              placeholder="Optional – any value, e.g. 3527.5"
            />
            <div className="hint">Optional. Leave blank to use usage from your saved scrape. Any decimal value is accepted.</div>
          </div>
        </div>
        {postcodeInputValid && (
          <>
          <div className="form-row">
            <div>
              <label className="block-label">Is this for a home or business?</label>
              <div className="radio-group" role="group" aria-label="Home or business">
                <label className="radio-label">
                  <input
                    type="radio"
                    name="home_or_business"
                    value="home"
                    checked={homeOrBusiness === 'home'}
                    onChange={() => setHomeOrBusiness('home')}
                  />
                  <span>No, it&apos;s a home</span>
                </label>
                <label className="radio-label">
                  <input
                    type="radio"
                    name="home_or_business"
                    value="business"
                    checked={homeOrBusiness === 'business'}
                    onChange={() => setHomeOrBusiness('business')}
                  />
                  <span>Yes, it&apos;s a business</span>
                </label>
              </div>
              <div className="hint">Used when fetching tariffs so we select the right option on the comparison site.</div>
            </div>
          </div>
          <div className="form-row">
            <button type="button" className="btn" onClick={() => loadFromScrape(true)} disabled={loading}>
              {scraping ? 'Scraping… (1–2 min)' : loading ? 'Loading…' : 'Load usage & tariffs from scrape'}
            </button>
            {scrapeLoaded && (
              <span className="hint" style={{ marginLeft: '0.5rem', color: 'var(--accent)' }}>
                Using {scrapeTariffCount} tariffs from your saved scrape
              </span>
            )}
          </div>
          </>
        )}
        {!scrapeLoaded && postcodeInputValid && (
          <p className="hint" style={{ marginTop: '0.5rem' }}>
            Click &quot;Load usage & tariffs from scrape&quot; above. Tariffs will load from saved data or the scraper will run for this postcode. Demand and system options will appear next.
          </p>
        )}
        {scrapeLoaded && (
          <>
            <div id="demand-and-system">
            <h2 style={{ marginTop: '0.65rem' }}>Demand adjustment</h2>
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

        <h2 style={{ marginTop: '0.65rem' }}>System</h2>
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
        <div className="form-row col3" style={{ marginTop: '0.5rem' }}>
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
        <h2 style={{ marginTop: '0.65rem' }}>Sensitivity sliders (±300%, step 50%)</h2>
        <div className="form-row col2">
          <div>
            <label htmlFor="solar_capacity_pct">Solar capacity range adjustment: {solarCapacityPct}%</label>
            <input
              type="range"
              id="solar_capacity_pct"
              min={-300}
              max={300}
              step={50}
              value={solarCapacityPct}
              onChange={(e) => setSolarCapacityPct(Number(e.target.value))}
            />
            <div className="hint">Applies to optimiser solar max kW (base 20 kW).</div>
          </div>
          <div>
            <label htmlFor="wind_capacity_pct">Wind capacity range adjustment: {windCapacityPct}%</label>
            <input
              type="range"
              id="wind_capacity_pct"
              min={-300}
              max={300}
              step={50}
              value={windCapacityPct}
              onChange={(e) => setWindCapacityPct(Number(e.target.value))}
            />
            <div className="hint">Applies to optimiser wind max kW (base 10 kW).</div>
          </div>
        </div>
        <div className="form-row col2">
          <div>
            <label htmlFor="demand_pct">Demand adjustment: {demandPct}%</label>
            <input
              type="range"
              id="demand_pct"
              min={-300}
              max={300}
              step={50}
              value={demandPct}
              onChange={(e) => setDemandPct(Number(e.target.value))}
            />
            <div className="hint">Scales annual electricity use before optimisation.</div>
          </div>
          <div>
            <label htmlFor="export_price_pct">Export price adjustment: {exportPricePct}%</label>
            <input
              type="range"
              id="export_price_pct"
              min={-300}
              max={300}
              step={50}
              value={exportPricePct}
              onChange={(e) => setExportPricePct(Number(e.target.value))}
            />
            <div className="hint">Scales export price before optimisation.</div>
          </div>
        </div>
        <p className="hint" style={{ marginTop: '0.25rem' }}>
          The optimiser evaluates combinations of solar and wind capacities within these adjusted ranges.
        </p>
        <div style={{ marginTop: '0.6rem' }}>
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
