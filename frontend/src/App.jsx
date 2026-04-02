import { useState, useEffect, useRef } from 'react'
import { usePostcodeLookup, fetchRecommend, fetchScrapeResults, fetchRunScrape, fetchScrapeStatus, fetchExportPriceReference } from './api'
import {
  HEATING_SHARE_OPTIONS,
  HEAT_PUMP_OPTIONS,
  INSULATION_OPTIONS,
  SOLAR_TIER_INFO,
  WIND_TIER_INFO,
  copForHeatPumpTier,
} from './optimiserConstants'
import { ResultView } from './ResultView'
import { ScrapeGlobe } from './ScrapeGlobe'
import { CesiumFlyTo } from './CesiumFlyTo'
import { InfoIcon } from './InfoIcon'

export function App() {
  const [postcode, setPostcode] = useState('')
  const [latitude, setLatitude] = useState(null)
  const [longitude, setLongitude] = useState(null)
  const [postcodeDistrict, setPostcodeDistrict] = useState('')
  // Controls the single-screen "step" experience:
  // 1) Postcode input, 2) Scraping globe, 3) Optimiser inputs, 4) Graph + tariffs
  const [uiStep, setUiStep] = useState(1)
  const [annualConsumptionKwh, setAnnualConsumptionKwh] = useState('')
  const [scrapeLoaded, setScrapeLoaded] = useState(false)
  const [scrapeTariffCount, setScrapeTariffCount] = useState(null)
  const [scrapeTariffs, setScrapeTariffs] = useState([])
  const [scraping, setScraping] = useState(false)
  const [heatingFraction, setHeatingFraction] = useState(0.6)
  const [insulationRValue, setInsulationRValue] = useState(2.5)
  const [heatPumpTier, setHeatPumpTier] = useState('mid')
  const [exportPriceHint, setExportPriceHint] = useState('')
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
  const [globeVisualReady, setGlobeVisualReady] = useState(false)

  const [postcodeStatus, lookupPostcode] = usePostcodeLookup(setLatitude, setLongitude)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const debounceRef = useRef(null)
  const requestSeqRef = useRef(0)
  const stepAdvanceTimerRef = useRef(null)
  const didFetchExportRef = useRef(false)

  useEffect(() => {
    if (uiStep !== 3 || didFetchExportRef.current) return
    didFetchExportRef.current = true
    let cancelled = false
    ;(async () => {
      try {
        const ref = await fetchExportPriceReference()
        if (cancelled) return
        if (ref.export_price_per_kwh != null) {
          setExportPricePerKwh(ref.export_price_per_kwh)
          setExportPriceHint(
            `Live estimate: Octopus “${ref.tariff_name || 'Outgoing'}” flat export (${ref.export_price_per_kwh} £/kWh). ${ref.disclaimer || ''}`
          )
        } else {
          setExportPriceHint(ref.disclaimer || ref.error || 'Could not load live export rate; using the value in the box.')
        }
      } catch {
        if (!cancelled) setExportPriceHint('Could not load live export rate; enter £/kWh manually.')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [uiStep])

  // No scrolling: keep the UI within a single view.

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
      if (stepAdvanceTimerRef.current) {
        window.clearTimeout(stepAdvanceTimerRef.current)
        stepAdvanceTimerRef.current = null
      }
      setGlobeLanded(false)
      setGlobeSpinning(true)
      setGlobeVisualReady(false)
      setUiStep(2)
    }
    setError(null)
    setLoading(true)
    try {
      let data = await fetchScrapeResults(norm)
      const ONE_MONTH_MS = 30 * 24 * 60 * 60 * 1000
      const searchDate = data?.search_date ? new Date(data.search_date) : null
      const isStale = !searchDate || (Date.now() - searchDate.getTime() > ONE_MONTH_MS)
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
          // Let the globe "land/zoom" animation play before advancing.
          stepAdvanceTimerRef.current = window.setTimeout(() => {
            setUiStep(3)
            stepAdvanceTimerRef.current = null
          }, 650)
        }
        return true
      }
      // No saved scrape or data older than 1 week: run scrape from the app, then load
      if (geocodable) {
        const geo = await lookupPostcode(norm)
        const ok = geo && Number.isFinite(geo.latitude) && Number.isFinite(geo.longitude)
        if (!ok) {
          setError('invalid postcode, try again')
          if (triggeredByEnter) {
            setGlobeSpinning(false)
            setGlobeLanded(false)
            setUiStep(1)
          }
          return false
        }
        setPostcodeDistrict(geo?.district || geo?.region || '')
      }
      setScraping(true)
      try {
        await fetchRunScrape(norm, homeOrBusiness)
      } catch (err) {
        setError(err.message || 'Could not start scrape')
        setScraping(false)
        setLoading(false)
        return false
      }
      // Poll until completed/failed. Treat long-lived "idle" as lost in-memory job (e.g. Gunicorn worker restart).
      const pollIntervalMs = 5000
      let success = false
      let sawRunning = false
      let polls = 0
      const maxIdlePollsBeforeGiveUp = 72 // ~6 min: never saw running/failed (start not registered or routing issue)
      // eslint-disable-next-line no-constant-condition -- poll until scrape ends or we give up on stuck idle
      while (true) {
        const status = await fetchScrapeStatus(norm)
        polls += 1
        if (status.status === 'running') sawRunning = true
        if (status.status === 'idle') {
          if (sawRunning) {
            setError(
              'Scrape progress was lost (server may have restarted). Try loading again — if it keeps happening, check Render logs and that only one Gunicorn worker is running.'
            )
            if (triggeredByEnter) {
              setGlobeSpinning(false)
              setGlobeLanded(false)
              setUiStep(1)
            }
            break
          }
          if (polls >= maxIdlePollsBeforeGiveUp) {
            setError(
              'No scrape status from server after several minutes. The job may not have started: check API URL (VITE_API_BASE_URL), CORS, and database env vars on Render, then inspect logs.'
            )
            if (triggeredByEnter) {
              setGlobeSpinning(false)
              setGlobeLanded(false)
              setUiStep(1)
            }
            break
          }
        }
        if (status.status === 'completed') {
          data = await fetchScrapeResults(norm)
          const tariffsOk = data && !data.no_saved_scrape && Array.isArray(data.tariffs) && data.tariffs.length > 0
          if (tariffsOk) {
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
              // Let the globe "land/zoom" animation play before advancing.
              stepAdvanceTimerRef.current = window.setTimeout(() => {
                setUiStep(3)
                stepAdvanceTimerRef.current = null
              }, 650)
            }
          } else {
            setError(
              'Scrape reported done but no tariffs were found in the database. Check RDS credentials (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME), security group, and Render logs for MySQL errors.'
            )
            if (triggeredByEnter) {
              setGlobeSpinning(false)
              setGlobeLanded(false)
              setUiStep(1)
            }
          }
          break
        }
        if (status.status === 'failed') {
          setError(status.error || 'Scrape failed')
          if (triggeredByEnter) {
            setGlobeSpinning(false)
            setGlobeLanded(false)
            setUiStep(1)
          }
          break
        }
        await new Promise((r) => setTimeout(r, pollIntervalMs))
      }
      return success
    } catch {
      setError('Could not load scrape results')
      if (triggeredByEnter) {
        setGlobeSpinning(false)
        setGlobeLanded(false)
        setUiStep(1)
      }
      return false
    } finally {
      setLoading(false)
      setScraping(false)
    }
  }

  const canNavigate = !(loading || scraping || refreshing)

  const stepAvailable = (step) => {
    if (step === 1) return true
    if (step === 2) return scraping || uiStep === 2
    if (step === 3) return scrapeLoaded
    if (step === 4) return Boolean(result)
    return false
  }

  const goToStep = (step) => {
    if (!canNavigate) return
    if (!stepAvailable(step)) return

    if (step === 1) {
      setGlobeSpinning(false)
      setGlobeLanded(false)
      setUiStep(1)
      return
    }
    if (step === 3) {
      setUiStep(3)
      return
    }
    if (step === 4) {
      setUiStep(4)
      return
    }
    // step 2: only enable while scraping/loading is active
    setUiStep(2)
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
      // Also scale the *minimum* capacities so the sliders reliably affect the optimiser result.
      // Without this, changing only the max bounds often doesn't move the optimal solution.
      const solarMinKwBase = 1.5 * (1 + solarCapacityPct / 100)
      const windMinKwBase = 0.5 * (1 + windCapacityPct / 100)
      const solarMinKw = Math.max(0, Math.min(solarMaxKw, solarMinKwBase))
      const windMinKw = Math.max(0, Math.min(windMaxKw, windMinKwBase))
      const exportPrice = Math.max(0, exportPricePerKwh * (1 + exportPricePct / 100))
      const heatPumpCop = copForHeatPumpTier(heatPumpTier)
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
        min_solar_kw: solarMinKw,
        min_wind_kw: windMinKw,
        optimize_over_years: optimizeOverYears,
        prefer_green: preferGreen,
      })
      if (reqId !== requestSeqRef.current) return false
      setResult(data)
      setUiStep(4)
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
    await runRecommendation({ ensureScrape: true, clearPreviousResult: true, showErrors: true })
  }

  // Live-update optimisation output when sliders/inputs change after initial result is shown.
  useEffect(() => {
    if (uiStep !== 4) return
    if (!scrapeLoaded || !result || loading || scraping || refreshing) return
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      // Show errors for background updates so "nothing changes" doesn't fail silently.
      runRecommendation({ ensureScrape: false, clearPreviousResult: false, showErrors: true, background: true })
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
    heatPumpTier,
    solarTier,
    windTier,
    exportPricePerKwh,
    optimizeOverYears,
    preferGreen,
    annualConsumptionKwh,
    scrapeLoaded,
    uiStep,
  ])

  return (
    <div className="wrap">
      <div className="top-row">
        <h1>PowerPlan</h1>
        <div className="step-dots" aria-label="Page navigation (steps)">
          {[1, 2, 3, 4].map((s) => {
            const enabled = stepAvailable(s)
            const active = uiStep === s
            return (
              <button
                key={s}
                type="button"
                className={`step-dot ${active ? 'active' : ''} ${enabled ? '' : 'disabled'}`}
                onClick={() => goToStep(s)}
                disabled={!canNavigate || !enabled}
                aria-current={active ? 'page' : undefined}
                aria-label={`Go to step ${s}`}
                title={`Step ${s}`}
              />
            )
          })}
        </div>
      </div>

      {error && (
        <div className="error-msg" role="alert">
          {error}
        </div>
      )}

      {uiStep === 2 && (
        <div className="scrape-loading scrape-loading-global" role="status" aria-live="polite">
          <p className="scrape-loading-label">{scraping ? 'Fetching tariff data…' : 'Loading…'}</p>
          <div className="scrape-globe-wrap">
            <div className="scrape-globe">
              <ScrapeGlobe latitude={latitude} longitude={longitude} spinning={globeSpinning && !globeLanded} />
            </div>
            <div className={`scrape-globe scrape-globe-cesium-wrap ${globeVisualReady ? 'ready' : 'loading'}`}>
              <CesiumFlyTo
                latitude={latitude}
                longitude={longitude}
                active={globeLanded || globeSpinning}
                onReady={() => setGlobeVisualReady(true)}
              />
            </div>
          </div>
          <div className="hint">{postcodeDistrict ? `District: ${postcodeDistrict}` : 'District: locating…'}</div>
          <div className="scrape-progress" aria-hidden="true">
            <div className="scrape-progress-bar" />
          </div>
        </div>
      )}

      {uiStep === 1 && (
        <form onSubmit={(e) => { e.preventDefault(); loadFromScrape(true) }} className="card">
          <h2>Postcode</h2>
          <div className="form-row col2">
            <div>
              <label htmlFor="postcode">
                UK postcode
                <InfoIcon text="Used to fetch saved tariffs and weather/flux data for your location." />
              </label>
              <input
                type="text"
                id="postcode"
                value={postcode}
                onChange={(e) => {
                  setPostcode(e.target.value)
                  setPostcodeDistrict('')
                  // Each postcode has its own saved usage; prevent carry-over from the previous postcode.
                  setAnnualConsumptionKwh('')
                  setUiStep(1)
                  setResult(null)
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
            </div>
            <div>
              <label htmlFor="annual_consumption_kwh">
                Annual electricity use (kWh)
                <InfoIcon text="Your baseline annual electricity demand (before insulation/heat pump adjustments)." />
              </label>
              <input
                type="text"
                id="annual_consumption_kwh"
                value={annualConsumptionKwh}
                onChange={(e) => setAnnualConsumptionKwh(e.target.value)}
                inputMode="decimal"
                spellCheck={false}
                placeholder="Optional"
              />
            </div>
          </div>

          {postcodeInputValid && (
            <>
              <div className="form-row">
                <div>
                  <label className="block-label">
                    Home or business
                    <InfoIcon text="Choose which fuel/account type to compare when scraping tariffs." />
                  </label>
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
                </div>
              </div>

              <div className="form-row">
                <button type="button" className="btn" onClick={() => loadFromScrape(true)} disabled={loading || scraping}>
                  {scraping || loading ? 'Loading…' : 'Load usage & tariffs'}
                </button>
              </div>
            </>
          )}
        </form>
      )}

      {uiStep === 3 && scrapeLoaded && (
        <form onSubmit={handleSubmit} className="card">
          <h2>Optimiser</h2>

          <div className="form-row col3">
            <div>
              <label htmlFor="heating_fraction">
                How much of your electricity is heating?
                <InfoIcon text="Rough share of your yearly electricity use used for space heating (not hot water). Pick the sentence that fits; we convert it into a number for the model." />
              </label>
              <select
                id="heating_fraction"
                value={heatingFraction}
                onChange={(e) => setHeatingFraction(Number(e.target.value))}
              >
                {HEATING_SHARE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <p className="field-hint">You don’t need an exact meter split — a ballpark is fine.</p>
            </div>
            <div>
              <label htmlFor="insulation_r_value">
                Home insulation (fabric)
                <InfoIcon text="Roughly how good your walls, loft and draught-proofing are. Higher = less heat loss, so less demand to cover with solar/wind. Values are a model input (similar to thermal resistance), not a survey." />
              </label>
              <select
                id="insulation_r_value"
                value={insulationRValue}
                onChange={(e) => setInsulationRValue(Number(e.target.value))}
              >
                {INSULATION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="heat_pump_tier">
                Heat pump type
                <InfoIcon text="Air-source heat pumps turn electricity into heat more efficiently than old electric heaters. We use simple “budget / mid / premium” performance bands (COP). Follow the links for independent background — not a product recommendation." />
              </label>
              <select
                id="heat_pump_tier"
                value={heatPumpTier}
                onChange={(e) => setHeatPumpTier(e.target.value)}
              >
                {HEAT_PUMP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <p className="field-hint">
                Model uses COP ≈ {copForHeatPumpTier(heatPumpTier)}.{' '}
                <a href={HEAT_PUMP_OPTIONS.find((x) => x.value === heatPumpTier)?.specUrl} target="_blank" rel="noopener noreferrer">
                  Read typical specs / guidance
                </a>
              </p>
            </div>
          </div>

          <div className="form-row col2">
            <div>
              <label htmlFor="solar_tier">
                Solar cost band (~£/kWp installed, indicative)
                <InfoIcon text="Higher bands assume pricier kit and slightly better modelled output. Figures are for comparison only — get quotes for real projects." />
              </label>
              <select id="solar_tier" value={solarTier} onChange={(e) => setSolarTier(e.target.value)}>
                {Object.entries(SOLAR_TIER_INFO).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label} — ~£{v.capexPerKw.toLocaleString('en-GB')}/kWp · {v.blurb}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="wind_tier">
                Wind cost band (~£/kW installed, indicative)
                <InfoIcon text="Small wind costs vary hugely by site and planning; these are illustrative bands for the optimiser only." />
              </label>
              <select id="wind_tier" value={windTier} onChange={(e) => setWindTier(e.target.value)}>
                {Object.entries(WIND_TIER_INFO).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label} — ~£{v.capexPerKw.toLocaleString('en-GB')}/kW · {v.blurb}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row col3" style={{ marginTop: '0.4rem' }}>
            <div>
              <label htmlFor="export_price_per_kwh">
                Export price (£/kWh)
                <InfoIcon text="Money you get per unit of electricity you export. We try to preload a public reference rate; override to match your tariff." />
              </label>
              <input
                type="number"
                id="export_price_per_kwh"
                value={exportPricePerKwh}
                onChange={(e) => setExportPricePerKwh(Number(e.target.value))}
                step={0.01}
                min={0}
              />
              {exportPriceHint ? <p className="field-hint">{exportPriceHint}</p> : null}
            </div>
            <div>
              <label htmlFor="optimize_over_years">
                Compare costs over how many years?
                <InfoIcon text="We add up roughly: equipment cost today + importing power minus export earnings, over the years you choose. Longer horizon = more years of bills in the comparison." />
              </label>
              <input
                type="number"
                id="optimize_over_years"
                value={optimizeOverYears}
                onChange={(e) => setOptimizeOverYears(Number(e.target.value))}
                min={1}
                max={20}
                step={1}
              />
              <p className="field-hint">Layman terms: “If I committed for N years, what’s the total picture?”</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={preferGreen}
                  onChange={(e) => setPreferGreen(e.target.checked)}
                />
                Prefer green
                <InfoIcon text="If your cheapest tariffs are within ~2%, prefer options marked as green." />
              </label>
            </div>
          </div>

          <div className="form-row col2" style={{ marginTop: '0.4rem' }}>
            <div>
              <label htmlFor="solar_capacity_pct">
                Solar search slider: {solarCapacityPct}%
                <InfoIcon text="Another name for this control is a range slider: it widens or narrows how much solar capacity the tool is allowed to consider around a 20 kW reference." />
              </label>
              <input
                type="range"
                id="solar_capacity_pct"
                min={-300}
                max={300}
                step={50}
                value={solarCapacityPct}
                onChange={(e) => setSolarCapacityPct(Number(e.target.value))}
              />
            </div>
            <div>
              <label htmlFor="wind_capacity_pct">
                Wind search slider: {windCapacityPct}%
                <InfoIcon text="Range slider for wind: search bounds around a 10 kW reference." />
              </label>
              <input
                type="range"
                id="wind_capacity_pct"
                min={-300}
                max={300}
                step={50}
                value={windCapacityPct}
                onChange={(e) => setWindCapacityPct(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="form-row col2" style={{ marginTop: '0.2rem' }}>
            <div>
              <label htmlFor="demand_pct">
                Demand slider: {demandPct}%
                <InfoIcon text="Range slider: nudges your annual usage up or down before running the optimiser (e.g. if your bill is a bit higher or lower than the scrape)." />
              </label>
              <input
                type="range"
                id="demand_pct"
                min={-300}
                max={300}
                step={50}
                value={demandPct}
                onChange={(e) => setDemandPct(Number(e.target.value))}
              />
            </div>
            <div>
              <label htmlFor="export_price_pct">
                Export pay sensitivity: {exportPricePct}%
                <InfoIcon text="Range slider: stress-test how sensitive results are to your export £/kWh (±%)." />
              </label>
              <input
                type="range"
                id="export_price_pct"
                min={-300}
                max={300}
                step={50}
                value={exportPricePct}
                onChange={(e) => setExportPricePct(Number(e.target.value))}
              />
            </div>
          </div>

          <div style={{ marginTop: '0.7rem' }}>
            <button type="submit" className="btn btn-block" disabled={loading}>
              {loading ? 'Calculating…' : 'Get recommendation'}
            </button>
          </div>
        </form>
      )}

      {uiStep === 4 && result && (
        <div id="results">
          <div
            className="updating-graph-indicator"
            aria-live="polite"
            style={{ visibility: refreshing ? 'visible' : 'hidden' }}
          >
            Updating graph…
          </div>
          <ResultView
            result={result}
            optimiserControls={
              <>
                <div className="form-row col3">
                  <div>
                    <label htmlFor="heating_fraction_results">
                      Heating share
                      <InfoIcon text="Rough share of yearly electricity used for space heating." />
                    </label>
                    <select
                      id="heating_fraction_results"
                      value={heatingFraction}
                      onChange={(e) => setHeatingFraction(Number(e.target.value))}
                    >
                      {HEATING_SHARE_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="insulation_r_value_results">
                      Insulation
                      <InfoIcon text="Fabric / insulation level for the model." />
                    </label>
                    <select
                      id="insulation_r_value_results"
                      value={insulationRValue}
                      onChange={(e) => setInsulationRValue(Number(e.target.value))}
                    >
                      {INSULATION_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="heat_pump_tier_results">
                      Heat pump (COP ≈ {copForHeatPumpTier(heatPumpTier)})
                      <InfoIcon text="Heat pump performance band." />
                    </label>
                    <select
                      id="heat_pump_tier_results"
                      value={heatPumpTier}
                      onChange={(e) => setHeatPumpTier(e.target.value)}
                    >
                      {HEAT_PUMP_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-row col2" style={{ marginTop: '0.35rem' }}>
                  <div>
                    <label htmlFor="solar_capacity_pct">
                      Solar slider {solarCapacityPct}%
                      <InfoIcon text="Range slider: solar search bounds around 20 kW." />
                    </label>
                    <input
                      type="range"
                      id="solar_capacity_pct"
                      min={-300}
                      max={300}
                      step={50}
                      value={solarCapacityPct}
                      onChange={(e) => setSolarCapacityPct(Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <label htmlFor="wind_capacity_pct">
                      Wind slider {windCapacityPct}%
                      <InfoIcon text="Range slider: wind search bounds around 10 kW." />
                    </label>
                    <input
                      type="range"
                      id="wind_capacity_pct"
                      min={-300}
                      max={300}
                      step={50}
                      value={windCapacityPct}
                      onChange={(e) => setWindCapacityPct(Number(e.target.value))}
                    />
                  </div>
                </div>

                <div className="form-row col2" style={{ marginTop: '0.35rem' }}>
                  <div>
                    <label htmlFor="demand_pct">
                      Demand slider {demandPct}%
                      <InfoIcon text="Range slider: scales baseline annual electricity use." />
                    </label>
                    <input
                      type="range"
                      id="demand_pct"
                      min={-300}
                      max={300}
                      step={50}
                      value={demandPct}
                      onChange={(e) => setDemandPct(Number(e.target.value))}
                    />
                  </div>
                  <div>
              <label htmlFor="export_price_pct">
                Export sensitivity {exportPricePct}%
                <InfoIcon text="Range slider: stress-test export £/kWh." />
              </label>
                    <input
                      type="range"
                      id="export_price_pct"
                      min={-300}
                      max={300}
                      step={50}
                      value={exportPricePct}
                      onChange={(e) => setExportPricePct(Number(e.target.value))}
                    />
                  </div>
                </div>
              </>
            }
          />
        </div>
      )}
    </div>
  )
}

export default App
