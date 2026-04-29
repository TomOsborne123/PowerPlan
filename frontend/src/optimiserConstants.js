/**
 * Copy and illustrative £/kWp (solar) / £/kW (wind) for MVP — aligned with src/data/energy_tiers.py
 */
export const SOLAR_TIER_INFO = {
  none: { label: "No — I don't want solar", capexPerKw: 0, blurb: 'Solar is fixed at 0 kWp and excluded from the search.' },
  budget: { label: 'Budget', capexPerKw: 1250, blurb: 'Lower-cost kit; slightly lower yield assumptions.' },
  mid: { label: 'Mid', capexPerKw: 1600, blurb: 'Balanced cost and performance.' },
  premium: { label: 'Premium', capexPerKw: 1950, blurb: 'Higher-spec panels/inverter; better modelled output.' },
}

export const WIND_TIER_INFO = {
  none: { label: "No — I don't want wind", capexPerKw: 0, blurb: 'Wind is fixed at 0 kW and excluded from the search.' },
  budget: { label: 'Budget', capexPerKw: 2300, blurb: 'Entry-level small wind assumptions.' },
  mid: { label: 'Mid', capexPerKw: 2750, blurb: 'Balanced turbine assumptions.' },
  premium: { label: 'Premium', capexPerKw: 3300, blurb: 'Higher-spec turbine / install assumptions.' },
}

export const BATTERY_TIER_INFO = {
  none: { label: "No — I don't want a battery", capexPerKwh: 0, blurb: 'Battery is fixed at 0 kWh and excluded from the search.' },
  budget: { label: 'Budget', capexPerKwh: 600, blurb: 'Entry-level home battery (~85% round-trip).' },
  mid: { label: 'Mid', capexPerKwh: 800, blurb: 'Modern lithium battery (~90% round-trip).' },
  premium: { label: 'Premium', capexPerKwh: 1050, blurb: 'High-spec battery + inverter (~94% round-trip).' },
}

/** Default usable battery sizes (kWh) used in the cost-projection scenario. */
export const PROJECTION_SCENARIO_BATTERY_KWH = { none: 0, budget: 5, mid: 8, premium: 12 }

/** Fixed kWp used only on the cost-projection step (independent of optimiser tier sliders). */
export const PROJECTION_SCENARIO_SOLAR_KW = { budget: 3, mid: 4.5, premium: 6 }
/** Fixed kW nominal used only on the cost-projection step. */
export const PROJECTION_SCENARIO_WIND_KW = { budget: 1, mid: 2, premium: 3.5 }

/** Share of yearly electricity use that goes to space heating (0–1). */
export const HEATING_SHARE_OPTIONS = [
  { value: 0.25, label: 'Low — mostly appliances & hot water; heating is a small slice' },
  { value: 0.4, label: 'Moderate — some electric heating or mild winters' },
  { value: 0.5, label: 'Half and half — rough 50/50 heating vs everything else' },
  { value: 0.6, label: 'Typical — heating is a big part (default for many homes)' },
  { value: 0.75, label: 'High — heating dominates your electricity use' },
]

/**
 * Fabric/insulation model input (m²·K/W style scalar in the optimiser).
 * Default matches “typical mixed UK stock with some loft/cavity improvement”.
 */
export const INSULATION_OPTIONS = [
  { value: 0, label: "No — I don't want insulation modelled (no change to heating demand)" },
  { value: 1.0, label: 'Basic — some loft; walls still fairly leaky' },
  { value: 2.5, label: 'Typical UK — loft + partial cavity / mixed stock (default)' },
  { value: 4.0, label: 'Good — solid retrofit (e.g. full cavity, thick loft)' },
  { value: 6.0, label: 'Strong — closer to new-build fabric' },
]

export const HEAT_PUMP_OPTIONS = [
  {
    value: 'none',
    cop: 1.0,
    label: "No — I don't want a heat pump (ordinary electric heating, COP 1)",
    specUrl: 'https://www.energysavingtrust.org.uk/advice/electric-heating/',
  },
  {
    value: 'budget',
    cop: 2.5,
    label: 'Budget — typical older ASHP (COP ~2.5)',
    specUrl: 'https://www.energysavingtrust.org.uk/advice/air-source-heat-pumps/',
  },
  {
    value: 'mid',
    cop: 3.0,
    label: 'Mid — modern ASHP (COP ~3.0)',
    specUrl: 'https://www.gov.uk/improve-energy-efficiency',
  },
  {
    value: 'premium',
    cop: 3.5,
    label: 'Premium — high-performance ASHP (COP ~3.5)',
    specUrl: 'https://mcscertified.com/',
  },
]

export function copForHeatPumpTier(tier) {
  const row = HEAT_PUMP_OPTIONS.find((o) => o.value === tier)
  return row ? row.cop : 3.0
}

/**
 * Suggested UK installer finder links for each technology.
 * These are intentionally "directory" style pages rather than endorsement URLs.
 */
export const INSTALLER_SUGGESTIONS = [
  {
    key: 'solar',
    title: 'Solar PV',
    note: 'Use the directory and filter by “Solar PV”.',
    links: [
      { label: 'MCS – Find an installer', href: 'https://www.mcscertified.com/find-an-installer/' },
    ],
  },
  {
    key: 'wind',
    title: 'Small wind',
    note: 'Use the directory and filter by “Small Wind Turbines”.',
    links: [
      { label: 'MCS – Find an installer', href: 'https://www.mcscertified.com/find-an-installer/' },
    ],
  },
  {
    key: 'insulation',
    title: 'Insulation / retrofit',
    note: 'Search by postcode/town in the directory.',
    links: [{ label: 'NIA – Find an installer', href: 'https://www.nia-uk.org/find-an-installer/' }],
  },
  {
    key: 'heat_pump',
    title: 'Heat pumps',
    note: 'Use the directory and filter by heat-pump type as needed.',
    links: [
      { label: 'GOV.UK – Find a heat pump installer', href: 'https://www.gov.uk/guidance/find-a-heat-pump-installer' },
      { label: 'MCS – Find an installer', href: 'https://www.mcscertified.com/find-an-installer/' },
    ],
  },
  {
    key: 'battery',
    title: 'Battery storage',
    note: 'Use the manufacturer/partner directory for certified installers.',
    links: [
      { label: 'Tesla – Certified installers (Powerwall)', href: 'https://www.tesla.com/en_GB/support/certified-installers?productType=powerwall' },
      { label: 'Renewables Excellence – Battery storage installers', href: 'https://renewablesexcellence.co.uk/battery-storage-installers/' },
    ],
  },
]
