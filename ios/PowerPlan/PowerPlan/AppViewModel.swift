import Foundation
import SwiftUI

@MainActor
final class AppViewModel: ObservableObject {
    enum Phase: Hashable {
        case welcome
        case postcode
        case preferences
        case results
        case projection
    }

    @Published var phase: Phase = .welcome
    @Published var errorMessage: String?
    @Published var isBusy = false
    /// True while the server is still scraping tariffs (user can be on preferences like the website).
    @Published var isScrapePolling = false
    /// Time-based scrape progress 0…1 (mirrors web `scrapeProgressPct`; not tied to server %).
    @Published var scrapeProgressFraction: Double = 0

    private var scrapeProgressTask: Task<Void, Never>?
    private var scrapePollTask: Task<Void, Never>?

    // Postcode step
    @Published var postcodeInput = ""
    @Published var addressName = "1 Savings Lane"
    @Published var homeOrBusiness = "home"
    @Published var evInterest = "interested" // yes | no | interested

    // Loaded from scrape / lookup
    @Published var latitude: Double?
    @Published var longitude: Double?
    @Published var annualConsumptionKwh = ""
    @Published var scrapeTariffs: [TariffInput] = []
    @Published var scrapeStatusText = ""

    // Preferences
    @Published var heatingFraction = 0.6
    @Published var insulationRValue = 2.5
    @Published var heatPumpTier: EnergyOptions.HeatPumpTier = .mid
    @Published var solarTier: EnergyOptions.KitTier = .budget
    @Published var windTier: EnergyOptions.KitTier = .budget
    @Published var batteryTier: EnergyOptions.KitTier = .none
    @Published var batteryMaxKwh = 15.0
    @Published var solarMaxKw = 20.0
    @Published var windMaxKw = 10.0
    @Published var preferGreen = false
    @Published var optimizeOverYears = 5
    @Published var exportPricePerKwh = 0.05

    // Results
    @Published private(set) var recommendResult: RecommendResponse?

    // Projection
    @Published var projectionYears = 20
    @Published var projectionSolarTier: EnergyOptions.KitTier = .mid
    @Published var projectionWindTier: EnergyOptions.KitTier = .mid
    @Published var projectionBatteryTier: EnergyOptions.KitTier = .none
    @Published private(set) var projectionResult: CostProjectionResponse?

    private let client = PowerPlanClient()

    var normalizedPostcode: String {
        PostcodeNormalizer.normalize(postcodeInput)
    }

    func goWelcome() {
        cancelActiveScrape(reason: .userNavigatedAway)
        phase = .welcome
        errorMessage = nil
    }

    func goPostcode() {
        cancelActiveScrape(reason: .userNavigatedAway)
        phase = .postcode
        errorMessage = nil
    }

    private enum ScrapeCancelReason {
        case userNavigatedAway
    }

    private func cancelActiveScrape(reason: ScrapeCancelReason) {
        scrapePollTask?.cancel()
        scrapePollTask = nil
        if isScrapePolling {
            isScrapePolling = false
            stopScrapeProgressAnimation(completed: false)
        }
        if reason == .userNavigatedAway {
            scrapeStatusText = ""
        }
    }

    /// Whether the user may jump to this step from the journey bar.
    func canNavigate(to target: Phase) -> Bool {
        switch target {
        case .welcome: return true
        case .postcode: return !isScrapePolling
        case .preferences: return isScrapePolling || !scrapeTariffs.isEmpty
        case .results: return recommendResult != nil
        case .projection: return recommendResult != nil
        }
    }

    func navigate(to target: Phase) {
        guard canNavigate(to: target) else { return }
        errorMessage = nil
        switch target {
        case .welcome: goWelcome()
        case .postcode: goPostcode()
        case .preferences: phase = .preferences
        case .results: phase = .results
        case .projection: phase = .projection
        }
    }

