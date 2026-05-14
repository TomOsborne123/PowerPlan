import Foundation

// MARK: - Postcode

struct PostcodeLookupResponse: Decodable {
    let latitude: Double?
    let longitude: Double?
    let adminDistrict: String?
    let region: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case latitude, longitude, error
        case adminDistrict = "admin_district"
        case region
    }
}

// MARK: - Scrape

struct ScrapeResultsResponse: Decodable {
    let noSavedScrape: Bool?
    let tariffs: [TariffInput]?
    let annualElectricityKwh: Double?
    let latitude: Double?
    let longitude: Double?
    let searchDate: String?

    enum CodingKeys: String, CodingKey {
        case tariffs, latitude, longitude
        case noSavedScrape = "no_saved_scrape"
        case annualElectricityKwh = "annual_electricity_kwh"
        case searchDate = "search_date"
    }
}

/// Tariff row as stored / returned by scrape (before recommend normalisation).
struct TariffInput: Codable, Hashable {
    var supplierName: String?
    var newSupplierName: String?
    var tariffName: String?
    var unitRate: Double?
    var unitRatePPerKwh: Double?
    var standingChargeDay: Double?
    var standingChargePPerDay: Double?
    var isGreen: Bool?

    enum CodingKeys: String, CodingKey {
        case supplierName = "supplier_name"
        case newSupplierName = "new_supplier_name"
        case tariffName = "tariff_name"
        case unitRate = "unit_rate"
        case unitRatePPerKwh = "unit_rate_p_per_kwh"
        case standingChargeDay = "standing_charge_day"
        case standingChargePPerDay = "standing_charge_p_per_day"
        case isGreen = "is_green"
    }

    func encodedForAPI() -> [String: Any] {
        var o: [String: Any] = [:]
        let supplier = newSupplierName ?? supplierName ?? ""
        o["supplier_name"] = supplier
        o["tariff_name"] = tariffName ?? ""
        if let ur = unitRate ?? unitRatePPerKwh { o["unit_rate"] = ur }
        if let sc = standingChargeDay ?? standingChargePPerDay { o["standing_charge_day"] = sc }
        o["is_green"] = isGreen ?? false
        return o
    }

    /// Stable identity for de-duplicating scrape rows that repeat the same product/rates.
    var deduplicationKey: String {
        let sup = (newSupplierName ?? supplierName ?? "")
            .lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let name = (tariffName ?? "")
            .lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let u = unitRate ?? unitRatePPerKwh ?? -1
        let s = standingChargeDay ?? standingChargePPerDay ?? -1
        return "\(sup)|\(name)|\(String(format: "%.5g", u))|\(String(format: "%.5g", s))"
    }
}

extension Array where Element == TariffInput {
    func deduplicatedTariffsPreservingOrder() -> [TariffInput] {
        var seen = Set<String>()
        var out: [TariffInput] = []
        for t in self {
            if seen.insert(t.deduplicationKey).inserted {
                out.append(t)
            }
        }
        return out
    }
}

struct ScrapeStatusResponse: Decodable {
    let status: String
    let error: String?
}

struct RunScrapeResponse: Decodable {
    let status: String?
    let postcode: String?
    let error: String?
}

struct ExportPriceResponse: Decodable {
    let exportPricePerKwh: Double?
    let tariffName: String?
    let disclaimer: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case exportPricePerKwh = "export_price_per_kwh"
        case tariffName = "tariff_name"
        case disclaimer, error
    }
}

// MARK: - Recommend

struct RecommendResponse: Decodable {
    let recommendedTariff: TariffScored?
    let ranking: [RankingRow]?
    let optimization: OptimizationSummary?
    let optimizeOverYears: Double?
    /// 12 rows: month, solar_kwh, wind_kwh, demand_kwh, … (same as web `result.monthly_balance`).
    let monthlyBalance: [MonthlyBalanceRow]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case recommendedTariff = "recommended_tariff"
        case ranking, optimization, error
        case optimizeOverYears = "optimize_over_years"
        case monthlyBalance = "monthly_balance"
    }
}

struct MonthlyBalanceRow: Decodable, Hashable {
    let month: String?
    let solarKwh: Double?
    let windKwh: Double?
    let demandKwh: Double?

    enum CodingKeys: String, CodingKey {
        case month
        case solarKwh = "solar_kwh"
        case windKwh = "wind_kwh"
        case demandKwh = "demand_kwh"
    }
}

