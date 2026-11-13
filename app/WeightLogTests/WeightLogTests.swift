import Foundation
import Testing
@testable import WeightLog

// Real `/api/summary` payload from the daemon (2026-10-19).
let summaryJSON = """
{"latest": {"id": 2, "ts": 1792402770, "profile_id": 1, "weight_kg": 74.6, "status": "ok",
 "reason": null, "manual": false}, "count": 2, "goal_kg": 65.0, "height_cm": 170,
 "start_kg": 74.4, "trend_kg": 74.4000978927014, "delta_prev": 0.19999999999998863,
 "delta_start": 0.19999999999998863, "delta_trend_week": null, "pace_kg_per_week": null,
 "eta_ts": null, "bmi": 25.813148788927336, "lowest_kg": 74.4, "streak_days": 1,
 "milestones": [{"kind": "new_low", "title": "最安値を更新"}],
 "comment": "前回から +0.20 kg。もう数日記録するとトレンドが見えてきます"}
"""

@Suite struct DecodingTests {
    @Test func decodesSummary() throws {
        let s = try WireCoding.decoder().decode(Summary.self, from: Data(summaryJSON.utf8))
        #expect(s.latest?.weightKg == 74.6)
        #expect(s.latest?.status == .ok)
        #expect(s.latest?.trendKg == nil)
        #expect(s.heightCm == 170)
        #expect(s.paceKgPerWeek == nil)
        #expect(s.milestones.first?.kind == "new_low")
        #expect(s.streakDays == 1)
    }

    @Test func decodesReadingsWithTrendAndStatus() throws {
        let json = """
        {"readings": [{"id": 1, "ts": 100, "profile_id": 1, "weight_kg": 74.4, "status": "outlier",
          "reason": "x", "manual": true, "trend_kg": 74.0}],
         "settings": {"height_cm": 170, "goal_kg": null, "start_kg": null}}
        """
        let r = try WireCoding.decoder().decode(ReadingsResponse.self, from: Data(json.utf8))
        #expect(r.readings[0].status == .outlier)
        #expect(r.readings[0].manual)
        #expect(r.readings[0].trendKg == 74.0)
        #expect(r.settings.goalKg == nil)
    }

