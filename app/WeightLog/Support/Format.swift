import Foundation

/// The UI is Japanese, so dates are too, whatever the system language is.
enum AppLocale {
    static let locale = Locale(identifier: "ja_JP")

    static var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = locale
        return calendar
    }
}

enum Format {
    static func kg(_ value: Double?, digits: Int = 2) -> String {
        guard let value else { return "–" }
        return value.formatted(.number.precision(.fractionLength(digits)))
    }

    /// "+0.20" / "-0.35" / "±0.00"
    static func signed(_ value: Double?, digits: Int = 2) -> String {
        guard let value else { return "–" }
        let rounded = (value * pow(10, Double(digits))).rounded() / pow(10, Double(digits))
        if rounded == 0 { return "±" + kg(0, digits: digits) }
        return (rounded > 0 ? "+" : "-") + kg(abs(rounded), digits: digits)
    }

    static func dateTime(_ date: Date) -> String {
        date.formatted(.dateTime.month().day().weekday(.abbreviated).hour().minute()
            .locale(AppLocale.locale))
    }

    static func day(_ date: Date) -> String {
        date.formatted(.dateTime.year().month().day().locale(AppLocale.locale))
    }

    static func relative(_ date: Date, now: Date = .now) -> String {
        date.formatted(.relative(presentation: .named).locale(AppLocale.locale))
    }
}

enum Trend {
    case down, flat, up

    /// Classify a change in kg; within ±threshold counts as flat.
    init(_ delta: Double?, threshold: Double = 0.05) {
        guard let delta, abs(delta) > threshold else { self = .flat; return }
        self = delta < 0 ? .down : .up
    }

    var symbol: String {
        switch self {
        case .down: "arrow.down.right"
        case .flat: "arrow.right"
        case .up: "arrow.up.right"
        }
    }
}

/// Local calendar day key matching the daemon's `YYYY-MM-DD` notes keys.
enum DayKey {
    static func string(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }
}
