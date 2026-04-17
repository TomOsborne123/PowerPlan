import { useState, useEffect, useRef } from 'react'
import {
  usePostcodeLookup,
  fetchRecommend,
  fetchScrapeResults,
  fetchRunScrape,
  fetchScrapeStatus,
  fetchExportPriceReference,
  fetchCostProjection,
} from './api'
import {
  HEATING_SHARE_OPTIONS,
  HEAT_PUMP_OPTIONS,
  INSULATION_OPTIONS,
  PROJECTION_SCENARIO_SOLAR_KW,
  PROJECTION_SCENARIO_WIND_KW,
  SOLAR_TIER_INFO,
  WIND_TIER_INFO,
  copForHeatPumpTier,
} from './optimiserConstants'
import { ResultView } from './ResultView'
import { CostProjectionView } from './CostProjectionView'
import { ScrapeGlobe } from './ScrapeGlobe'
import { CesiumFlyTo } from './CesiumFlyTo'
import { InfoIcon } from './InfoIcon'
import { FAVICON_PATH } from './branding'
import { normalizePostcode, isOutwardOnlyPostcode, isFullPostcode } from './postcodeUtils'

export function App() {
  const [postcode, setPostcode] = useState('')
  const [latitude, setLatitude] = useState(null)
  const [longitude, setLongitude] = useState(null)
  const [postcodeDistrict, setPostcodeDistrict] = useState('')
  const [addressName, setAddressName] = useState('')
  // Controls the single-screen "step" experience:
  // 1) Postcode input, 2) Scraping globe, 3) Optimiser inputs, 4) Graph + tariffs
  const [uiStep, setUiStep] = useState(1)
  const [annualConsumptionKwh, setAnnualConsumptionKwh] = useState('')
  const [scrapeLoaded, setScrapeLoaded] = useState(false)
  const [scrapeTariffCount, setScrapeTariffCount] = useState(null)
  const [scrapeTariffs, setScrapeTariffs] = useState([])
  const [scraping, setScraping] = useState(false)
  /** True during the post-fly delay before `scraping` — keeps the AmCharts globe rotating. */
  const [tariffScrapePending, setTariffScrapePending] = useState(false)
  /** Approximate 0–100% while waiting for tariff scrape (time-based, not exact). */
  const [scrapeProgressPct, setScrapeProgressPct] = useState(0)
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
  /** Scrapes tariffs with the right EV tariff filter: yes | interested | no */
  const [evInterest, setEvInterest] = useState('interested')
  // Direct kW caps for solar and wind. Defaults match the previous baseline limits (20 / 10 kW).
  const [solarMaxKwInput, setSolarMaxKwInput] = useState(20)
  const [windMaxKwInput, setWindMaxKwInput] = useState(10)
  const [demandPct, setDemandPct] = useState(0)
  const [exportPricePct, setExportPricePct] = useState(0)
  const [globeSpinning, setGlobeSpinning] = useState(false)
  const [globeLanded, setGlobeLanded] = useState(false)
  const [globeVisualReady, setGlobeVisualReady] = useState(false)
  const [globeFlyTrigger, setGlobeFlyTrigger] = useState(0)

  const [postcodeStatus, lookupPostcode] = usePostcodeLookup(setLatitude, setLongitude)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [projection, setProjection] = useState(null)
  const [projectionYears, setProjectionYears] = useState(20)
  const [projectionLoading, setProjectionLoading] = useState(false)
  const [projectionScenarios, setProjectionScenarios] = useState([
    'combo_baseline',
    'combo_solar',
    'combo_wind',
    'combo_insulation',
    'combo_solar_wind_insulation',
  ])
  const [optimiserQuestionIdx, setOptimiserQuestionIdx] = useState(0)
  const [projectionSolarTier, setProjectionSolarTier] = useState('mid')
  const [projectionWindTier, setProjectionWindTier] = useState('mid')
  const debounceRef = useRef(null)
  const requestSeqRef = useRef(0)
  const stepAdvanceTimerRef = useRef(null)
  const didFetchExportRef = useRef(false)
  const didHydrateRef = useRef(false)

  const PERSIST_KEY = 'powerplan:v1'

  useEffect(() => {
    if (didHydrateRef.current) return
    didHydrateRef.current = true
    try {
      const raw = typeof window !== 'undefined' ? window.localStorage.getItem(PERSIST_KEY) : null
      if (!raw) return
      const saved = JSON.parse(raw) || {}
      if (typeof saved.postcode === 'string') setPostcode(saved.postcode)
      if (typeof saved.addressName === 'string') setAddressName(saved.addressName)
      if (typeof saved.annualConsumptionKwh === 'string') setAnnualConsumptionKwh(saved.annualConsumptionKwh)
      if (typeof saved.homeOrBusiness === 'string') setHomeOrBusiness(saved.homeOrBusiness)
      if (typeof saved.evInterest === 'string') setEvInterest(saved.evInterest)
      if (typeof saved.heatingFraction === 'number') setHeatingFraction(saved.heatingFraction)
      if (typeof saved.insulationRValue === 'number') setInsulationRValue(saved.insulationRValue)
      if (typeof saved.heatPumpTier === 'string') setHeatPumpTier(saved.heatPumpTier)
      if (typeof saved.solarTier === 'string') setSolarTier(saved.solarTier)
      if (typeof saved.windTier === 'string') setWindTier(saved.windTier)
      if (typeof saved.preferGreen === 'boolean') setPreferGreen(saved.preferGreen)
      if (typeof saved.optimizeOverYears === 'number') setOptimizeOverYears(saved.optimizeOverYears)
      if (typeof saved.projectionYears === 'number') setProjectionYears(saved.projectionYears)
      if (typeof saved.projectionSolarTier === 'string') setProjectionSolarTier(saved.projectionSolarTier)
      if (typeof saved.projectionWindTier === 'string') setProjectionWindTier(saved.projectionWindTier)
    } catch {
      // Ignore malformed localStorage.
    }
  }, [])

  useEffect(() => {
    if (!didHydrateRef.current) return
    try {
      const payload = {
        postcode,
        addressName,
        annualConsumptionKwh,
        homeOrBusiness,
        evInterest,
        heatingFraction,
        insulationRValue,
        heatPumpTier,
        solarTier,
        windTier,
        preferGreen,
        optimizeOverYears,
        projectionYears,
        projectionSolarTier,
        projectionWindTier,
      }
      window.localStorage.setItem(PERSIST_KEY, JSON.stringify(payload))
    } catch {
      // Storage may be unavailable (e.g. private mode); ignore.
    }
  }, [
    postcode,
    addressName,
    annualConsumptionKwh,
    homeOrBusiness,
    evInterest,
    heatingFraction,
    insulationRValue,
    heatPumpTier,
    solarTier,
    windTier,
    preferGreen,
    optimizeOverYears,
    projectionYears,
    projectionSolarTier,
    projectionWindTier,
  ])

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

  useEffect(() => {
    const base = 'PowerPlan'
    const byStep = {
      1: {
        title: 'PowerPlan - Home Energy Planning in the UK',
        description: 'Enter your UK postcode and usage to start comparing energy tariffs and optimisation options.',
      },
      2: {
        title: `${base} — Loading local tariffs`,
        description: 'PowerPlan is locating your area and preparing tariff data for your postcode.',
      },
      3: {
        title: `${base} — Optimiser setup`,
        description: 'Answer setup questions for heating, insulation, technology cost bands, and comparison horizon.',
      },
      4: {
        title: `${base} — Recommendation results`,
        description: 'View recommended tariff ranking, annual bill estimates, and generation versus demand results.',
      },
      5: {
        title: `${base} — Cost projection`,
        description: 'Explore cumulative long-run costs by scenario with solar, wind, and insulation upgrades.',
      },
    }
    const meta = byStep[uiStep] || byStep[1]
    document.title = meta.title
    let desc = document.querySelector('meta[name="description"]')
    if (!desc) {
      desc = document.createElement('meta')
      desc.setAttribute('name', 'description')
      document.head.appendChild(desc)
    }
    desc.setAttribute('content', meta.description)
  }, [uiStep])

  useEffect(() => {
    if (!scraping && !tariffScrapePending) {
      // Snap to 100% briefly when a scrape finishes so the bar reads as done on any visible step.
      if (scrapeLoaded) setScrapeProgressPct(100)
      else setScrapeProgressPct(0)
      return
    }
    if (tariffScrapePending) {
      const t0 = Date.now()
      const id = window.setInterval(() => {
        setScrapeProgressPct(Math.min(12, ((Date.now() - t0) / 9000) * 12))
      }, 200)
      return () => window.clearInterval(id)
    }
    if (scraping) {
      const started = Date.now()
      const id = window.setInterval(() => {
        const elapsed = Date.now() - started
        setScrapeProgressPct(Math.min(92, 12 + (elapsed / 130000) * 80))
      }, 400)
      return () => window.clearInterval(id)
    }
    setScrapeProgressPct(0)
  }, [tariffScrapePending, scraping, scrapeLoaded])

  // No scrolling: keep the UI within a single view.

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
          setGlobeFlyTrigger((v) => v + 1)
          // Let the globe "land/zoom" animation play before advancing.
          stepAdvanceTimerRef.current = window.setTimeout(() => {
            setUiStep(3)
            stepAdvanceTimerRef.current = null
          }, 650)
        }
        return true
      }
      // No saved scrape or data older than 1 week: run scrape from the app, then load.
      // First run the globe landing animation before starting the scrape.
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
        // Ensure zoom animation plays before the scrape begins.
        setGlobeSpinning(false)
        setGlobeLanded(true)
        setGlobeFlyTrigger((v) => v + 1)
        setTariffScrapePending(true)
        try {
          await new Promise((r) => setTimeout(r, 1600))
        } finally {
          setTariffScrapePending(false)
        }
      }
      setScraping(true)
      try {
        await fetchRunScrape(norm, homeOrBusiness, evInterest, addressName, 0)
      } catch (err) {
        setError(err.message || 'Could not start scrape')
        setScraping(false)
        setLoading(false)
        return false
      }
      // Let the user answer optimiser questions while the scrape continues in the background.
      if (triggeredByEnter) {
        if (stepAdvanceTimerRef.current) {
          window.clearTimeout(stepAdvanceTimerRef.current)
        }
        stepAdvanceTimerRef.current = window.setTimeout(() => {
          setUiStep((prev) => (prev <= 2 ? 3 : prev))
          stepAdvanceTimerRef.current = null
        }, 400)
      }
      // Poll until completed/failed. Treat long-lived "idle" as lost in-memory job (e.g. Gunicorn worker restart).
      // How often we ask the server for scrape status (job runtime is unchanged; lower = snappier UI).
      const pollIntervalMs = 3500
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
              // Only bounce the user back to step 1 if they're still on the loading screen.
              setUiStep((prev) => (prev > 2 ? prev : 1))
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
              // Only bounce the user back to step 1 if they're still on the loading screen.
              setUiStep((prev) => (prev > 2 ? prev : 1))
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
              setGlobeFlyTrigger((v) => v + 1)
              // Only advance if the user is still on the loading step —
              // otherwise they've already moved on to the optimiser questions.
              stepAdvanceTimerRef.current = window.setTimeout(() => {
                setUiStep((prev) => (prev <= 2 ? 3 : prev))
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
              // Only bounce the user back to step 1 if they're still on the loading screen.
              setUiStep((prev) => (prev > 2 ? prev : 1))
            }
          }
          break
        }
        if (status.status === 'failed') {
          setError(status.error || 'Scrape failed')
          if (triggeredByEnter) {
            setGlobeSpinning(false)
            setGlobeLanded(false)
            setUiStep((prev) => (prev > 2 ? prev : 1))
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
        setUiStep((prev) => (prev > 2 ? prev : 1))
      }
      return false
    } finally {
      setLoading(false)
      setScraping(false)
      setTariffScrapePending(false)
    }
  }

  const canNavigate = !(loading || scraping || refreshing)

  const stepAvailable = (step) => {
    if (step === 1) return true
    if (step === 2) return scraping || tariffScrapePending || uiStep === 2
    if (step === 3) return scrapeLoaded || scraping || tariffScrapePending
    if (step === 4) return Boolean(result)
    if (step === 5) return Boolean(result)
    return false
  }

  const goToStep = (step) => {
    if (!canNavigate) return
    if (!stepAvailable(step)) return

    if (step === 1) {
      setGlobeSpinning(false)
      setGlobeLanded(false)
      setTariffScrapePending(false)
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
    if (step === 5) {
      setUiStep(5)
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
      const solarOff = solarTier === 'none'
      const windOff = windTier === 'none'
      const solarMaxKwTyped = Number(solarMaxKwInput)
      const windMaxKwTyped = Number(windMaxKwInput)
      const solarMaxKw = solarOff ? 0 : Math.max(0, Number.isFinite(solarMaxKwTyped) ? solarMaxKwTyped : 0)
      const windMaxKw = windOff ? 0 : Math.max(0, Number.isFinite(windMaxKwTyped) ? windMaxKwTyped : 0)
      // Scale the minimum capacities proportionally to the user's chosen max so the optimiser
      // is nudged into a range near the typed value (otherwise it often sticks at the default).
      const solarMinKwBase = 1.5 * (solarMaxKw / 20)
      const windMinKwBase = 0.5 * (windMaxKw / 10)
      const solarMinKw = solarOff ? 0 : Math.max(0, Math.min(solarMaxKw, solarMinKwBase))
      const windMinKw = windOff ? 0 : Math.max(0, Math.min(windMaxKw, windMinKwBase))
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
      setProjection(null)
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

  const runCostProjection = async ({ showErrors = true, background = false } = {}) => {
    const norm = normalizePostcode(postcode)
    const bestTariff = result?.ranking?.[0]?.tariff || result?.recommended_tariff
    const usageRaw = (annualConsumptionKwh ?? '').toString().trim()
    const usageBase = usageRaw === '' ? undefined : Number(usageRaw.replace(',', '.'))
    const usage = usageBase == null ? undefined : Math.max(0, usageBase * (1 + demandPct / 100))
    const heatPumpCop = copForHeatPumpTier(heatPumpTier)
    const solarScenarioKw = Math.max(0, PROJECTION_SCENARIO_SOLAR_KW[projectionSolarTier] ?? PROJECTION_SCENARIO_SOLAR_KW.mid)
    const windScenarioKw = Math.max(0, PROJECTION_SCENARIO_WIND_KW[projectionWindTier] ?? PROJECTION_SCENARIO_WIND_KW.mid)
    if (!bestTariff) return false
    if (background) setProjectionLoading(true)
    else setLoading(true)
    try {
      const out = await fetchCostProjection({
        postcode: norm,
        latitude: latitude ?? undefined,
        longitude: longitude ?? undefined,
        annual_consumption_kwh: usage,
        heating_fraction: heatingFraction,
        heat_pump_cop: heatPumpCop,
        export_price_per_kwh: Math.max(0, exportPricePerKwh * (1 + exportPricePct / 100)),
        unit_rate_p_per_kwh: Number(bestTariff.unit_rate_p_per_kwh ?? bestTariff.unit_rate),
        standing_charge_p_per_day: Number(bestTariff.standing_charge_p_per_day ?? bestTariff.standing_charge_day),
        max_years: projectionYears,
        baseline_insulation_r_value: 2.5,
        upgraded_insulation_r_value: Math.max(4.0, insulationRValue),
        scenario_solar_kw: solarScenarioKw,
        scenario_wind_kw: windScenarioKw,
        solar_tier: projectionSolarTier,
        wind_tier: projectionWindTier,
        tariff_label: `${bestTariff.supplier_name || 'Tariff'} — ${bestTariff.tariff_name || ''}`.trim(),
      })
      setProjection(out)
      return true
    } catch (err) {
      if (showErrors) setError(err.message || 'Could not build cost projection')
      return false
    } finally {
      if (background) setProjectionLoading(false)
      else setLoading(false)
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
    solarMaxKwInput,
    windMaxKwInput,
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

  useEffect(() => {
    if (uiStep !== 5) return
    if (!result || loading || scraping || refreshing) return
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      runCostProjection({ showErrors: true, background: true })
    }, 350)
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [
    uiStep,
    result,
    annualConsumptionKwh,
    demandPct,
    heatingFraction,
    insulationRValue,
    heatPumpTier,
    projectionSolarTier,
    projectionWindTier,
    exportPricePerKwh,
    exportPricePct,
    projectionYears,
  ])

  const appOverviewText =
    'PowerPlan helps you compare UK electricity tariffs, estimate annual running costs, and explore how upgrades like solar, wind, insulation, and heat pumps could change your bills over time.'
  const pageFunctionText = (
    {
      1: 'This page gathers the key starting details for your plan. Enter your postcode, add an optional address hint to help match the property, and include your annual electricity use so PowerPlan can build a comparison around your home.',
      2: 'This page is the data-loading stage. PowerPlan is locating your area, checking for saved results, and gathering tariff information so the rest of the journey is based on real options for your postcode.',
      3: 'This page personalises your recommendation. You can tell PowerPlan how your home uses electricity and which upgrades you are open to, so the model can balance comfort, technology choices, and likely long-term value.',
      4: 'This page shows your recommendation results. You can review the strongest tariff matches, expected yearly costs, and how generation and demand compare under the selected home energy setup.',
      5: 'This page helps you think ahead. It compares long-term cumulative costs across different upgrade paths, making it easier to see where bigger upfront investment could lead to lower lifetime energy spend.',
    }[uiStep] || 'PowerPlan compares tariffs and home energy upgrade choices to help you make a more confident decision.'
  )

  return (
    <div className="wrap">
      <div className="top-row">
        <h1>
          <img src={FAVICON_PATH} alt="" className="title-logo" />
          PowerPlan
        </h1>
        <div className="top-row-right">
          <button
            type="button"
            className="btn btn-sm"
            disabled={!result || loading || scraping || refreshing}
            onClick={() => {
              setUiStep(5)
              runCostProjection({ showErrors: true, background: false })
            }}
          >
            Cost projection
          </button>
          <nav className="step-pills" aria-label="Page navigation (steps)">
            {[
              { s: 1, label: 'Postcode' },
              { s: 2, label: 'Loading' },
              { s: 3, label: 'Preferences' },
              { s: 4, label: 'Results' },
              { s: 5, label: 'Projection' },
            ].map(({ s, label }) => {
              const enabled = stepAvailable(s)
              const active = uiStep === s
              return (
                <button
                  key={s}
                  type="button"
                  className={`step-pill ${active ? 'active' : ''} ${enabled ? '' : 'disabled'}`}
                  onClick={() => goToStep(s)}
                  disabled={!canNavigate || !enabled}
                  aria-current={active ? 'page' : undefined}
                  title={`${s}. ${label}`}
                >
                  <span className="step-pill-num">{s}</span>
                  <span className="step-pill-label">{label}</span>
                </button>
              )
            })}
          </nav>
        </div>
      </div>
      <p className="app-overview-text">{appOverviewText}</p>
      <p className="page-function-text">{pageFunctionText}</p>

      {error && (
        <div className="error-msg" role="alert">
          {error}
        </div>
      )}

      {uiStep === 2 && (
        <div className="scrape-loading scrape-loading-global" role="status" aria-live="polite">
          <p className="scrape-loading-label">
            {scraping ? 'Fetching tariff data…' : tariffScrapePending ? 'Preparing tariff search…' : 'Loading…'}
          </p>
          <div className="scrape-globe-wrap">
            <div className="scrape-globe">
              <ScrapeGlobe
                latitude={latitude}
                longitude={longitude}
                spinning={(globeSpinning && !globeLanded) || scraping || tariffScrapePending}
              />
            </div>
            <div className={`scrape-globe scrape-globe-cesium-wrap ${globeVisualReady ? 'ready' : 'loading'}`}>
              <CesiumFlyTo
                latitude={latitude}
                longitude={longitude}
                active={globeLanded}
                flyTrigger={globeFlyTrigger}
                onReady={() => setGlobeVisualReady(true)}
              />
            </div>
          </div>
          <div className="hint">{postcodeDistrict ? `District: ${postcodeDistrict}` : 'District: locating…'}</div>
          {(scraping || tariffScrapePending) && (
            <div
              className="scrape-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(scrapeProgressPct)}
              aria-label="Approximate tariff scrape progress"
            >
              <div className="scrape-progress-bar" style={{ width: `${scrapeProgressPct}%` }} />
            </div>
          )}
          <p className="scrape-progress-hint">
            {(scraping || tariffScrapePending) && 'Typical run is a few minutes; progress is approximate.'}
          </p>
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
                  setAddressName('')
                  // Each postcode has its own saved usage; prevent carry-over from the previous postcode.
                  setAnnualConsumptionKwh('')
                  setUiStep(1)
                  setResult(null)
                  setScrapeLoaded(false)
                  setScrapeTariffCount(null)
                  setScrapeTariffs([])
                  setScraping(false)
                  setTariffScrapePending(false)
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
              <label htmlFor="address_name">
                Address name (optional)
                <InfoIcon text="Enter part of your address (house name/number/street). We allow fuzzy matching to tolerate minor spelling and formatting differences." />
              </label>
              <input
                type="text"
                id="address_name"
                value={addressName}
                onChange={(e) => setAddressName(e.target.value)}
                placeholder="e.g. Chalfont Lodge or 14 High Street"
                autoComplete="off"
              />
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
                      <span>Home</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="home_or_business"
                        value="business"
                        checked={homeOrBusiness === 'business'}
                        onChange={() => setHomeOrBusiness('business')}
                      />
                      <span>Business</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="form-row">
                <div>
                  <label className="block-label">
                    Electric vehicles
                    <InfoIcon text="Comparison sites often ask whether you have an EV or are interested in one; this can change which electricity tariffs they show." />
                  </label>
                  <div className="radio-group" role="group" aria-label="Electric vehicle interest">
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="ev_interest"
                        value="yes"
                        checked={evInterest === 'yes'}
                        onChange={() => setEvInterest('yes')}
                      />
                      <span>Yes, I have an EV</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="ev_interest"
                        value="interested"
                        checked={evInterest === 'interested'}
                        onChange={() => setEvInterest('interested')}
                      />
                      <span>No EV yet, but interested</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="ev_interest"
                        value="no"
                        checked={evInterest === 'no'}
                        onChange={() => setEvInterest('no')}
                      />
                      <span>No / not interested</span>
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

      {uiStep === 3 && (scrapeLoaded || scraping || tariffScrapePending) && (
        <form onSubmit={handleSubmit} className="card">
          <h2>Optimiser questions</h2>
          <p className="field-hint">Question {optimiserQuestionIdx + 1} of 7</p>

          {(scraping || tariffScrapePending) && (
            <div className="scrape-inline-status" role="status" aria-live="polite">
              <div className="scrape-inline-status-row">
                <span className="scrape-inline-spinner" aria-hidden="true" />
                <span className="scrape-inline-text">
                  Searching local tariffs in the background — keep answering and we&apos;ll be ready when you are.
                </span>
              </div>
              <div
                className="scrape-progress"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(scrapeProgressPct)}
                aria-label="Approximate tariff scrape progress"
              >
                <div className="scrape-progress-bar" style={{ width: `${scrapeProgressPct}%` }} />
              </div>
            </div>
          )}
          {!scraping && !tariffScrapePending && scrapeLoaded && (
            <div className="scrape-inline-ready" role="status" aria-live="polite">
              Tariff search complete — {scrapeTariffCount ?? 0} tariffs ready.
            </div>
          )}

          {optimiserQuestionIdx === 0 && (
            <div>
              <label htmlFor="heating_fraction">
                How much of your electricity is heating?
                <InfoIcon text="Rough share of your yearly electricity use used for space heating (not hot water)." />
              </label>
              <select id="heating_fraction" value={heatingFraction} onChange={(e) => setHeatingFraction(Number(e.target.value))}>
                {HEATING_SHARE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          )}

          {optimiserQuestionIdx === 1 && (
            <div>
              <label htmlFor="insulation_r_value">
                Home insulation (fabric)
                <InfoIcon text="Higher insulation means less heating demand." />
              </label>
              <select id="insulation_r_value" value={insulationRValue} onChange={(e) => setInsulationRValue(Number(e.target.value))}>
                {INSULATION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          )}

          {optimiserQuestionIdx === 2 && (
            <div>
              <label htmlFor="heat_pump_tier">
                Heat pump type
                <InfoIcon text="Choose the heat-pump efficiency assumption (or No heat pump)." />
              </label>
              <select id="heat_pump_tier" value={heatPumpTier} onChange={(e) => setHeatPumpTier(e.target.value)}>
                {HEAT_PUMP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <p className="field-hint">Model COP ≈ {copForHeatPumpTier(heatPumpTier)}</p>
            </div>
          )}

          {optimiserQuestionIdx === 3 && (
            <div>
              <label htmlFor="solar_tier">
                Solar cost band
                <InfoIcon text="Indicative installed cost/performance band for solar." />
              </label>
              <select id="solar_tier" value={solarTier} onChange={(e) => setSolarTier(e.target.value)}>
                {Object.entries(SOLAR_TIER_INFO).map(([k, v]) => (
                  <option key={k} value={k}>{v.label} — ~£{v.capexPerKw.toLocaleString('en-GB')}/kWp · {v.blurb}</option>
                ))}
              </select>
            </div>
          )}

          {optimiserQuestionIdx === 4 && (
            <div>
              <label htmlFor="wind_tier">
                Wind cost band
                <InfoIcon text="Indicative installed cost/performance band for wind." />
              </label>
              <select id="wind_tier" value={windTier} onChange={(e) => setWindTier(e.target.value)}>
                {Object.entries(WIND_TIER_INFO).map(([k, v]) => (
                  <option key={k} value={k}>{v.label} — ~£{v.capexPerKw.toLocaleString('en-GB')}/kW · {v.blurb}</option>
                ))}
              </select>
            </div>
          )}

          {optimiserQuestionIdx === 5 && (
            <div>
              <label className="block-label">
                Prefer green tariffs?
                <InfoIcon text="If costs are very close, prefer green options." />
              </label>
              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input type="checkbox" checked={preferGreen === true} onChange={() => setPreferGreen(true)} />
                  <span>Yes</span>
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={preferGreen === false} onChange={() => setPreferGreen(false)} />
                  <span>No</span>
                </label>
              </div>
            </div>
          )}

          {optimiserQuestionIdx === 6 && (
            <div>
              <label htmlFor="optimize_over_years">
                Compare costs over how many years?
                <InfoIcon text="Longer periods include more future running cost." />
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
            </div>
          )}

          <div className="form-row col2" style={{ marginTop: '0.8rem' }}>
            <button
              type="button"
              className="btn"
              disabled={optimiserQuestionIdx === 0}
              onClick={() => setOptimiserQuestionIdx((q) => Math.max(0, q - 1))}
            >
              Back
            </button>
            {optimiserQuestionIdx < 6 ? (
              <button
                type="button"
                className="btn"
                onClick={() => setOptimiserQuestionIdx((q) => Math.min(6, q + 1))}
              >
                Next
              </button>
            ) : (
              <button
                type="submit"
                className="btn"
                disabled={loading || scraping || tariffScrapePending || !scrapeLoaded}
                title={!scrapeLoaded && (scraping || tariffScrapePending) ? 'Waiting for tariff search to finish' : undefined}
              >
                {loading
                  ? 'Calculating…'
                  : scraping || tariffScrapePending || !scrapeLoaded
                  ? 'Waiting for tariffs…'
                  : 'Get recommendation'}
              </button>
            )}
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
                <div className="form-row col2" style={{ marginTop: '0.35rem' }}>
                  <div>
                    <label htmlFor="export_price_per_kwh_results">
                      Export price (£/kWh)
                      <InfoIcon text="Value for exported electricity in the optimisation." />
                    </label>
                    <input
                      type="number"
                      id="export_price_per_kwh_results"
                      value={exportPricePerKwh}
                      onChange={(e) => setExportPricePerKwh(Number(e.target.value))}
                      step={0.01}
                      min={0}
                    />
                    {exportPriceHint ? <p className="field-hint">{exportPriceHint}</p> : null}
                  </div>
                  <div>
                    <label htmlFor="export_price_pct">
                      Export price adjustment ({exportPricePct}%)
                      <InfoIcon text="Adjusts the export price assumption up or down to test sensitivity." />
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

                <div className="form-row col2" style={{ marginTop: '0.35rem' }}>
                  <div>
                    <label htmlFor="demand_pct">
                      Home electricity usage adjustment ({demandPct}%)
                      <InfoIcon text="Scales your baseline annual electricity use up or down." />
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
                  <div />
                </div>

                <div className="form-row col2" style={{ marginTop: '0.35rem' }}>
                  <div>
                    <label htmlFor="solar_max_kw_results">
                      Solar maximum capacity (kW)
                      <InfoIcon text="Upper bound on installed solar kWp the optimiser may choose. Default is 20 kW." />
                    </label>
                    <input
                      type="number"
                      id="solar_max_kw_results"
                      min={0}
                      step={0.5}
                      value={solarMaxKwInput}
                      disabled={solarTier === 'none'}
                      onChange={(e) => setSolarMaxKwInput(e.target.value === '' ? '' : Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <label htmlFor="wind_max_kw_results">
                      Wind maximum capacity (kW)
                      <InfoIcon text="Upper bound on installed wind kW the optimiser may choose. Default is 10 kW." />
                    </label>
                    <input
                      type="number"
                      id="wind_max_kw_results"
                      min={0}
                      step={0.5}
                      value={windMaxKwInput}
                      disabled={windTier === 'none'}
                      onChange={(e) => setWindMaxKwInput(e.target.value === '' ? '' : Number(e.target.value))}
                    />
                  </div>
                </div>
              </>
            }
          />
        </div>
      )}

      {uiStep === 5 && result && (
        <CostProjectionView
          projection={projection}
          maxYears={projectionYears}
          loading={projectionLoading || loading}
          selectedScenarioIds={projectionScenarios}
          projectionSolarTier={projectionSolarTier}
          projectionWindTier={projectionWindTier}
          onProjectionSolarTier={setProjectionSolarTier}
          onProjectionWindTier={setProjectionWindTier}
          onYearsChange={(v) => setProjectionYears(v)}
          onToggleScenario={(id) => {
            setProjectionScenarios((prev) => (
              prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
            ))
          }}
        />
      )}
    </div>
  )
}

export default App
