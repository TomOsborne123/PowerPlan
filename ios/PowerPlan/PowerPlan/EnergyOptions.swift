import Foundation

/// Aligned with `frontend/src/optimiserConstants.js` for API payloads.
enum EnergyOptions {
    static let heatingShares: [(label: String, value: Double)] = [
        ("Low (25%)", 0.25),
        ("Moderate (40%)", 0.4),
        ("Half (50%)", 0.5),
        ("Typical (60%)", 0.6),
        ("High (75%)", 0.75),
    ]

    static let insulation: [(label: String, value: Double)] = [
        ("No insulation change", 0),
        ("Basic (1.0)", 1.0),
        ("Typical UK (2.5)", 2.5),
        ("Good (4.0)", 4.0),
        ("Strong (6.0)", 6.0),
    ]

    enum HeatPumpTier: String, CaseIterable, Identifiable {
        case none, budget, mid, premium
        var id: String { rawValue }
        var label: String {
            switch self {
            case .none: return "No heat pump"
            case .budget: return "Budget ASHP (COP ~2.5)"
            case .mid: return "Mid ASHP (COP ~3.0)"
            case .premium: return "Premium ASHP (COP ~3.5)"
            }
        }
        var cop: Double {
            switch self {
            case .none: return 1.0
            case .budget: return 2.5
            case .mid: return 3.0
            case .premium: return 3.5
            }
        }
    }

    enum KitTier: String, CaseIterable, Identifiable {
        case none, budget, mid, premium
        var id: String { rawValue }
        var label: String {
            switch self {
            case .none: return "None"
            case .budget: return "Budget"
            case .mid: return "Mid"
            case .premium: return "Premium"
            }
        }
    }

    /// Projection-only scenario sizes (kW / kWh), aligned with `PROJECTION_SCENARIO_*` in JS.
    static func projectionSolarKw(tier: KitTier) -> Double {
        switch tier {
        case .none, .budget: return 3
        case .mid: return 4.5
        case .premium: return 6
        }
    }

    static func projectionWindKw(tier: KitTier) -> Double {
        switch tier {
        case .none, .budget: return 1
        case .mid: return 2
        case .premium: return 3.5
        }
    }

    static func projectionBatteryKwh(tier: KitTier) -> Double {
        switch tier {
        case .none: return 0
        case .budget: return 5
        case .mid: return 8
        case .premium: return 12
        }
    }
}
