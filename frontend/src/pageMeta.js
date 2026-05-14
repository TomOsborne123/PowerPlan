import { SITE_ORIGIN } from './siteOrigin.js'

/**
 * Canonical field set for every PowerPlan HTML surface (planner + static hub/blog).
 * Static `.html` files should mirror this block in order; SPA uses `applySeoHead`.
 */
export const PAGE_META_TEMPLATE = {
  charset: 'UTF-8',
  viewport: 'width=device-width, initial-scale=1.0',
  htmlLang: 'en-GB',
  robots: 'index, follow',
  themeColor: '#0a0e14',
  ogSiteName: 'PowerPlan',
  ogLocale: 'en-GB',
  ogImagePath: '/favicon.png?v=7',
  ogImageType: 'image/png',
  ogImageWidth: '512',
  ogImageHeight: '512',
  twitterCard: 'summary_large_image',
}

export const ogImageAbsoluteUrl = () => `${SITE_ORIGIN}${PAGE_META_TEMPLATE.ogImagePath}`

/**
 * Planner steps — paths must stay aligned with `seoRoutes.UI_STEP_PATHS`.
 * @type {Record<number, { path: string, title: string, description: string, keywords: string, ogType?: 'website' }>}
 */
export const PLANNER_STEP_META = {
  0: {
    path: '/',
    title: 'PowerPlan - UK Home Energy Planning',
    description:
      'Compare UK electricity tariffs and model solar, wind, insulation and heat-pump upgrades with PowerPlan.',
    keywords:
      'UK energy planner, compare electricity tariffs, home solar UK, heat pump costs, energy bill calculator',
    ogType: 'website',
  },
  1: {
    path: '/postcode',
    title: 'PowerPlan - Home Energy Planning in the UK',
    description:
      'Enter your UK postcode and usage to start comparing energy tariffs and optimisation options.',
    keywords:
      'UK postcode electricity, compare tariffs by postcode, annual kWh estimate, PowerPlan planner',
    ogType: 'website',
  },
  2: {
    path: '/tariffs',
    title: 'PowerPlan — Loading local tariffs',
    description: 'PowerPlan is locating your area and preparing tariff data for your postcode.',
    keywords: 'UK electricity tariffs, tariff scrape, postcode tariffs, PowerPlan',
    ogType: 'website',
  },
  3: {
    path: '/optimiser',
    title: 'PowerPlan — Optimiser setup',
    description:
      'Answer setup questions for heating, insulation, technology cost bands, and comparison horizon.',
    keywords:
      'home energy optimiser, solar wind battery UK, heating fraction, insulation R-value, export rate',
    ogType: 'website',
  },
  4: {
    path: '/results',
    title: 'PowerPlan — Recommendation results',
    description:
      'View recommended tariff ranking, annual bill estimates, and generation versus demand results.',
    keywords:
      'best electricity tariff UK, tariff ranking, annual bill estimate, solar export savings',
    ogType: 'website',
  },
  5: {
    path: '/projection',
    title: 'PowerPlan — Cost projection',
    description: 'Explore cumulative long-run costs by scenario with solar, wind, and insulation upgrades.',
    keywords:
      'energy cost projection UK, cumulative bill model, solar payback UK, retrofit lifetime cost',
    ogType: 'website',
  },
}

/** Keys for static HTML — mirror heads under `frontend/public/`. */
export const STATIC_PAGE_IDS = /** @type {const} */ ([
  'plannerShell',
  'blogIndex',
  'blogCompareTariffsPostcode',
  'blogHomeBatterySolarWind',
  'collectionUkHomeEnergy',
])

/**
 * @typedef {Object} StaticPageMetaRow
 * @property {string} path — pathname (with trailing slash for directory indexes)
 * @property {string} title
 * @property {string} description
 * @property {string} keywords
 * @property {'website'|'article'} ogType
 * @property {string} [ogTitle]
 * @property {string} [ogDescription]
 * @property {string} [twitterTitle]
 * @property {string} [twitterDescription]
 */

