import { describe, it, expect } from 'vitest'
import {
  UI_STEP_PATHS,
  uiStepToPath,
  pathToUiStep,
  normalizePublicPath,
  breadcrumbItemsForSeo,
} from './seoRoutes'

describe('seoRoutes', () => {
  it('maps steps to stable paths', () => {
    expect(UI_STEP_PATHS).toHaveLength(6)
    expect(uiStepToPath(0)).toBe('/')
    expect(uiStepToPath(5)).toBe('/projection')
    expect(uiStepToPath(99)).toBe('/')
  })

  it('normalises pathnames', () => {
    expect(normalizePublicPath('/')).toBe('/')
    expect(normalizePublicPath('/postcode/')).toBe('/postcode')
    expect(normalizePublicPath('')).toBe('/')
  })

  it('maps path to UI step', () => {
    expect(pathToUiStep('/')).toBe(0)
    expect(pathToUiStep('/optimiser')).toBe(3)
    expect(pathToUiStep('/blog/foo')).toBe(0)
  })

  it('builds breadcrumb items', () => {
    const site = 'https://www.powerplan.site'
    const home = breadcrumbItemsForSeo(site, '/', `${site}/`)
    expect(home).toHaveLength(1)
    const two = breadcrumbItemsForSeo(site, '/results', `${site}/results`)
    expect(two).toHaveLength(2)
    expect(two[1].item).toBe('https://www.powerplan.site/results')
  })
})
