import SwiftUI

/// Step-style navigation aligned with the web app’s flow pills.
struct JourneyNavBar: View {
    @EnvironmentObject private var vm: AppViewModel

    private let steps: [(title: String, phase: AppViewModel.Phase)] = [
        ("Start", .welcome),
        ("Postcode", .postcode),
        ("Setup", .preferences),
        ("Results", .results),
        ("£", .projection),
    ]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(steps.enumerated()), id: \.offset) { _, item in
                    let (title, phase) = item
                    let active = isActive(phase: phase)
                    let tappable = vm.canNavigate(to: phase) || active
                    let blocked = vm.isScrapePolling || (vm.isBusy && !active)
                    Button {
                        vm.navigate(to: phase)
                    } label: {
                        Text(title)
                            .font(.caption.weight(active ? .bold : .medium))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(active ? Color.accentColor.opacity(0.35) : Color(uiColor: .secondarySystemFill))
                            )
                            .overlay(
                                Capsule()
                                    .strokeBorder(active ? Color.accentColor : Color.clear, lineWidth: 1.5)
                            )
                    }
                    .buttonStyle(.plain)
                    .disabled(!tappable || blocked)
                    .opacity((!tappable || blocked) ? 0.45 : 1)
                }
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 6)
        }
        .background(.ultraThinMaterial)
    }

    private func isActive(phase: AppViewModel.Phase) -> Bool {
        if phase == .postcode { return vm.phase == .postcode }
        return vm.phase == phase
    }
}
