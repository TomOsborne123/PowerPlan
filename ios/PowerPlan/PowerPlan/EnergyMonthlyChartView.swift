import Charts
import SwiftUI

/// Mirrors `frontend/src/ResultView.jsx` monthly chart: solar, wind, usage split, insulation-adjusted heating, net demand (kWh/month).
///
/// Uses `foregroundStyle(by:)` so each series gets its own style inside a `List` (row tint overrides fixed colours like `.orange` on every line).
struct EnergyMonthlyChartView: View {
    let result: RecommendResponse

    /// Series keys shown in the chart and legend toggles (must match `plotPoints` / colour scale).
    private static let allSeriesKeys: [String] = [
        seriesSolar,
        seriesWind,
        seriesUsageBefore,
        seriesUsageAfter,
        seriesDemand,
    ]

    private static let seriesSolar = "Solar"
    private static let seriesWind = "Wind"
    private static let seriesUsageBefore = "Usage (baseline)"
    private static let seriesUsageAfter = "Heating + insulation"
    private static let seriesDemand = "Net demand"

    private static let seriesSortOrder: [String: Int] = [
        seriesSolar: 0,
        seriesWind: 1,
        seriesUsageBefore: 2,
        seriesUsageAfter: 3,
        seriesDemand: 4,
    ]

    private static let seriesColor: [String: Color] = [
        seriesSolar: .orange,
        seriesWind: .blue,
        seriesUsageBefore: .red,
        seriesUsageAfter: .green,
        seriesDemand: .purple,
    ]

    @State private var visibleSeries: Set<String> = Set(Self.allSeriesKeys)

    private struct ChartRow {
        let monthOrder: Int
        let month: String
        let solar: Double
        let wind: Double
        let usageBefore: Double
        let usageAfter: Double
        let demand: Double
    }

    private struct PlotPoint: Identifiable {
        let id: String
        let monthOrder: Int
        let series: String
        let kwh: Double
        let dashed: Bool
    }

