import SwiftUI

/// Welcome screen aligned with `frontend/src/index.css` (`.welcome`) and `App.jsx` step 0.
struct WelcomeView: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var appeared = false

    private let bgDeep = Color(red: 0.039, green: 0.055, blue: 0.078)
    private let surface2 = Color(red: 0.086, green: 0.110, blue: 0.149)
    private let borderStrong = Color.white.opacity(0.16)
    private let textPrimary = Color(red: 0.902, green: 0.929, blue: 0.953)
    private let textMuted = Color(red: 0.545, green: 0.584, blue: 0.620)
    private let descriptionTone = Color(red: 0.859, green: 0.894, blue: 0.949)

    var body: some View {
        ZStack {
            bgDeep.ignoresSafeArea()
            RadialGradient(
                colors: [Color(red: 0.30, green: 0.64, blue: 1).opacity(0.08), .clear],
                center: UnitPoint(x: 0.12, y: 0.02),
                startRadius: 0,
                endRadius: 420
            )
            .ignoresSafeArea()
            RadialGradient(
                colors: [Color(red: 0.49, green: 0.36, blue: 1).opacity(0.06), .clear],
                center: UnitPoint(x: 0.95, y: 0.05),
                startRadius: 0,
                endRadius: 380
            )
            .ignoresSafeArea()
            RadialGradient(
                colors: [Color(red: 0.25, green: 0.73, blue: 0.45).opacity(0.06), .clear],
                center: UnitPoint(x: 0.5, y: 1.05),
                startRadius: 0,
                endRadius: 400
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 12)
                    mainCard
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 20)
                .frame(maxWidth: 560)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            withAnimation(.easeOut(duration: 0.45)) {
                appeared = true
            }
        }
    }

    private var mainCard: some View {
        VStack(spacing: 0) {
            hero
            Text("PowerPlan helps you compare UK energy tariffs, estimate annual costs, and explore how technology could reduce your bills over time. Enter your postcode, answer a handful of questions about your home, and get tailored recommendations using real tariff and weather data for your area.")
                .font(.body)
                .foregroundStyle(descriptionTone)
                .multilineTextAlignment(.center)
                .lineSpacing(4)
                .padding(.horizontal, 8)
                .padding(.bottom, 22)

            featureGrid

            getStartedButton
                .padding(.top, 4)

            Text("Free to use · Built for UK postcodes · No sign-up required")
                .font(.caption)
                .foregroundStyle(textMuted)
                .multilineTextAlignment(.center)
                .padding(.top, 16)

            Text("Use the gear icon to set the API base URL (production by default).")
                .font(.caption2)
                .foregroundStyle(textMuted.opacity(0.85))
                .multilineTextAlignment(.center)
                .padding(.top, 8)
                .padding(.bottom, 4)
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 28)
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(surface2)
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        RadialGradient(
                            colors: [Color(red: 0.25, green: 0.73, blue: 0.45).opacity(0.14), .clear],
                            center: .topLeading,
                            startRadius: 20,
                            endRadius: 320
                        )
                    )
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        RadialGradient(
                            colors: [Color(red: 0.30, green: 0.64, blue: 1).opacity(0.14), .clear],
                            center: .bottomTrailing,
                            startRadius: 20,
                            endRadius: 320
                        )
                    )
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [.white.opacity(0.045), .clear],
                            startPoint: .top,
                            endPoint: .center
                        )
                    )
            }
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(borderStrong, lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.5), radius: 28, y: 18)
        }
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 10)
    }

    private var hero: some View {
        VStack(spacing: 10) {
            Image("PowerPlanLogo")
                .resizable()
                .scaledToFit()
                .frame(width: 96, height: 96)
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(Color(red: 0.043, green: 0.071, blue: 0.125))
                        .shadow(color: .black.opacity(0.45), radius: 12, y: 6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .stroke(Color.white.opacity(0.06), lineWidth: 1)
                        )
                )
                .accessibilityLabel("PowerPlan logo")

            Text("PowerPlan")
                .font(.system(size: 38, weight: .heavy, design: .rounded))
                .tracking(-0.8)
                .foregroundStyle(
                    LinearGradient(
                        colors: [
                            Color(red: 0.96, green: 0.84, blue: 0.28),
                            Color(red: 0.25, green: 0.73, blue: 0.45),
                            Color(red: 0.30, green: 0.64, blue: 1),
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .minimumScaleFactor(0.75)

            Text("Smart energy planning for UK homes")
                .font(.body.weight(.medium))
                .foregroundStyle(textMuted)
                .multilineTextAlignment(.center)
        }
        .padding(.bottom, 20)
    }

    private var featureGrid: some View {
        let columns = [GridItem(.adaptive(minimum: 158), spacing: 12, alignment: .top)]
        return LazyVGrid(columns: columns, spacing: 12) {
            featureCard(
                title: "Compare tariffs",
                body: "See how the best electricity tariffs at your postcode stack up against your usage."
            )
            featureCard(
                title: "Optimise your home",
                body: "Model solar, wind, insulation and heat-pump upgrades with local weather data."
            )
            featureCard(
                title: "Long-term projection",
                body: "Explore cumulative costs over multiple years to see where investment pays back."
            )
        }
        .padding(.bottom, 22)
    }

    private func featureCard(title: String, body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(textPrimary)
            Text(body)
                .font(.caption)
                .foregroundStyle(textMuted)
                .fixedSize(horizontal: false, vertical: true)
                .lineSpacing(3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [.white.opacity(0.05), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color(red: 0.051, green: 0.067, blue: 0.086).opacity(0.55))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
        }
    }

    private var getStartedButton: some View {
        Button {
            vm.goPostcode()
        } label: {
            Text("Get started")
                .font(.headline.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    LinearGradient(
                        colors: [
                            Color(red: 0.22, green: 0.68, blue: 0.40),
                            Color(red: 0.14, green: 0.53, blue: 0.28),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .shadow(color: Color(red: 0.25, green: 0.73, blue: 0.45).opacity(0.42), radius: 18, y: 10)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.18), lineWidth: 1)
                        .blendMode(.plusLighter)
                )
        }
        .buttonStyle(.plain)
    }
}
