import { useState, useCallback } from 'react'

const DEFAULT_TARIFFS = [
  { supplier_name: 'Octopus', tariff_name: 'Flexible', unit_rate: 24.5, standing_charge_day: 55, is_green: true },
  { supplier_name: 'British Gas', tariff_name: 'Standard', unit_rate: 28.2, standing_charge_day: 60, is_green: false },
  { supplier_name: 'EDF', tariff_name: 'Standard', unit_rate: 26.8, standing_charge_day: 52, is_green: true },
]

const normalizePostcode = (p) => (p || '').toUpperCase().replace(/\s+/g, '')
const isFullPostcode = (norm) => /^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$/.test(norm)

export function usePostcodeLookup(setLatitude, setLongitude) {
  const [status, setStatus] = useState({ message: '', ok: null })

  const lookup = useCallback(async (postcode) => {
    const norm = normalizePostcode(postcode)
    if (!norm || !isFullPostcode(norm)) {
      setStatus({ message: '', ok: null })
      return null
    }
    setStatus({ message: 'Looking up…', ok: null })
    try {
      const r = await fetch('/api/postcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postcode: norm }),
      })
      const data = await r.json()
      if (r.ok && data.latitude != null && data.longitude != null) {
        setLatitude(data.latitude)
        setLongitude(data.longitude)
        const loc = [data.admin_district, data.region].filter(Boolean).join(' ') || 'Resolved'
        setStatus({ message: loc, ok: true })
        return {
          latitude: data.latitude,
          longitude: data.longitude,
          district: data.admin_district || '',
          region: data.region || '',
        }
      } else {
        setStatus({ message: data.error || 'Could not resolve', ok: false })
        return null
      }
    } catch {
      setStatus({ message: 'Lookup failed', ok: false })
      return null
    }
  }, [setLatitude, setLongitude])

  return [status, lookup]
}

export async function fetchScrapeResults(postcode) {
  const norm = normalizePostcode(postcode)
  if (!norm) return null
  const r = await fetch(`/api/scrape-results?postcode=${encodeURIComponent(norm)}`)
  const data = await r.json()
  if (!r.ok) return null
  return data
}

/** Start a background scrape for postcode. homeOrBusiness: 'home' | 'business'. Returns { status: 'started', postcode } or throws. */
export async function fetchRunScrape(postcode, homeOrBusiness = 'home') {
  const norm = normalizePostcode(postcode)
  if (!norm) throw new Error('Postcode required')
  const r = await fetch('/api/run-scrape', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ postcode: norm, home_or_business: homeOrBusiness === 'business' ? 'business' : 'home' }),
  })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Failed to start scrape')
  return data
}

/** Get scrape job status: { status: 'idle'|'running'|'completed'|'failed', error? } */
export async function fetchScrapeStatus(postcode) {
  const norm = normalizePostcode(postcode)
  if (!norm) return { status: 'idle' }
  const r = await fetch(`/api/scrape-status?postcode=${encodeURIComponent(norm)}`)
  const data = await r.json()
  return r.ok ? data : { status: 'idle' }
}

export async function fetchRecommend(payload) {
  const r = await fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Request failed')
  return data
}

export { DEFAULT_TARIFFS }
