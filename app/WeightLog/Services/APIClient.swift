import Foundation

struct APIError: LocalizedError {
    let status: Int
    let message: String

    var errorDescription: String? { "API \(status): \(message)" }
}

/// Thin async client for the local daemon.
struct APIClient: Sendable {
    var baseURL: URL
    var session: URLSession = .shared

    static let local = APIClient(baseURL: URL(string: "http://127.0.0.1:8200")!)

    func summary() async throws -> Summary {
        try await get("api/summary")
    }

    func readings() async throws -> ReadingsResponse {
        try await get("api/readings")
    }

    func notes() async throws -> [DayNote] {
        let res: NotesResponse = try await get("api/notes")
        return res.notes
    }

    func putNote(_ note: DayNote) async throws -> DayNote {
        struct Body: Encodable { let note: String; let tags: [String] }
        return try await send("PUT", "api/notes/\(note.date)", body: Body(note: note.note, tags: note.tags))
    }

    func setStatus(readingID: Int, _ status: ReadingStatus) async throws -> Reading {
        try await send("PATCH", "api/readings/\(readingID)", body: ["status": status.rawValue] as [String: String])
    }

    func driveStatus() async throws -> DriveStatus {
        try await get("api/drive")
    }

    func putSettings(_ settings: BodySettings) async throws -> BodySettings {
        try await send("PUT", "api/settings", body: settings)
    }

    // MARK: - plumbing

    private func get<T: Decodable>(_ path: String) async throws -> T {
        try await perform(URLRequest(url: baseURL.appending(path: path)))
    }

    private func send<T: Decodable>(_ method: String, _ path: String, body: some Encodable) async throws -> T {
        var req = URLRequest(url: baseURL.appending(path: path))
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try WireCoding.encoder().encode(body)
        return try await perform(req)
    }

    private func perform<T: Decodable>(_ req: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: req)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let message = (try? JSONDecoder().decode([String: String].self, from: data))?["error"]
            throw APIError(status: status, message: message ?? "unexpected response")
        }
        return try WireCoding.decoder().decode(T.self, from: data)
    }
}
