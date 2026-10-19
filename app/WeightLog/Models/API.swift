import Foundation

/// Wire types for the s200 daemon API (`s200/web.py`). Keys are snake_case on the wire.

enum ReadingStatus: String, Codable, Sendable {
    case ok, outlier, merged

    var isIncluded: Bool { self == .ok }
}

struct Reading: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    let ts: Int
    let profileId: Int
    let weightKg: Double
    let status: ReadingStatus
    let reason: String?
    let manual: Bool
    /// Present on `/api/readings`; absent on the summary's `latest`.
    let trendKg: Double?

    var date: Date { Date(timeIntervalSince1970: TimeInterval(ts)) }
}

struct Milestone: Codable, Hashable, Sendable {
    let kind: String
    let title: String
}

struct Summary: Codable, Equatable, Sendable {
    let latest: Reading?
    let count: Int
    let goalKg: Double?
    let heightCm: Double?
    let startKg: Double?
    let trendKg: Double?
    let deltaPrev: Double?
    let deltaStart: Double?
    let deltaTrendWeek: Double?
    let paceKgPerWeek: Double?
    let etaTs: Int?
    let bmi: Double?
    let lowestKg: Double?
    let streakDays: Int
    let milestones: [Milestone]
    let comment: String

    var etaDate: Date? { etaTs.map { Date(timeIntervalSince1970: TimeInterval($0)) } }
}

struct DayNote: Codable, Equatable, Sendable {
    var date: String
    var note: String
    var tags: [String]

    var isEmpty: Bool { note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && tags.isEmpty }
}

struct BodySettings: Codable, Equatable, Sendable {
    var heightCm: Double?
    var goalKg: Double?
    var startKg: Double?
}

struct ReadingsResponse: Codable, Sendable {
    let readings: [Reading]
    let settings: BodySettings
}

struct NotesResponse: Codable, Sendable {
    let notes: [DayNote]
}

struct ReadingEvent: Codable, Sendable {
    let reading: Reading
    let summary: Summary
}

struct ChangedEvent: Codable, Sendable {
    let summary: Summary
}

enum WireCoding {
    static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    static func encoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }
}
