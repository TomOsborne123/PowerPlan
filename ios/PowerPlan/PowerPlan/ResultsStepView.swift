import SwiftUI

struct ResultsStepView: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var tariffRankingExpanded = false

    var body: some View {
        List {
            if let opt = vm.recommendResult?.optimization {
                Section("Optimal system") {
                    LabeledContent("Solar kW", value: fmt(opt.optimalSolarKw))
                    LabeledContent("Wind kW", value: fmt(opt.optimalWindKw))
                    LabeledContent("Battery kWh", value: fmt(opt.optimalBatteryKwh))
                    LabeledContent("Generation kWh/yr", value: fmt(opt.annualGenerationKwh))
                    LabeledContent("Import kWh/yr", value: fmt(opt.annualImportKwh))
                    LabeledContent("Export kWh/yr", value: fmt(opt.annualExportKwh))
                    LabeledContent("Demand met by gen", value: "\(fmt(opt.demandMetFromGenerationPct))%")
                    LabeledContent("Capex £", value: fmt(opt.capex))
                }
            }
            if let res = vm.recommendResult {
                Section("Typical year (energy)") {
                    EnergyMonthlyChartView(result: res)
                        .padding(.vertical, 4)
                }
            }
            if let rows = vm.recommendResult?.ranking?.deduplicatedRankingPreservingOrder() {
                Section {
                    DisclosureGroup(isExpanded: $tariffRankingExpanded) {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("#\(row.rank) \(row.tariff?.supplierName ?? "—") — \(row.tariff?.tariffName ?? "")")
                                    .font(.headline)
                                if let t = row.tariff {
                                    Text("Unit \(fmt(t.unitRatePPerKwh)) p/kWh · Standing \(fmt(t.standingChargePPerDay)) p/day")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if let total = row.totalCostGbp {
                                    Text("Total incl capex (horizon): £\(String(format: "%.0f", total))")
                                        .font(.subheadline)
                                }
                                if let bill = row.opexPerYearGbp {
                                    Text("Bill ≈ £\(String(format: "%.0f", bill))/yr")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    } label: {
                        Text("Tariff ranking (\(rows.count))")
                            .font(.body.weight(.semibold))
                    }
                }
            }
            Section {
                Button("Cost projection") {
                    Task { await vm.runProjection() }
                }
                Button("Change preferences") {
                    vm.phase = .preferences
                }
            }
        }
        .disabled(vm.isBusy)
    }

    private func fmt(_ v: Double?) -> String {
        guard let v else { return "—" }
        if abs(v - round(v)) < 0.001 { return String(format: "%.0f", v) }
        return String(format: "%.1f", v)
    }
}
