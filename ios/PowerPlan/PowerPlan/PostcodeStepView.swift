import SwiftUI

struct PostcodeStepView: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        Form {
            Section("Property") {
                TextField("UK postcode", text: $vm.postcodeInput)
                    .textInputAutocapitalization(.characters)
                TextField("Address hint (optional)", text: $vm.addressName)
            }
            Section("Tariff scrape") {
                Picker("Account type", selection: $vm.homeOrBusiness) {
                    Text("Home").tag("home")
                    Text("Business").tag("business")
                }
                Picker("EV", selection: $vm.evInterest) {
                    Text("I have an EV").tag("yes")
                    Text("Interested").tag("interested")
                    Text("No / not interested").tag("no")
                }
            }
            Section {
                Button("Load saved tariffs") {
                    Task { await vm.loadExistingScrape() }
                }
                Button("Fetch tariffs (background scrape)") {
                    Task { await vm.startScrape() }
                }
            }
        }
        .disabled(vm.isBusy)
    }
}
