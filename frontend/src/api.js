import { useState, useCallback } from 'react'

const DEFAULT_TARIFFS = [
  { supplier_name: 'Octopus', tariff_name: 'Flexible', unit_rate: 24.5, standing_charge_day: 55, is_green: true },
  { supplier_name: 'British Gas', tariff_name: 'Standard', unit_rate: 28.2, standing_charge_day: 60, is_green: false },
  { supplier_name: 'EDF', tariff_name: 'Standard', unit_rate: 26.8, standing_charge_day: 52, is_green: true },
]

export function usePostcodeLookup(setLatitude, setLongitude) {
  const [status, setStatus] = useState({ message: '', ok: null })

  const lookup = useCallback(async (postcode) => {
    const trimmed = (postcode || '').trim()
    if (!trimmed || trimmed.length < 5) {
      setStatus({ message: '', ok: null })
      return
    }
    setStatus({ message: 'Looking up…', ok: null })
    try {
      const r = await fetch('/api/postcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postcode: trimmed }),
      })
      const data = await r.json()
      if (r.ok && data.latitude != null) {
        setLatitude(data.latitude)
        setLongitude(data.longitude)
        const loc = [data.admin_district, data.region].filter(Boolean).join(' ') || 'Resolved'
        setStatus({ message: loc, ok: true })
      } else {
        setStatus({ message: data.error || 'Could not resolve', ok: false })
      }
    } catch {
      setStatus({ message: 'Lookup failed', ok: false })
    }
  }, [setLatitude, setLongitude])

  return [status, lookup]
}

export async function fetchScrapeResults(postcode) {
  const trimmed = (postcode || '').trim()
  if (!trimmed) return null
  const r = await fetch(`/api/scrape-results?postcode=${encodeURIComponent(trimmed)}`)
  const data = await r.json()
  if (!r.ok) return null
  return data
}

/** Start a background scrape for postcode. Returns { status: 'started', postcode } or throws. */
export async function fetchRunScrape(postcode) {
  const trimmed = (postcode || '').trim()
  if (!trimmed) throw new Error('Postcode required')
  const r = await fetch('/api/run-scrape', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ postcode: trimmed }),
  })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Failed to start scrape')
  return data
}

/** Get scrape job status: { status: 'idle'|'running'|'completed'|'failed', error? } */
export async function fetchScrapeStatus(postcode) {
  const trimmed = (postcode || '').trim()
  if (!trimmed) return { status: 'idle' }
  const r = await fetch(`/api/scrape-status?postcode=${encodeURIComponent(trimmed)}`)
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
