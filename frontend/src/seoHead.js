/** Production site origin — override in `.env` with `VITE_SITE_ORIGIN=https://staging.example` if needed. */
export const SITE_ORIGIN = (import.meta.env.VITE_SITE_ORIGIN || 'https://www.powerplan.site').replace(/\/$/, '')

function upsertMeta(attr, key, value) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', value)
}

function upsertLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

/**
 * Keeps title/description + canonical/Open Graph/Twitter tags aligned while users move through the SPA.
 * Crawlers that execute JS see updates; the static `index.html` still supplies a sensible first paint.
 */
export function applySeoHead({ title, description, path = '/' }) {
  if (typeof document === 'undefined') return
  const normalPath = path.startsWith('/') ? path : `/${path}`
  const pageUrl = `${SITE_ORIGIN}${normalPath === '//' ? '/' : normalPath}`

  document.title = title

  upsertMeta('name', 'description', description)
  upsertLink('canonical', pageUrl)

  upsertMeta('property', 'og:title', title)
  upsertMeta('property', 'og:description', description)
  upsertMeta('property', 'og:url', pageUrl)
  upsertMeta('property', 'og:type', 'website')
  upsertMeta('property', 'og:site_name', 'PowerPlan')
  upsertMeta('property', 'og:locale', 'en_GB')
  upsertMeta('property', 'og:image', `${SITE_ORIGIN}/favicon.png?v=7`)

  upsertMeta('name', 'twitter:card', 'summary_large_image')
  upsertMeta('name', 'twitter:title', title)
  upsertMeta('name', 'twitter:description', description)
  upsertMeta('name', 'twitter:image', `${SITE_ORIGIN}/favicon.png?v=7`)
}
