import { describe, expect, it } from 'vitest'
import {
  HEAT_PUMP_OPTIONS,
  PROJECTION_SCENARIO_SOLAR_KW,
  PROJECTION_SCENARIO_WIND_KW,
  SOLAR_TIER_INFO,
  WIND_TIER_INFO,
  copForHeatPumpTier,
} from './optimiserConstants'

describe('copForHeatPumpTier', () => {
  it('returns COP for known tiers', () => {
    expect(copForHeatPumpTier('none')).toBe(1.0)
    expect(copForHeatPumpTier('budget')).toBe(2.5)
    expect(copForHeatPumpTier('mid')).toBe(3.0)
    expect(copForHeatPumpTier('premium')).toBe(3.5)
  })

  it('defaults for unknown tier', () => {
    expect(copForHeatPumpTier('unknown-tier')).toBe(3.0)
  })
})

describe('tier metadata alignment', () => {
  it('solar tier keys match projection solar keys', () => {
    const keys = new Set(Object.keys(SOLAR_TIER_INFO))
    for (const k of Object.keys(PROJECTION_SCENARIO_SOLAR_KW)) {
      expect(keys.has(k), `SOLAR_TIER_INFO missing ${k}`).toBe(true)
    }
  })

  it('wind tier keys match projection wind keys', () => {
    const keys = new Set(Object.keys(WIND_TIER_INFO))
    for (const k of Object.keys(PROJECTION_SCENARIO_WIND_KW)) {
      expect(keys.has(k), `WIND_TIER_INFO missing ${k}`).toBe(true)
    }
  })

  it('every heat pump option has cop and value', () => {
    for (const row of HEAT_PUMP_OPTIONS) {
      expect(row.value).toBeTypeOf('string')
      expect(row.cop).toBeGreaterThan(0)
    }
  })
})
