import { breadcrumbItemsForSeo } from './seoRoutes'
import { SITE_ORIGIN } from './siteOrigin.js'

export { SITE_ORIGIN } from './siteOrigin.js'

function upsertMeta(attr, key, value) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', value)
}

function removeMeta(attr, key) {
  document.head.querySelector(`meta[${attr}="${key}"]`)?.remove()
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

function upsertJsonLd(graph) {
  if (typeof document === 'undefined') return
  const id = 'powerplan-ld-json'
  let el = document.getElementById(id)
  if (!el) {
    el = document.createElement('script')
    el.type = 'application/ld+json'
    el.id = id
    document.head.appendChild(el)
  }
  el.textContent = JSON.stringify(graph)
}

function buildStructuredGraph({ title, description, normalPath, pageUrl }) {
  const crumbs = breadcrumbItemsForSeo(SITE_ORIGIN, normalPath, pageUrl)
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${SITE_ORIGIN}/#website`,
        name: 'PowerPlan',
        url: `${SITE_ORIGIN}/`,
        description: 'UK home energy planning: tariff comparison and upgrade modelling.',
        inLanguage: 'en-GB',
        publisher: { '@id': `${SITE_ORIGIN}/#org` },
      },
      {
        '@type': 'Organization',
        '@id': `${SITE_ORIGIN}/#org`,
        name: 'PowerPlan',
        url: `${SITE_ORIGIN}/`,
        logo: { '@type': 'ImageObject', url: `${SITE_ORIGIN}/favicon.png?v=7` },
      },
      {
        '@type': 'WebPage',
        '@id': `${pageUrl}#webpage`,
        url: pageUrl,
        name: title,
        description,
        inLanguage: 'en-GB',
        isPartOf: { '@id': `${SITE_ORIGIN}/#website` },
      },
      {
        '@type': 'SoftwareApplication',
        name: 'PowerPlan',
        applicationCategory: 'UtilitiesApplication',
        operatingSystem: 'Web',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'GBP' },
        url: `${SITE_ORIGIN}/`,
      },
      {
        '@type': 'BreadcrumbList',
        '@id': `${pageUrl}#breadcrumb`,
        itemListElement: crumbs,
      },
    ],
  }
}

/**
 * Full page meta from `pageMeta.getPlannerPageMeta` (shape matches `PAGE_META_TEMPLATE` + resolved URLs).
 * @param {object} meta
 */
export function applySeoHead(meta) {
  if (typeof document === 'undefined') return
  const {
    title,
    description,
    path = '/',
    pageUrl: pageUrlOverride,
    robots = 'index, follow',
    keywords,
    themeColor = '#0a0e14',
    ogType = 'website',
    ogSiteName = 'PowerPlan',
    ogLocale = 'en-GB',
    ogTitle,
    ogDescription,
    ogUrl,
    ogImage,
    ogImageType = 'image/png',
    ogImageWidth = '512',
    ogImageHeight = '512',
    twitterCard = 'summary_large_image',
    twitterTitle,
    twitterDescription,
    twitterImage,
  } = meta

  const normalPath = path.startsWith('/') ? path : `/${path}`
  const pageUrl = pageUrlOverride ?? `${SITE_ORIGIN}${normalPath === '//' ? '/' : normalPath}`

  document.title = title

  upsertMeta('name', 'robots', robots)
  upsertMeta('name', 'theme-color', themeColor)
  if (keywords && String(keywords).trim()) {
    upsertMeta('name', 'keywords', String(keywords).trim())
  } else {
    removeMeta('name', 'keywords')
  }

  upsertMeta('name', 'description', description)
  upsertLink('canonical', pageUrl)

  upsertMeta('property', 'og:type', ogType)
  upsertMeta('property', 'og:site_name', ogSiteName)
  upsertMeta('property', 'og:locale', ogLocale)
  upsertMeta('property', 'og:title', ogTitle ?? title)
  upsertMeta('property', 'og:description', ogDescription ?? description)
  upsertMeta('property', 'og:url', ogUrl ?? pageUrl)
  upsertMeta('property', 'og:image', ogImage ?? `${SITE_ORIGIN}/favicon.png?v=7`)
  upsertMeta('property', 'og:image:type', ogImageType)
  upsertMeta('property', 'og:image:width', String(ogImageWidth))
  upsertMeta('property', 'og:image:height', String(ogImageHeight))

  upsertMeta('name', 'twitter:card', twitterCard)
  upsertMeta('name', 'twitter:title', twitterTitle ?? ogTitle ?? title)
  upsertMeta('name', 'twitter:description', twitterDescription ?? ogDescription ?? description)
  upsertMeta('name', 'twitter:image', twitterImage ?? ogImage ?? `${SITE_ORIGIN}/favicon.png?v=7`)

  upsertJsonLd(buildStructuredGraph({ title, description, normalPath, pageUrl }))
}
