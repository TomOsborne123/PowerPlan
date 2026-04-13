import { describe, expect, it } from 'vitest'
import { isFullPostcode, isOutwardOnlyPostcode, normalizePostcode } from './postcodeUtils'

describe('normalizePostcode', () => {
  it('uppercases and strips spaces', () => {
    expect(normalizePostcode('  bs1 1aa ')).toBe('BS11AA')
  })

  it('handles empty input', () => {
    expect(normalizePostcode('')).toBe('')
    expect(normalizePostcode(null)).toBe('')
  })
})

describe('isFullPostcode', () => {
  it('accepts valid full postcodes', () => {
    expect(isFullPostcode('BS11AA')).toBe(true)
    expect(isFullPostcode('SW1A1AA')).toBe(true)
    expect(isFullPostcode('M11AE')).toBe(true)
  })

  it('rejects outward-only codes', () => {
    expect(isFullPostcode('BS39')).toBe(false)
    expect(isFullPostcode('SW1A')).toBe(false)
  })
})

describe('isOutwardOnlyPostcode', () => {
  it('accepts outward codes', () => {
    expect(isOutwardOnlyPostcode('BS39')).toBe(true)
    expect(isOutwardOnlyPostcode('SW1A')).toBe(true)
    expect(isOutwardOnlyPostcode('M1')).toBe(true)
  })

  it('rejects full postcodes (inward part breaks pattern)', () => {
    expect(isOutwardOnlyPostcode('BS11AA')).toBe(false)
  })
})
