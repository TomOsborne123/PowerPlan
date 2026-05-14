import Foundation

/// Mirrors `frontend/src/postcodeUtils.js` so validation matches the web app and API.
enum PostcodeNormalizer {
    static func normalize(_ raw: String) -> String {
        raw.uppercased().replacingOccurrences(of: "\\s+", with: "", options: .regularExpression)
    }

    static func isOutwardOnly(_ norm: String) -> Bool {
        let re = try! NSRegularExpression(pattern: "^[A-Z]{1,2}\\d{1,2}[A-Z]?$")
        return re.firstMatch(in: norm, range: NSRange(norm.startIndex..., in: norm)) != nil
    }

    static func isFullPostcode(_ norm: String) -> Bool {
        let re = try! NSRegularExpression(pattern: "^[A-Z]{1,2}\\d{1,2}[A-Z]?\\d[A-Z]{2}$")
        return re.firstMatch(in: norm, range: NSRange(norm.startIndex..., in: norm)) != nil
    }

    static func isValidForApp(_ norm: String) -> Bool {
        !norm.isEmpty && (isOutwardOnly(norm) || isFullPostcode(norm))
    }
}
