/** UK postcode helpers shared by the app and API layer. */

export function normalizePostcode(p) {
  return (p || '').toUpperCase().replace(/\s+/g, '')
}

/** Outward code only, e.g. BS39, SW1A */
export function isOutwardOnlyPostcode(norm) {
  return /^[A-Z]{1,2}\d{1,2}[A-Z]?$/.test(norm)
}

/** Full UK postcode inward + outward, e.g. BS11AA */
export function isFullPostcode(norm) {
  return /^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$/.test(norm)
}
