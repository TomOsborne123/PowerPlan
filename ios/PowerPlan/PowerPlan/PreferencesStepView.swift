import SwiftUI

struct PreferencesStepView: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        Form {
            if vm.isScrapePolling {
                Section {
                    ScrapeInProgressBanner()
                }
                .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                .listRowBackground(Color.clear)
            }
            Section("Annual use (kWh)") {
                TextField("e.g. 3500", text: $vm.annualConsumptionKwh)
                    .keyboardType(.decimalPad)
                    .textFieldStyle(.roundedBorder)
            }
            Section("Heating & fabric") {
                Picker("Heating share", selection: $vm.heatingFraction) {
                    ForEach(EnergyOptions.heatingShares, id: \.value) { item in
                        Text(item.label).tag(item.value)
                    }
                }
                Picker("Insulation", selection: $vm.insulationRValue) {
                    ForEach(EnergyOptions.insulation, id: \.value) { item in
                        Text(item.label).tag(item.value)
                    }
                }
                Picker("Heat pump", selection: $vm.heatPumpTier) {
                    ForEach(EnergyOptions.HeatPumpTier.allCases) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
            }
            Section("Technology bands") {
                Picker("Solar", selection: $vm.solarTier) {
                    ForEach(EnergyOptions.KitTier.allCases) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                Picker("Wind", selection: $vm.windTier) {
                    ForEach(EnergyOptions.KitTier.allCases) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                Picker("Battery", selection: $vm.batteryTier) {
                    ForEach(EnergyOptions.KitTier.allCases) { tier in
                        Text(tier.label).tag(tier)
                    }
                }
                if vm.batteryTier != .none {
                    LabeledContent("Max battery (kWh)") {
                        TextField(
                            "Max battery (kWh)",
                            value: $vm.batteryMaxKwh.clamped(to: 1 ... 50),
                            format: .number.precision(.fractionLength(0))
                        )
                        .labelsHidden()
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.trailing)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 120)
                    }
                }
            }
            Section("Optimiser bounds") {
                LabeledContent("Solar max (kW)") {
                    TextField(
                        "Solar max (kW)",
                        value: $vm.solarMaxKw.clamped(to: 0 ... 50),
                        format: .number.precision(.fractionLength(0 ... 1))
                    )
                    .labelsHidden()
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 120)
                }
                .disabled(vm.solarTier == .none)
                LabeledContent("Wind max (kW)") {
                    TextField(
                        "Wind max (kW)",
                        value: $vm.windMaxKw.clamped(to: 0 ... 30),
                        format: .number.precision(.fractionLength(0 ... 1))
                    )
                    .labelsHidden()
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 120)
                }
                .disabled(vm.windTier == .none)
            }
            Section("Other") {
                LabeledContent("Export (£/kWh)") {
                    TextField(
                        "Export (£/kWh)",
                        value: $vm.exportPricePerKwh.clamped(to: 0 ... 0.5),
                        format: .number.precision(.fractionLength(1 ... 3))
                    )
                    .labelsHidden()
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 120)
                }
                LabeledContent("Compare over (years)") {
                    TextField(
                        "Years",
                        value: $vm.optimizeOverYears.clamped(to: 1 ... 20),
                        format: .number
                    )
                    .labelsHidden()
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.trailing)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 80)
                }
                Toggle("Prefer green tariffs", isOn: $vm.preferGreen)
            }
            Section {
                Button(vm.isScrapePolling ? "Run recommendation (waiting for tariffs…)" : "Run recommendation") {
                    Task { await vm.runRecommend() }
                }
                .disabled(vm.isBusy || vm.isScrapePolling || vm.scrapeTariffs.isEmpty)
            }
        }
        .disabled(vm.isBusy)
    }
}