struct RankingRow: Decodable, Identifiable {
    var id: Int { rank }
    let rank: Int
    let totalCostGbp: Double?
    let opexPerYearGbp: Double?
    let tariff: TariffScored?

    enum CodingKeys: String, CodingKey {
        case rank
        case totalCostGbp = "total_cost_gbp"
        case opexPerYearGbp = "opex_per_year_gbp"
        case tariff
    }
}

struct TariffScored: Decodable {
    let supplierName: String?
    let tariffName: String?
    let unitRatePPerKwh: Double?
    let standingChargePPerDay: Double?
    let isGreen: Bool?

    enum CodingKeys: String, CodingKey {
        case supplierName = "supplier_name"
        case tariffName = "tariff_name"
        case unitRatePPerKwh = "unit_rate_p_per_kwh"
        case standingChargePPerDay = "standing_charge_p_per_day"
        case isGreen = "is_green"
    }

    var deduplicationKey: String {
        let sup = (supplierName ?? "").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let name = (tariffName ?? "").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let u = unitRatePPerKwh ?? -1
        let s = standingChargePPerDay ?? -1
        return "\(sup)|\(name)|\(String(format: "%.5g", u))|\(String(format: "%.5g", s))"
    }
}

extension Array where Element == RankingRow {
    /// Keeps the best-ranked row for each supplier/name/rates combo (API can repeat tariffs).
    func deduplicatedRankingPreservingOrder() -> [RankingRow] {
        var seen = Set<String>()
        var out: [RankingRow] = []
        for row in sorted(by: { $0.rank < $1.rank }) {
            if row.tariff == nil {
                out.append(row)
                continue
            }
            let key = row.tariff!.deduplicationKey
            if seen.insert(key).inserted {
                out.append(row)
            }
        }
        return out
    }
}

struct OptimizationSummary: Decodable {
    let optimalSolarKw: Double?
    let optimalWindKw: Double?
    let optimalBatteryKwh: Double?
    let totalCapacityKw: Double?
    let annualDemandKwh: Double?
    let annualGenerationKwh: Double?
    let annualImportKwh: Double?
    let annualExportKwh: Double?
    let demandMetFromGenerationPct: Double?
    let capex: Double?
    let paybackSolarYears: Double?
    let paybackWindYears: Double?
    let paybackBatteryYears: Double?
    /// Used with `monthly_balance` to mirror the web monthly chart.
    let annualDemandBeforeAdjustmentsKwh: Double?
    let heatingFraction: Double?
    let annualDemandAfterInsulationKwh: Double?
    let heatingDemandAfterInsulationKwh: Double?

    enum CodingKeys: String, CodingKey {
        case optimalSolarKw = "optimal_solar_kw"
        case optimalWindKw = "optimal_wind_kw"
        case optimalBatteryKwh = "optimal_battery_kwh"
        case totalCapacityKw = "total_capacity_kw"
        case annualDemandKwh = "annual_demand_kwh"
        case annualGenerationKwh = "annual_generation_kwh"
        case annualImportKwh = "annual_import_kwh"
        case annualExportKwh = "annual_export_kwh"
        case demandMetFromGenerationPct = "demand_met_from_generation_pct"
        case capex
        case paybackSolarYears = "payback_solar_years"
        case paybackWindYears = "payback_wind_years"
        case paybackBatteryYears = "payback_battery_years"
        case annualDemandBeforeAdjustmentsKwh = "annual_demand_before_adjustments_kwh"
        case heatingFraction = "heating_fraction"
        case annualDemandAfterInsulationKwh = "annual_demand_after_insulation_kwh"
        case heatingDemandAfterInsulationKwh = "heating_demand_after_insulation_kwh"
    }
}

// MARK: - Cost projection

struct CostProjectionResponse: Decodable {
    let years: [Int]?
    let maxYears: Int?
    let tariffLabel: String?
    let series: [ProjectionSeries]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case years, series, error
        case maxYears = "max_years"
        case tariffLabel = "tariff_label"
    }
}

struct ProjectionSeries: Decodable, Identifiable {
    var id: String { seriesId }
    let seriesId: String
    let label: String?
    let cumulativeGbp: [Double]?
    let annualRunningGbp: Double?
    let capexGbp: Double?

    enum CodingKeys: String, CodingKey {
        case label
        case seriesId = "id"
        case cumulativeGbp = "cumulative_gbp"
        case annualRunningGbp = "annual_running_gbp"
        case capexGbp = "capex_gbp"
    }
}