    @Test func decodesDriveStatus() throws {
        let decoder = WireCoding.decoder()
        let off = try decoder.decode(DriveStatus.self, from: Data(#"{"enabled": false}"#.utf8))
        #expect(off.line == .off)

        let ok = try decoder.decode(DriveStatus.self, from: Data(
            #"{"enabled": true, "last_success": 1793918715, "last_error": null}"#.utf8))
        #expect(ok.line == .synced(Date(timeIntervalSince1970: 1_793_918_715)))

        let failing = try decoder.decode(DriveStatus.self, from: Data(
            #"{"enabled": true, "last_success": 1793918715, "last_error": "500"}"#.utf8))
        #expect(failing.line == .error("500"))

        let fresh = try decoder.decode(DriveStatus.self, from: Data(#"{"enabled": true}"#.utf8))
        #expect(fresh.line == .waiting)
    }

    @Test func encodesSettingsSnakeCase() throws {
        let data = try WireCoding.encoder().encode(BodySettings(heightCm: 172, goalKg: 68))
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Double]
        #expect(obj == ["height_cm": 172, "goal_kg": 68])
    }
}

@Suite struct SSEParserTests {
    @Test func parsesEventThenData() {
        var p = SSEParser()
        #expect(p.feed(": connected") == nil)
        #expect(p.feed("event: reading") == nil)
        #expect(p.feed("data: {\"a\":1}") == ServerSentEvent(event: "reading", data: "{\"a\":1}"))
    }

    @Test func dataWithoutEventIsMessage() {
        var p = SSEParser()
        #expect(p.feed("data:x") == ServerSentEvent(event: "message", data: "x"))
    }

    @Test func eventResetsAfterDispatchAndBlankLine() {
        var p = SSEParser()
        _ = p.feed("event: changed")
        _ = p.feed("data: 1")
        #expect(p.feed("data: 2")?.event == "message")
        _ = p.feed("event: reading")
        _ = p.feed("")
        #expect(p.feed("data: 3")?.event == "message")
    }

    @Test func decodesStreamEvents() {
        let changed = ServerSentEvent(event: "changed", data: "{\"summary\": \(summaryJSON)}")
        guard case .changed(let s) = EventStream.decode(changed) else {
            Issue.record("expected changed event")
            return
        }
        #expect(s.count == 2)
        #expect(EventStream.decode(ServerSentEvent(event: "changed", data: "nope")) == nil)
        #expect(EventStream.decode(ServerSentEvent(event: "other", data: "{}")) == nil)
    }
}

@Suite struct FormatTests {
    @Test func signedFormatting() {
        #expect(Format.signed(0.2) == "+0.20")
        #expect(Format.signed(-0.354) == "-0.35")
        #expect(Format.signed(0.001) == "±0.00")
        #expect(Format.signed(nil) == "–")
        #expect(Format.kg(74.6) == "74.60")
        #expect(Format.kg(74.6, digits: 1) == "74.6")
    }

    @Test func datesAreJapaneseRegardlessOfSystemLanguage() {
        var c = DateComponents()
        (c.year, c.month, c.day, c.hour, c.minute) = (2026, 11, 13, 7, 32)
        let date = AppLocale.calendar.date(from: c)!
        #expect(Format.dateTime(date).contains("11月13日"))
        #expect(Format.dateTime(date).contains("(金)"))
        #expect(Format.day(date) == "2026年11月13日")
        #expect(CalendarLogic.weekdaySymbols() == ["日", "月", "火", "水", "木", "金", "土"])
    }

    @Test func trendClassification() {
        #expect(Trend(-0.3) == .down)
        #expect(Trend(0.3) == .up)
        #expect(Trend(0.02) == .flat)
        #expect(Trend(nil) == .flat)
    }
}

@Suite struct CalendarLogicTests {
    var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "Asia/Tokyo")!
        c.firstWeekday = 1
        return c
    }

    func reading(_ id: Int, _ date: String, _ kg: Double, _ status: ReadingStatus = .ok) -> Reading {
        let f = ISO8601DateFormatter()
        let ts = Int(f.date(from: date)!.timeIntervalSince1970)
        return Reading(id: id, ts: ts, profileId: 1, weightKg: kg, status: status, reason: nil, manual: false, trendKg: nil)
    }

    @Test func dayInfosUseLastIncludedReadingPerDay() {
        let infos = CalendarLogic.dayInfos([
            reading(1, "2026-10-18T07:00:00+09:00", 75.0),
            reading(2, "2026-10-19T07:00:00+09:00", 74.8),
            reading(3, "2026-10-19T21:00:00+09:00", 74.6),
            reading(4, "2026-10-20T07:00:00+09:00", 30.0, .outlier),
            reading(5, "2026-10-21T07:00:00+09:00", 74.9),
        ], calendar: calendar)
        #expect(infos["2026-10-18"] == DayInfo(weightKg: 75.0, delta: nil))
        #expect(infos["2026-10-19"]?.weightKg == 74.6)
        #expect(abs((infos["2026-10-19"]?.delta ?? 0) - -0.4) < 1e-9)
        #expect(infos["2026-10-20"] == nil)
        #expect(abs((infos["2026-10-21"]?.delta ?? 0) - 0.3) < 1e-9)
    }

    @Test func dayKeyUsesLocalCalendar() {
        let late = ISO8601DateFormatter().date(from: "2026-10-19T23:30:00+09:00")!
        #expect(DayKey.string(late, calendar: calendar) == "2026-10-19")
    }

    @Test func monthGridPadsToWeeks() {
        // October 2026 starts on a Thursday.
        let oct = ISO8601DateFormatter().date(from: "2026-10-15T12:00:00+09:00")!
        let grid = CalendarLogic.monthGrid(containing: oct, calendar: calendar)
        #expect(grid.count % 7 == 0)
        #expect(grid.prefix(4).allSatisfy { $0 == nil })
        #expect(grid[4].map { calendar.component(.day, from: $0) } == 1)
        #expect(grid.compactMap { $0 }.count == 31)
    }

    @Test func weekdaySymbolsStartAtFirstWeekday() {
        var c = calendar
        c.locale = Locale(identifier: "ja_JP")
        c.firstWeekday = 2
        #expect(CalendarLogic.weekdaySymbols(calendar: c).first == "月")
    }
}