    func loadExistingScrape(showBusy: Bool = true) async {
        errorMessage = nil
        guard PostcodeNormalizer.isValidForApp(normalizedPostcode) else {
            errorMessage = "Enter a valid UK postcode area (e.g. BS39) or full postcode (e.g. BS1 1AA)."
            return
        }
        if showBusy { isBusy = true }
        defer { if showBusy { isBusy = false } }
        do {
            let r = try await client.fetchScrapeResults(postcode: normalizedPostcode)
            if r.noSavedScrape == true || (r.tariffs?.isEmpty ?? true) {
                errorMessage = "No saved tariffs for this postcode. Use “Fetch tariffs” to run the scraper (can take a few minutes)."
                latitude = r.latitude
                longitude = r.longitude
                scrapeTariffs = (r.tariffs ?? []).deduplicatedTariffsPreservingOrder()
                if let kwh = r.annualElectricityKwh, annualConsumptionKwh.isEmpty {
                    annualConsumptionKwh = String(format: "%.0f", kwh)
                }
                phase = .postcode
                return
            }
            scrapeTariffs = (r.tariffs ?? []).deduplicatedTariffsPreservingOrder()
            latitude = r.latitude
            longitude = r.longitude
            if let kwh = r.annualElectricityKwh {
                annualConsumptionKwh = String(format: "%.0f", kwh)
            }
            if PostcodeNormalizer.isFullPostcode(normalizedPostcode) {
                let loc = try await client.lookupPostcode(normalizedPostcode)
                if let la = loc.latitude, let lo = loc.longitude {
                    latitude = la
                    longitude = lo
                }
            }
            try await refreshExportHint()
            phase = .preferences
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startScrape() async {
        errorMessage = nil
        guard PostcodeNormalizer.isValidForApp(normalizedPostcode) else {
            errorMessage = "Enter a valid UK postcode first."
            return
        }
        scrapePollTask?.cancel()
        scrapePollTask = nil
        isBusy = true
        do {
            try await client.runScrape(
                postcode: normalizedPostcode,
                homeOrBusiness: homeOrBusiness,
                hasEv: evInterest,
                addressName: addressName,
                addressIndex: 0
            )
        } catch {
            isBusy = false
            errorMessage = error.localizedDescription
            return
        }
        isBusy = false
        isScrapePolling = true
        phase = .preferences
        startScrapeProgressAnimation()
        scrapePollTask = Task { [weak self] in
            guard let self else { return }
            await self.pollUntilScrapeDone()
        }
    }

    /// Same timing idea as `frontend/src/App.jsx`: ~0–12% over 9s, then ~12–92% over 130s.
    private func startScrapeProgressAnimation() {
        scrapeProgressFraction = 0
        scrapeProgressTask?.cancel()
        let started = Date()
        scrapeProgressTask = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 400_000_000)
                guard isScrapePolling else { break }
                let t = Date().timeIntervalSince(started)
                let pct: Double
                if t < 9 {
                    pct = (t / 9.0) * 12.0
                } else {
                    pct = min(92.0, 12.0 + ((t - 9.0) / 130.0) * 80.0)
                }
                scrapeProgressFraction = pct / 100.0
            }
        }
    }

    private func stopScrapeProgressAnimation(completed: Bool) {
        scrapeProgressTask?.cancel()
        scrapeProgressTask = nil
        scrapeProgressFraction = completed ? 1.0 : 0
    }

    private func pollUntilScrapeDone() async {
        scrapeStatusText = "Starting…"
        for _ in 0 ..< 200 {
            do {
                try await Task.sleep(nanoseconds: 2_000_000_000)
            } catch is CancellationError {
                handleScrapePollCancelled()
                return
            } catch {
                handleScrapePollFailure(message: error.localizedDescription)
                return
            }
            if Task.isCancelled {
                handleScrapePollCancelled()
                return
            }
            do {
                let st = try await client.scrapeStatus(postcode: normalizedPostcode)
                scrapeStatusText = Self.displayScrapeStatus(st.status)
                if st.status == "completed" {
                    isScrapePolling = false
                    stopScrapeProgressAnimation(completed: true)
                    scrapePollTask = nil
                    await loadExistingScrape(showBusy: false)
                    if phase != .preferences { errorMessage = errorMessage ?? "Scrape finished but no tariffs found." }
                    return
                }
                if st.status == "failed" {
                    isScrapePolling = false
                    stopScrapeProgressAnimation(completed: false)
                    scrapePollTask = nil
                    errorMessage = st.error ?? "Scrape failed"
                    phase = .postcode
                    return
                }
            } catch {
                isScrapePolling = false
                stopScrapeProgressAnimation(completed: false)
                scrapePollTask = nil
                errorMessage = error.localizedDescription
                phase = .postcode
                return
            }
        }
        isScrapePolling = false
        stopScrapeProgressAnimation(completed: false)
        scrapePollTask = nil
        errorMessage = "Timed out waiting for scrape. Try again or check the API server."
        phase = .postcode
    }

    private func handleScrapePollCancelled() {
        isScrapePolling = false
        stopScrapeProgressAnimation(completed: false)
        scrapePollTask = nil
        scrapeStatusText = ""
    }

    private func handleScrapePollFailure(message: String) {
        isScrapePolling = false
        stopScrapeProgressAnimation(completed: false)
        scrapePollTask = nil
        errorMessage = message
        phase = .postcode
    }

    /// Present API scrape states with sentence case (e.g. `running` → `Running`).
    private static func displayScrapeStatus(_ raw: String) -> String {
        let t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return raw }
        return t.capitalized
    }

    private func refreshExportHint() async throws {
        let ref = try await client.exportPriceReference()
        if let p = ref.exportPricePerKwh {
            exportPricePerKwh = p
        }
    }

    func runRecommend() async {
        errorMessage = nil
        isBusy = true
        defer { isBusy = false }
        do {
            let usage = Double(annualConsumptionKwh.replacingOccurrences(of: ",", with: ".")) ?? 0
            let solarOff = solarTier == .none
            let windOff = windTier == .none
            let batteryOff = batteryTier == .none
            let solarMax = solarOff ? 0.0 : max(0, solarMaxKw)
            let windMax = windOff ? 0.0 : max(0, windMaxKw)
            let batteryMax = batteryOff ? 0.0 : max(0, batteryMaxKwh)
            let solarMin = solarOff ? 0.0 : min(solarMax, 1.5 * (solarMax / 20.0))
            let windMin = windOff ? 0.0 : min(windMax, 0.5 * (windMax / 10.0))

            let tariffsJson: [[String: Any]] = scrapeTariffs.map { $0.encodedForAPI() }
            guard !tariffsJson.isEmpty else {
                errorMessage = "No tariffs loaded. Fetch tariffs for this postcode or load a saved scrape first."
                return
            }

            var payload: [String: Any] = [
                "postcode": normalizedPostcode,
                "latitude": latitude ?? 0,
                "longitude": longitude ?? 0,
                "tariffs": tariffsJson,
                "heating_fraction": heatingFraction,
                "insulation_r_value": insulationRValue,
                "heat_pump_cop": heatPumpTier.cop,
                "solar_tier": solarTier.rawValue,
                "wind_tier": windTier.rawValue,
                "battery_tier": batteryTier.rawValue,
                "export_price_per_kwh": exportPricePerKwh,
                "solar_max_kw": solarMax,
                "wind_max_kw": windMax,
                "battery_max_kwh": batteryMax,
                "battery_min_kwh": 0,
                "battery_step_kwh": 1,
                "min_solar_kw": solarMin,
                "min_wind_kw": windMin,
                "optimize_over_years": optimizeOverYears,
                "prefer_green": preferGreen,
            ]
            if usage > 0 {
                payload["annual_consumption_kwh"] = usage
            }

            let res = try await client.recommend(payload: payload)
            if let err = res.error, res.ranking == nil {
                errorMessage = err
                return
            }
            recommendResult = res
            phase = .results
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runProjection() async {
        errorMessage = nil
        guard let ranking = recommendResult?.ranking, let first = ranking.first,
              let t = first.tariff,
              let unit = t.unitRatePPerKwh,
              let standing = t.standingChargePPerDay else {
            errorMessage = "Need recommendation results first."
            return
        }
        let usage = Double(annualConsumptionKwh.replacingOccurrences(of: ",", with: ".")) ?? 3500
        let solarKw = EnergyOptions.projectionSolarKw(tier: projectionSolarTier)
        let windKw = EnergyOptions.projectionWindKw(tier: projectionWindTier)
        let battKwh = EnergyOptions.projectionBatteryKwh(tier: projectionBatteryTier)

        let label = "\(t.supplierName ?? "Tariff") — \(t.tariffName ?? "")"

        let payload: [String: Any] = [
            "postcode": normalizedPostcode,
            "latitude": latitude ?? 0,
            "longitude": longitude ?? 0,
            "annual_consumption_kwh": usage,
            "heating_fraction": heatingFraction,
            "heat_pump_cop": heatPumpTier.cop,
            "export_price_per_kwh": exportPricePerKwh,
            "unit_rate_p_per_kwh": unit,
            "standing_charge_p_per_day": standing,
            "max_years": projectionYears,
            "baseline_insulation_r_value": 2.5,
            "upgraded_insulation_r_value": max(4.0, insulationRValue),
            "scenario_solar_kw": solarKw,
            "scenario_wind_kw": windKw,
            "scenario_battery_kwh": battKwh,
            "solar_tier": projectionSolarTier.rawValue,
            "wind_tier": projectionWindTier.rawValue,
            "battery_tier": projectionBatteryTier.rawValue,
            "tariff_label": label,
        ]
        isBusy = true
        defer { isBusy = false }
        do {
            projectionResult = try await client.costProjection(payload: payload)
            phase = .projection
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

extension Binding where Value == Double {
    func clamped(to range: ClosedRange<Double>) -> Binding<Double> {
        Binding(
            get: { self.wrappedValue },
            set: { newValue in
                self.wrappedValue = Swift.min(range.upperBound, Swift.max(range.lowerBound, newValue))
            }
        )
    }
}

extension Binding where Value == Int {
    func clamped(to range: ClosedRange<Int>) -> Binding<Int> {
        Binding(
            get: { self.wrappedValue },
            set: { newValue in
                self.wrappedValue = Swift.min(range.upperBound, Swift.max(range.lowerBound, newValue))
            }
        )
    }
}
