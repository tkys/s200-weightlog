import Foundation

struct DayInfo: Equatable {
    /// Last included weigh-in of the day.
    let weightKg: Double
    /// Change vs. the previous day that has a weigh-in.
    let delta: Double?
}

enum CalendarLogic {
    /// Per-day weight and change, keyed by `DayKey`. Excluded readings are ignored.
    static func dayInfos(_ readings: [Reading], calendar: Calendar = .current) -> [String: DayInfo] {
        var lastOfDay: [(key: String, weight: Double)] = []
        for r in readings where r.status.isIncluded {
            let key = DayKey.string(r.date, calendar: calendar)
            if lastOfDay.last?.key == key {
                lastOfDay[lastOfDay.count - 1].weight = r.weightKg
            } else {
                lastOfDay.append((key, r.weightKg))
            }
        }
        var out: [String: DayInfo] = [:]
        for (i, day) in lastOfDay.enumerated() {
            let delta = i > 0 ? day.weight - lastOfDay[i - 1].weight : nil
            out[day.key] = DayInfo(weightKg: day.weight, delta: delta)
        }
        return out
    }

    /// Dates of a month laid out in week rows; nil pads the leading/trailing cells.
    static func monthGrid(containing date: Date, calendar: Calendar = .current) -> [Date?] {
        guard let interval = calendar.dateInterval(of: .month, for: date),
              let days = calendar.range(of: .day, in: .month, for: date) else { return [] }
        let firstWeekday = calendar.component(.weekday, from: interval.start)
        let leading = (firstWeekday - calendar.firstWeekday + 7) % 7
        var cells: [Date?] = Array(repeating: nil, count: leading)
        for day in days {
            cells.append(calendar.date(byAdding: .day, value: day - 1, to: interval.start))
        }
        while cells.count % 7 != 0 { cells.append(nil) }
        return cells
    }

    static func weekdaySymbols(calendar: Calendar = .current) -> [String] {
        let symbols = calendar.veryShortStandaloneWeekdaySymbols
        let start = calendar.firstWeekday - 1
        return Array(symbols[start...] + symbols[..<start])
    }
}
