/** Single source for public site origin (matches `VITE_SITE_ORIGIN` in `.env` when set). */
export const SITE_ORIGIN = (import.meta.env.VITE_SITE_ORIGIN || 'https://www.powerplan.site').replace(/\/$/, '')
