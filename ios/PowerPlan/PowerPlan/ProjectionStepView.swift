import Charts
import SwiftUI

private struct ChartPoint: Identifiable {
    var id: String { "\(seriesId)-\(year)" }
    let year: Int
    let gbp: Double
    let label: String
    let seriesId: String
}

struct ProjectionStepView: View {
    @EnvironmentObject private var vm: AppViewModel
    /// Scenario `seriesId`s hidden from the cumulative chart (empty = all visible).
    @State private var hiddenScenarioIds: Set<String> = []

    private var projectionFingerprint: String {
        guard let s = vm.projectionResult?.series else { return "" }
        return s.map(\.seriesId).sorted().joined(separator: "|")
    }

    var body: some View {
        List {
            if let res = vm.projectionResult {
                Section("Summary") {
                    Text(res.tariffLabel ?? "")
                        .font(.subheadline)
                }
                if let allPoints = chartPoints(from: res), !allPoints.isEmpty {
                    let visible = allPoints.filter { !hiddenScenarioIds.contains($0.seriesId) }
                    Section("Cumulative cost") {
                        Group {
                            if visible.isEmpty {
                                Text("Turn on at least one scenario below.")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, minHeight: 160, alignment: .center)
                            } else {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("£ cumulative")
                                        .font(.caption2.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Chart(visible) { point in
                                        LineMark(
                                            x: .value("Year", point.year),
                                            y: .value("£", point.gbp)
                                        )
                                        .foregroundStyle(by: .value("Scenario", point.label))
                                    }
                                    .frame(height: 260)
                                    .chartYAxis {
                                        AxisMarks(position: .leading) { value in
                                            AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                                                .foregroundStyle(.secondary.opacity(0.35))
                                            AxisTick(stroke: StrokeStyle(lineWidth: 0.5))
                                                .foregroundStyle(.secondary.opacity(0.5))
                                            AxisValueLabel {
                                                if let g = value.as(Double.self) {
                                                    Text(Self.formatGbpAxisTick(g))
                                                        .font(.caption2)
                                                }
                                            }
                                        }
                                    }
                                    .chartXAxis {
                                        AxisMarks(position: .bottom) { value in
                                            AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                                                .foregroundStyle(.secondary.opacity(0.25))
                                            AxisValueLabel {
                                                if let y = value.as(Int.self) {
                                                    Text(String(y))
                                                        .font(.caption2)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        scenarioToggles(series: res.series ?? [], allPoints: allPoints)
                    }
                }
                Section("Scenarios (final year)") {
                    ForEach(res.series ?? []) { s in
                        let final = s.cumulativeGbp?.last
                        LabeledContent(s.label ?? s.id, value: final.map { "£\(String(format: "%.0f", $0))" } ?? "—")
                    }
                }
            }
            Section {
                LabeledContent("Horizon (years)") {
                    TextField(
                        "Horizon (years)",
                        value: $vm.projectionYears.clamped(to: 1 ... 20),
                        format: .number
                    )
                    .labelsHidden()
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.trailing)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 80)
                }
                Picker("Projection solar tier", selection: $vm.projectionSolarTier) {
                    ForEach(EnergyOptions.KitTier.allCases.filter { $0 != .none }) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                Picker("Projection wind tier", selection: $vm.projectionWindTier) {
                    ForEach(EnergyOptions.KitTier.allCases.filter { $0 != .none }) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                Picker("Projection battery tier", selection: $vm.projectionBatteryTier) {
                    ForEach(EnergyOptions.KitTier.allCases) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                Button("Refresh projection") {
                    Task { await vm.runProjection() }
                }
            }
        }
        .disabled(vm.isBusy)
        .onChange(of: projectionFingerprint) { new in
            if !new.isEmpty {
                hiddenScenarioIds = []
            }
        }
        .onAppear {
            if !projectionFingerprint.isEmpty {
                hiddenScenarioIds = []
            }
        }
    }

    @ViewBuilder
    private func scenarioToggles(series: [ProjectionSeries], allPoints: [ChartPoint]) -> some View {
        let idsInChart = Set(allPoints.map(\.seriesId))
        let ordered = series.filter { idsInChart.contains($0.seriesId) }
        if ordered.count <= 1 {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text("Tap a scenario to show or hide its line.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                ForEach(ordered) { s in
                    let shown = !hiddenScenarioIds.contains(s.seriesId)
                    Button {
                        if shown {
                            let visibleCount = idsInChart.filter { !hiddenScenarioIds.contains($0) }.count
                            guard visibleCount > 1 else { return }
                            hiddenScenarioIds.insert(s.seriesId)
                        } else {
                            hiddenScenarioIds.remove(s.seriesId)
                        }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: shown ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(shown ? Color.accentColor : .secondary)
                                .imageScale(.medium)
                            Text(s.label ?? s.seriesId)
                                .font(.caption)
                                .foregroundStyle(shown ? .primary : .secondary)
                                .strikethrough(!shown, color: .secondary)
                                .multilineTextAlignment(.leading)
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(s.label ?? s.seriesId), \(shown ? "shown" : "hidden")")
                }
            }
            .padding(.top, 6)
        }
    }

    private static func formatGbpAxisTick(_ v: Double) -> String {
        let sign = v < 0 ? "-" : ""
        let x = abs(v)
        if x >= 1_000_000 {
            return "\(sign)£\(String(format: "%.1fM", x / 1_000_000))"
        }
        if x >= 1000 {
            return "\(sign)£\(String(format: "%.0fk", x / 1000))"
        }
        return "\(sign)£\(String(format: "%.0f", x))"
    }

    private func chartPoints(from res: CostProjectionResponse) -> [ChartPoint]? {
        guard let years = res.years, let series = res.series else { return nil }
        var out: [ChartPoint] = []
        for s in series.prefix(6) {
            guard let cum = s.cumulativeGbp else { continue }
            for (i, y) in years.enumerated() where i < cum.count {
                out.append(ChartPoint(year: y, gbp: cum[i], label: s.label ?? s.id, seriesId: s.seriesId))
            }
        }
        return out
    }
}
