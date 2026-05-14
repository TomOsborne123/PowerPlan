import { describe, it, expect } from 'vitest'
import { PLANNER_STEP_META, getPlannerPageMeta, STATIC_PAGE_META, STATIC_PAGE_IDS } from './pageMeta'
import { UI_STEP_PATHS } from './seoRoutes'

describe('pageMeta', () => {
  it('keeps planner paths aligned with seoRoutes', () => {
    for (let i = 0; i < UI_STEP_PATHS.length; i++) {
      expect(PLANNER_STEP_META[i]?.path).toBe(UI_STEP_PATHS[i])
    }
  })

  it('returns full meta for each planner step', () => {
    for (let s = 0; s < 6; s++) {
      const m = getPlannerPageMeta(s)
      expect(m.title).toBeTruthy()
      expect(m.description).toBeTruthy()
      expect(m.keywords).toBeTruthy()
      expect(m.pageUrl).toMatch(/^https:\/\//)
      expect(m.ogImage).toMatch(/favicon/)
      expect(m.twitterImage).toBe(m.ogImage)
    }
  })

  it('lists every static page id with meta', () => {
    for (const id of STATIC_PAGE_IDS) {
      expect(STATIC_PAGE_META[id]).toBeTruthy()
      expect(STATIC_PAGE_META[id].path).toMatch(/^\//)
    }
  })
})