/** @type {Record<(typeof STATIC_PAGE_IDS)[number], StaticPageMetaRow & { robots?: string }>} */
export const STATIC_PAGE_META = {
  plannerShell: {
    path: '/',
    title: 'PowerPlan - Home Energy Planning in the UK',
    description:
      'PowerPlan compares UK energy tariffs and models long-term home energy costs with solar, wind, insulation, and heat pump scenarios.',
    keywords:
      'PowerPlan, UK home energy, electricity tariff comparison, solar battery UK, heat pump planner',
    ogType: 'website',
    ogTitle: 'PowerPlan - UK home energy planning',
    ogDescription:
      'Compare UK electricity tariffs by postcode and model solar, wind, batteries and heat pumps with free tools.',
    twitterTitle: 'PowerPlan - UK home energy planning',
    twitterDescription: 'Compare UK electricity tariffs and model home energy upgrades — free, no sign-up.',
  },
  blogIndex: {
    path: '/blog/',
    title: 'PowerPlan blog — UK home energy tariffs & upgrades',
    description:
      'Practical UK-focused articles on electricity tariffs, solar, wind, batteries and heat pumps. Each post links to our home energy hub and free planner.',
    keywords: 'UK energy blog, electricity tariffs guide, solar batteries UK, heat pump advice, PowerPlan',
    ogType: 'website',
    ogTitle: 'PowerPlan blog — UK home energy',
    ogDescription: 'Guides on tariffs and home energy upgrades, with links to our free planner.',
    twitterTitle: 'PowerPlan blog — UK home energy',
    twitterDescription: 'Guides on tariffs and home energy upgrades, with links to our free planner.',
  },
  blogCompareTariffsPostcode: {
    path: '/blog/compare-uk-electricity-tariffs-postcode.html',
    title: 'Compare UK electricity tariffs by postcode | PowerPlan',
    description:
      'How to compare UK electricity tariffs for your postcode, what to check beyond the unit rate, and how to use PowerPlan’s free planner for ranked results.',
    keywords:
      'compare electricity tariffs UK, postcode tariff comparison, standing charge, green tariff UK, PowerPlan',
    ogType: 'article',
    ogTitle: 'Compare UK electricity tariffs by postcode | PowerPlan',
    ogDescription:
      'Practical steps to compare tariffs using postcode-level data — plus links to our hub and free tool.',
    twitterTitle: 'Compare UK electricity tariffs by postcode | PowerPlan',
    twitterDescription:
      'Practical steps to compare tariffs using postcode-level data — plus links to our hub and free tool.',
  },
  blogHomeBatterySolarWind: {
    path: '/blog/home-battery-solar-wind-uk-guide.html',
    title: 'Home batteries with solar & wind in the UK | PowerPlan',
    description:
      'How home batteries interact with solar and small wind in the UK: self-consumption, export, and long-term cost modelling with PowerPlan.',
    keywords:
      'home battery UK, solar battery storage, domestic wind turbine UK, self consumption, PowerPlan',
    ogType: 'article',
    ogTitle: 'Home batteries with solar & wind in the UK | PowerPlan',
    ogDescription: 'Planning storage alongside renewables — with links to our hub and projection tools.',
    twitterTitle: 'Home batteries with solar & wind in the UK | PowerPlan',
    twitterDescription: 'Planning storage alongside renewables — with links to our hub and projection tools.',
  },
  collectionUkHomeEnergy: {
    path: '/collections/uk-home-energy/',
    title: 'UK home energy hub — tariffs, solar, heat pumps & bills | PowerPlan',
    description:
      'Plan UK home electricity: compare tariffs by postcode, model solar, wind, batteries and heat pumps, and read practical guides. Free tools from PowerPlan.',
    keywords:
      'UK home energy hub, electricity tariffs UK, solar panels cost, heat pump UK, energy bills help',
    ogType: 'website',
    ogTitle: 'UK home energy hub — tariffs, solar, heat pumps & bills | PowerPlan',
    ogDescription:
      'Compare UK electricity tariffs, explore retrofit upgrades, and use our free planner for postcode-level results.',
    twitterTitle: 'UK home energy hub | PowerPlan',
    twitterDescription: 'Tariffs, solar, heat pumps and long-term bill modelling for UK homes.',
  },
}

/**
 * Resolved planner meta for `applySeoHead` (absolute OG/Twitter image, OG URL, etc.).
 * @param {number} step
 */
export function getPlannerPageMeta(step) {
  const s = Number(step)
  const row = PLANNER_STEP_META[Number.isFinite(s) ? s : 0] ?? PLANNER_STEP_META[0]
  const ogImage = ogImageAbsoluteUrl()
  const path = row.path.startsWith('/') ? row.path : `/${row.path}`
  const pageUrl = `${SITE_ORIGIN}${path === '//' ? '/' : path}`
  return {
    path,
    pageUrl,
    title: row.title,
    description: row.description,
    keywords: row.keywords,
    robots: PAGE_META_TEMPLATE.robots,
    themeColor: PAGE_META_TEMPLATE.themeColor,
    ogType: row.ogType ?? 'website',
    ogSiteName: PAGE_META_TEMPLATE.ogSiteName,
    ogLocale: PAGE_META_TEMPLATE.ogLocale,
    ogTitle: row.title,
    ogDescription: row.description,
    ogUrl: pageUrl,
    ogImage,
    ogImageType: PAGE_META_TEMPLATE.ogImageType,
    ogImageWidth: PAGE_META_TEMPLATE.ogImageWidth,
    ogImageHeight: PAGE_META_TEMPLATE.ogImageHeight,
    twitterCard: PAGE_META_TEMPLATE.twitterCard,
    twitterTitle: row.title,
    twitterDescription: row.description,
    twitterImage: ogImage,
  }
}
