import Foundation

enum PowerPlanAPIError: LocalizedError {
    case invalidURL
    case http(Int, String?)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid API URL"
        case .http(let code, let body): return PowerPlanAPIError.userFacingHttpMessage(code: code, body: body)
        case .decoding(let e): return "Could not read response: \(e.localizedDescription)"
        }
    }

    /// Avoid dumping full HTML error pages into alerts.
    private static func userFacingHttpMessage(code: Int, body: String?) -> String {
        guard let body, !body.isEmpty else { return "HTTP \(code)" }
        let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
        // Avoid `localizedCaseContains` — not available on all deployment targets / Swift toolchains.
        let looksLikeHtml = trimmed.hasPrefix("<!") || trimmed.lowercased().contains("<html")
        if looksLikeHtml {
            if code == 404 {
                return """
                HTTP 404 — the API path was not found on this server.

                Set the API base URL (gear) to the host that runs Flask (e.g. https://www.powerplan.site with no extra path), not a static-only site.
                """
            }
            return "HTTP \(code) — the server returned an HTML error page instead of JSON. Check the API base URL."
        }
        if trimmed.count > 400 { return "HTTP \(code): \(String(trimmed.prefix(400)))…" }
        return "HTTP \(code): \(trimmed)"
    }
}

actor PowerPlanClient {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    private func request(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem]? = nil,
        jsonBody: [String: Any]? = nil
    ) async throws -> (Data, HTTPURLResponse) {
        guard var components = URLComponents(url: APIConfiguration.baseURL, resolvingAgainstBaseURL: false) else {
            throw PowerPlanAPIError.invalidURL
        }
        // Path only — never put ?query= here; URLComponents would treat "?" as part of the path segment.
        var p = path.hasPrefix("/") ? path : "/\(path)"
        if let q = p.firstIndex(of: "?") {
            p = String(p[..<q])
        }
        components.path = p
        if let queryItems, !queryItems.isEmpty {
            var existing = components.queryItems ?? []
            existing.append(contentsOf: queryItems)
            components.queryItems = existing
        }
        guard let url = components.url else { throw PowerPlanAPIError.invalidURL }

        var req = URLRequest(url: url)
        req.httpMethod = method
        if let jsonBody {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: jsonBody)
        }
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw PowerPlanAPIError.http(-1, nil)
        }
        return (data, http)
    }

    func fetchScrapeResults(postcode: String) async throws -> ScrapeResultsResponse {
        let norm = PostcodeNormalizer.normalize(postcode)
        let (data, http) = try await request(
            path: "/api/scrape-results",
            queryItems: [URLQueryItem(name: "postcode", value: norm)]
        )
        guard (200 ... 299).contains(http.statusCode) else {
            throw PowerPlanAPIError.http(http.statusCode, String(data: data, encoding: .utf8))
        }
        do {
            return try JSONDecoder().decode(ScrapeResultsResponse.self, from: data)
        } catch {
            throw PowerPlanAPIError.decoding(error)
        }
    }

    func runScrape(
        postcode: String,
        homeOrBusiness: String,
        hasEv: String,
        addressName: String,
        addressIndex: Int = 0
    ) async throws {
        let norm = PostcodeNormalizer.normalize(postcode)
        let body: [String: Any] = [
            "postcode": norm,
            "home_or_business": homeOrBusiness,
            "has_ev": hasEv,
            "address_name": addressName,
            "address_index": addressIndex,
        ]
        let (data, http) = try await request(path: "/api/run-scrape", method: "POST", jsonBody: body)
        if http.statusCode == 409 {
            throw PowerPlanAPIError.http(409, "Scrape already running")
        }
        guard (200 ... 299).contains(http.statusCode) else {
            let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw PowerPlanAPIError.http(http.statusCode, msg ?? String(data: data, encoding: .utf8))
        }
    }

    func scrapeStatus(postcode: String) async throws -> ScrapeStatusResponse {
        let norm = PostcodeNormalizer.normalize(postcode)
        let (data, http) = try await request(
            path: "/api/scrape-status",
            queryItems: [URLQueryItem(name: "postcode", value: norm)]
        )
        guard (200 ... 299).contains(http.statusCode) else {
            throw PowerPlanAPIError.http(http.statusCode, String(data: data, encoding: .utf8))
        }
        return try JSONDecoder().decode(ScrapeStatusResponse.self, from: data)
    }

    func lookupPostcode(_ postcode: String) async throws -> PostcodeLookupResponse {
        let norm = PostcodeNormalizer.normalize(postcode)
        let (data, http) = try await request(path: "/api/postcode", method: "POST", jsonBody: ["postcode": norm])
        guard (200 ... 299).contains(http.statusCode) else {
            let err = try? JSONDecoder().decode(PostcodeLookupResponse.self, from: data)
            throw PowerPlanAPIError.http(http.statusCode, err?.error ?? String(data: data, encoding: .utf8))
        }
        return try JSONDecoder().decode(PostcodeLookupResponse.self, from: data)
    }

    func exportPriceReference() async throws -> ExportPriceResponse {
        let (data, _) = try await request(path: "/api/export-price")
        return try JSONDecoder().decode(ExportPriceResponse.self, from: data)
    }

    func recommend(payload: [String: Any]) async throws -> RecommendResponse {
        let (data, http) = try await request(path: "/api/recommend", method: "POST", jsonBody: payload)
        guard (200 ... 299).contains(http.statusCode) else {
            let err = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw PowerPlanAPIError.http(http.statusCode, err ?? String(data: data, encoding: .utf8))
        }
        do {
            return try JSONDecoder().decode(RecommendResponse.self, from: data)
        } catch {
            throw PowerPlanAPIError.decoding(error)
        }
    }

    func costProjection(payload: [String: Any]) async throws -> CostProjectionResponse {
        let (data, http) = try await request(path: "/api/cost-projection", method: "POST", jsonBody: payload)
        guard (200 ... 299).contains(http.statusCode) else {
            let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw PowerPlanAPIError.http(http.statusCode, msg)
        }
        do {
            return try JSONDecoder().decode(CostProjectionResponse.self, from: data)
        } catch {
            throw PowerPlanAPIError.decoding(error)
        }
    }
}