    var body: some View {
        Group {
            if chartRows.isEmpty {
                Text("No monthly energy breakdown for this run (needs 12 months of flux data from the API).")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                if visiblePlotPoints.isEmpty {
                    Text("Turn on at least one series below.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 120, alignment: .center)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("kWh / month")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Chart {
                            ForEach(visiblePlotPoints) { pt in
                                LineMark(
                                    x: .value("Month", pt.monthOrder),
                                    y: .value("kWh", pt.kwh)
                                )
                                .foregroundStyle(by: .value("Series", pt.series))
                                .lineStyle(pt.dashed ? StrokeStyle(lineWidth: 2, dash: [6, 4]) : StrokeStyle(lineWidth: 2))
                            }
                        }
                        .frame(height: 220)
                        .chartYAxis {
                            AxisMarks(position: .leading) { value in
                                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                                    .foregroundStyle(.secondary.opacity(0.35))
                                AxisTick(stroke: StrokeStyle(lineWidth: 0.5))
                                    .foregroundStyle(.secondary.opacity(0.5))
                                AxisValueLabel {
                                    if let y = value.as(Double.self) {
                                        Text(Self.formatKwhAxisTick(y))
                                            .font(.caption2)
                                    }
                                }
                            }
                        }
                        .chartXAxis {
                            AxisMarks(values: .stride(by: 2)) { value in
                                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                                    .foregroundStyle(.secondary.opacity(0.25))
                                AxisValueLabel {
                                    if let i = value.as(Int.self), i >= 0, i < chartRows.count {
                                        Text(chartRows[i].month)
                                            .font(.caption2)
                                    }
                                }
                            }
                        }
                        .modifier(MonthlyChartSeriesColorsModifier())
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Tap a row to show or hide that line.")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    ForEach(Self.allSeriesKeys, id: \.self) { key in
                        seriesToggleRow(series: key)
                    }
                }
                .padding(.top, 4)
                Text("Typical year: monthly kWh (same idea as the web results graph).")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private func seriesToggleRow(series: String) -> some View {
        let on = visibleSeries.contains(series)
        let color = Self.seriesColor[series] ?? .gray
        return Button {
            if on {
                guard visibleSeries.count > 1 else { return }
                visibleSeries.remove(series)
            } else {
                visibleSeries.insert(series)
            }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(on ? color : .secondary)
                    .imageScale(.medium)
                Circle()
                    .fill(color.opacity(on ? 1 : 0.25))
                    .frame(width: 8, height: 8)
                Text(series)
                    .font(.caption)
                    .foregroundStyle(on ? .primary : .secondary)
                    .strikethrough(!on, color: .secondary)
                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(series), \(on ? "shown" : "hidden")")
        .accessibilityHint("Double tap to toggle")
    }

    private var chartRows: [ChartRow] {
        guard let monthly = result.monthlyBalance, !monthly.isEmpty, let opt = result.optimization else { return [] }
        let labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        let (nonHeatingW, heatingW) = Self.typicalMonthlyWeights()

        let totalBefore = opt.annualDemandBeforeAdjustmentsKwh ?? opt.annualDemandKwh ?? 0
        let hf = opt.heatingFraction ?? 0.6
        let heatingBefore = totalBefore * hf
        let nonHeatingBefore = totalBefore - heatingBefore

        let totalAfter = opt.annualDemandAfterInsulationKwh ?? opt.annualDemandKwh ?? 0
        let heatingAfter = opt.heatingDemandAfterInsulationKwh ?? 0
        let nonHeatingAfter = totalAfter - heatingAfter

        return monthly.enumerated().map { idx, m in
            let label = m.month ?? (idx < labels.count ? labels[idx] : "M\(idx)")
            let solar = m.solarKwh ?? 0
            let wind = m.windKwh ?? 0
            let demand = m.demandKwh ?? 0
            let i = min(idx, 11)
            let ub = nonHeatingBefore * nonHeatingW[i] + heatingBefore * heatingW[i]
            let ua = nonHeatingAfter * nonHeatingW[i] + heatingAfter * heatingW[i]
            return ChartRow(monthOrder: idx, month: label, solar: solar, wind: wind, usageBefore: ub, usageAfter: ua, demand: demand)
        }
    }

    private var plotPoints: [PlotPoint] {
        var pts: [PlotPoint] = []
        for r in chartRows {
            let ord = r.monthOrder
            pts.append(PlotPoint(id: "\(ord)-s", monthOrder: ord, series: Self.seriesSolar, kwh: r.solar, dashed: false))
            pts.append(PlotPoint(id: "\(ord)-w", monthOrder: ord, series: Self.seriesWind, kwh: r.wind, dashed: false))
            pts.append(PlotPoint(id: "\(ord)-ub", monthOrder: ord, series: Self.seriesUsageBefore, kwh: r.usageBefore, dashed: true))
            pts.append(PlotPoint(id: "\(ord)-ua", monthOrder: ord, series: Self.seriesUsageAfter, kwh: r.usageAfter, dashed: true))
            pts.append(PlotPoint(id: "\(ord)-d", monthOrder: ord, series: Self.seriesDemand, kwh: r.demand, dashed: false))
        }
        return pts.sorted {
            let o0 = Self.seriesSortOrder[$0.series] ?? 99
            let o1 = Self.seriesSortOrder[$1.series] ?? 99
            if o0 != o1 { return o0 < o1 }
            return $0.monthOrder < $1.monthOrder
        }
    }

    private var visiblePlotPoints: [PlotPoint] {
        plotPoints.filter { visibleSeries.contains($0.series) }
    }

    private static func formatKwhAxisTick(_ v: Double) -> String {
        let a = abs(v)
        if a >= 10_000 {
            return String(format: "%.0fk", v / 1000)
        }
        return String(format: "%.0f", v)
    }

    private static func typicalMonthlyWeights() -> (nonHeating: [Double], heating: [Double]) {
        let winter = (0 ..< 12).map { m -> Double in
            0.5 + 0.5 * cos(2.0 * .pi * (Double(m) / 12.0))
        }
        let heatingRaw = winter.map { wf in 0.05 + 0.95 * pow(wf, 1.5) }
        let nonHeatingRaw = winter.map { wf in 0.08 + 0.12 * wf }
        let heatingSum = heatingRaw.reduce(0, +)
        let nonHeatingSum = nonHeatingRaw.reduce(0, +)
        let heating = heatingRaw.map { $0 / max(heatingSum, 1e-9) }
        let nonHeating = nonHeatingRaw.map { $0 / max(nonHeatingSum, 1e-9) }
        return (nonHeating, heating)
    }
}

private struct MonthlyChartSeriesColorsModifier: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 17.0, *) {
            content
                .chartForegroundStyleScale([
                    "Solar": .orange,
                    "Wind": .blue,
                    "Usage (baseline)": .red,
                    "Heating + insulation": .green,
                    "Net demand": .purple,
                ])
        } else {
            content
        }
    }
}
