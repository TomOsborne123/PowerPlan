import QuartzCore
import SwiftUI
import UIKit

// MARK: - Core Animation globe (UIKit + CALayer — always available on iOS)

/// Scrape “globe” using **SF Symbol + CABasicAnimation** on `CALayer`.
/// This is Core Animation (same subsystem as all system UI); it avoids SceneKit layout quirks in `Form`/`List` rows.
private final class SpinningGlobeUIView: UIView {
    private let globeImageView = UIImageView()
    private var shouldSpin = false

    private static let spinKey = "powerplan.globe.spin"

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .clear
        clipsToBounds = true

        globeImageView.translatesAutoresizingMaskIntoConstraints = false
        addSubview(globeImageView)
        NSLayoutConstraint.activate([
            globeImageView.centerXAnchor.constraint(equalTo: centerXAnchor),
            globeImageView.centerYAnchor.constraint(equalTo: centerYAnchor),
            globeImageView.widthAnchor.constraint(equalTo: widthAnchor, multiplier: 0.78),
            globeImageView.heightAnchor.constraint(equalTo: globeImageView.widthAnchor),
        ])

        let cfg = UIImage.SymbolConfiguration(pointSize: 96, weight: .medium, scale: .large)
        globeImageView.image = UIImage(systemName: "globe.europe.africa.fill", withConfiguration: cfg)
        globeImageView.tintColor = UIColor(red: 0.32, green: 0.78, blue: 0.58, alpha: 1)
        globeImageView.contentMode = .scaleAspectFit
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setSpinning(_ spinning: Bool) {
        shouldSpin = spinning
        applySpinIfPossible()
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        applySpinIfPossible()
    }

    private func applySpinIfPossible() {
        globeImageView.layer.removeAnimation(forKey: Self.spinKey)
        guard shouldSpin, bounds.width > 8, bounds.height > 8 else { return }

        let anim = CABasicAnimation(keyPath: "transform.rotation.z")
        anim.fromValue = 0
        anim.toValue = CGFloat.pi * 2
        anim.duration = 14
        anim.repeatCount = .infinity
        anim.isRemovedOnCompletion = false
        anim.timingFunction = CAMediaTimingFunction(name: .linear)
        globeImageView.layer.add(anim, forKey: Self.spinKey)
    }
}

private struct CoreAnimationGlobeRepresentable: UIViewRepresentable {
    var spinning: Bool

    func makeUIView(context: Context) -> SpinningGlobeUIView {
        let v = SpinningGlobeUIView()
        v.setSpinning(spinning)
        return v
    }

    func updateUIView(_ uiView: SpinningGlobeUIView, context: Context) {
        uiView.setSpinning(spinning)
    }
}

// MARK: - Public SwiftUI wrapper

struct ScrapeGlobeView: View {
    var latitude: Double?
    var longitude: Double?
    var spinning: Bool

    private var showPin: Bool {
        guard let la = latitude, let lo = longitude else { return false }
        return la.isFinite && lo.isFinite && abs(la) <= 90 && abs(lo) <= 180
    }

    var body: some View {
        ZStack {
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 0.08, green: 0.12, blue: 0.22),
                            Color(red: 0.02, green: 0.03, blue: 0.06),
                        ],
                        center: .center,
                        startRadius: 4,
                        endRadius: 120
                    )
                )

            CoreAnimationGlobeRepresentable(spinning: spinning)

            if showPin {
                ZStack {
                    Circle()
                        .stroke(Color.orange.opacity(0.45), lineWidth: 2)
                        .frame(width: 22, height: 22)
                    Circle()
                        .fill(Color.orange)
                        .frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Color.white, lineWidth: 1.2))
                }
                .offset(y: -38)
                .allowsHitTesting(false)
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .overlay(
            Circle()
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.28), .white.opacity(0.06)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1.5
                )
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spinning ? "Animated globe, fetching tariffs" : "Globe preview")
    }
}

// MARK: - Banner

/// Globe + progress strip for the preferences screen while a tariff scrape runs in the background.
struct ScrapeInProgressBanner: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        VStack(spacing: 14) {
            ScrapeGlobeView(
                latitude: vm.latitude,
                longitude: vm.longitude,
                spinning: true
            )
            .frame(width: 200, height: 200)

            Text("Fetching tariff data…")
                .font(.headline)

            VStack(alignment: .leading, spacing: 6) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color(uiColor: .tertiarySystemFill))
                        Capsule()
                            .fill(Color.green)
                            .frame(width: max(4, geo.size.width * min(1, vm.scrapeProgressFraction)))
                    }
                }
                .frame(height: 10)
                HStack {
                    Text("Progress (approximate)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("\(Int(round(vm.scrapeProgressFraction * 100)))%")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            Text(vm.scrapeStatusText)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text("You can fill in the questions below while we wait — “Run recommendation” stays disabled until tariffs arrive.")
                .font(.footnote)
                .foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 8)
    }
}
