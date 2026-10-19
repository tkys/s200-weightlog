import AppKit
import Foundation
import Observation

/// A freshly received weigh-in, shown as the reaction banner.
struct Reaction: Identifiable, Equatable {
    let id = UUID()
    let reading: Reading
    let summary: Summary
    let previousKg: Double?
}

struct Celebration: Identifiable, Equatable {
    let id = UUID()
    let milestones: [Milestone]
}

@MainActor
@Observable
final class AppModel {
    var summary: Summary?
    var readings: [Reading] = []
    var notes: [String: DayNote] = [:]
    var settings = BodySettings()
    var isConnected = false
    var reaction: Reaction?
    var celebration: Celebration?
    var errorMessage: String?

    let api: APIClient
    private var started = false

    init(api: APIClient = .local) {
        self.api = api
    }

    var dayInfos: [String: DayInfo] { CalendarLogic.dayInfos(readings) }

    /// Runs for the app's lifetime: initial load, then live updates.
    func start() async {
        guard !started else { return }
        started = true
        await Notifier.requestAuthorization()
        await reload()
        for await event in EventStream(api: api).events() {
            await handle(event)
        }
    }

    func reload() async {
        do {
            async let s = api.summary()
            async let r = api.readings()
            async let n = api.notes()
            let (summary, readings, notes) = try await (s, r, n)
            self.summary = summary
            self.readings = readings.readings
            self.settings = readings.settings
            self.notes = Dictionary(uniqueKeysWithValues: notes.map { ($0.date, $0) })
            errorMessage = nil
        } catch {
            errorMessage = "常駐プログラムに接続できません（\(error.localizedDescription)）"
        }
    }

    private func handle(_ event: StreamEvent) async {
        switch event {
        case .connected:
            isConnected = true
            await reload()  // catch up on anything missed while disconnected
        case .disconnected:
            isConnected = false
        case .changed(let summary):
            self.summary = summary
            await reloadReadings()
        case .reading(let event):
            let previous = readings.last(where: { $0.status.isIncluded })?.weightKg
            summary = event.summary
            await reloadReadings()
            react(to: event, previousKg: previous)
        }
    }

    private func react(to event: ReadingEvent, previousKg: Double?) {
        reaction = Reaction(reading: event.reading, summary: event.summary, previousKg: previousKg)
        if !event.summary.milestones.isEmpty {
            celebration = Celebration(milestones: event.summary.milestones)
        }
        if !NSApp.isActive {
            let title = event.reading.status.isIncluded
                ? "\(Format.kg(event.reading.weightKg)) kg（前回比 \(Format.signed(event.summary.deltaPrev))）"
                : "\(Format.kg(event.reading.weightKg)) kg は除外しました"
            Notifier.post(title: title, body: event.summary.comment)
        }
    }

    private func reloadReadings() async {
        if let res = try? await api.readings() {
            readings = res.readings
            settings = res.settings
        }
    }

    // MARK: - user actions

    func toggleExcluded(_ reading: Reading) async {
        let next: ReadingStatus = reading.status.isIncluded ? .outlier : .ok
        do {
            _ = try await api.setStatus(readingID: reading.id, next)
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func note(for key: String) -> DayNote {
        notes[key] ?? DayNote(date: key, note: "", tags: [])
    }

    func save(_ note: DayNote) async {
        do {
            let saved = try await api.putNote(note)
            notes[saved.date] = saved.isEmpty ? nil : saved
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save(_ settings: BodySettings) async {
        do {
            self.settings = try await api.putSettings(settings)
            summary = try await api.summary()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
