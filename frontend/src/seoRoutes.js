/** Normalise browser pathname to match `UI_STEP_PATHS` keys (no trailing slash except `/`). */
export function normalizePublicPath(pathname) {
  if (typeof pathname !== 'string' || !pathname.trim()) return '/'
  let p = pathname.trim()
  if (p.length > 1 && p.endsWith('/')) p = p.slice(0, -1)
  return p || '/'
}

/** Public URL path for each planner UI step (0 = welcome … 5 = projection). */
export const UI_STEP_PATHS = ['/', '/postcode', '/tariffs', '/optimiser', '/results', '/projection']

const STEP_LABELS = {
  '/': 'PowerPlan',
  '/postcode': 'Postcode & usage',
  '/tariffs': 'Tariff data',
  '/optimiser': 'Optimiser setup',
  '/results': 'Recommendations',
  '/projection': 'Cost projection',
}

export function uiStepToPath(step) {
  const i = Number(step)
  if (!Number.isFinite(i) || i < 0 || i >= UI_STEP_PATHS.length) return '/'
  return UI_STEP_PATHS[i]
}

/** Normalise pathname and map to UI step (0 if unknown — static pages do not use this). */
export function pathToUiStep(pathname) {
  const p = normalizePublicPath(pathname)
  const idx = UI_STEP_PATHS.indexOf(p)
  return idx >= 0 ? idx : 0
}

export function stepLabelForPath(normalPath) {
  return STEP_LABELS[normalPath] || 'PowerPlan'
}

/**
 * BreadcrumbList itemListElement for schema.org (2 levels: home + current when not home).
 */
export function breadcrumbItemsForSeo(siteOrigin, normalPath, pageUrl) {
  const root = siteOrigin.replace(/\/$/, '')
  const homeUrl = `${root}/`
  if (normalPath === '/') {
    return [{ '@type': 'ListItem', position: 1, name: 'PowerPlan', item: homeUrl }]
  }
  const label = stepLabelForPath(normalPath)
  return [
    { '@type': 'ListItem', position: 1, name: 'PowerPlan', item: homeUrl },
    { '@type': 'ListItem', position: 2, name: label, item: pageUrl },
  ]
}
