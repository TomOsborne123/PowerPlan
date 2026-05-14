import SwiftUI

struct ContentView: View {
    @StateObject private var vm = AppViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if vm.phase != .welcome {
                    JourneyNavBar()
                        .environmentObject(vm)
                }
                Group {
                    switch vm.phase {
                    case .welcome:
                        WelcomeView()
                    case .postcode:
                        PostcodeStepView()
                    case .preferences:
                        PreferencesStepView()
                    case .results:
                        ResultsStepView()
                    case .projection:
                        ProjectionStepView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .environmentObject(vm)
            .overlay {
                if vm.isBusy {
                    ZStack {
                        Color.black.opacity(0.2).ignoresSafeArea()
                        ProgressView("Working…")
                            .padding(24)
                            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                    }
                }
            }
            .navigationTitle(navTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if vm.phase != .welcome {
                        Button("Home") { vm.goWelcome() }
                    }
                }
            }
            .alert("Error", isPresented: Binding(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
        }
    }

    private var navTitle: String {
        switch vm.phase {
        case .welcome: return "PowerPlan"
        case .postcode: return "Postcode"
        case .preferences: return "Preferences"
        case .results: return "Results"
        case .projection: return "Projection"
        }
    }
}
