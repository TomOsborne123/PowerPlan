import { describe, it, expect } from 'vitest'
import { SITE_ORIGIN } from './seoHead'

describe('seoHead', () => {
  it('SITE_ORIGIN has no trailing slash', () => {
    expect(SITE_ORIGIN.endsWith('/')).toBe(false)
    expect(SITE_ORIGIN).toMatch(/^https:\/\//)
  })
})
