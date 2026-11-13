import SwiftUI

/// Month heatmap of weigh-in days, colored by change, with note markers.
struct CalendarCard: View {
    @Environment(AppModel.self) private var model
    @State private var month = Date.now
    @State private var editing: String?

    private let calendar = AppLocale.calendar

    var body: some View {
        let infos = model.dayInfos
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    SectionTitle(title: "カレンダー", symbol: "calendar")
                    Spacer()
                    if let streak = model.summary?.streakDays, streak > 0 {
                        Label("\(streak) 日連続", systemImage: "flame.fill")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(Palette.trend)
                    }
                }
                HStack {
                    Button { shift(-1) } label: { Image(systemName: "chevron.left") }
                    Text(month.formatted(.dateTime.year().month(.wide).locale(AppLocale.locale)))
                        .font(.title3.weight(.semibold))
                        .frame(minWidth: 120)
                    Button { shift(1) } label: { Image(systemName: "chevron.right") }
                    Spacer()
                    Button("今月") { month = .now }
                        .disabled(calendar.isDate(month, equalTo: .now, toGranularity: .month))
                }
                .buttonStyle(.borderless)

                let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 7)
                LazyVGrid(columns: columns, spacing: 6) {
                    ForEach(CalendarLogic.weekdaySymbols(calendar: calendar), id: \.self) { symbol in
                        Text(symbol).font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(Array(CalendarLogic.monthGrid(containing: month, calendar: calendar).enumerated()),
                            id: \.offset) { _, date in
                        if let date {
                            let key = DayKey.string(date, calendar: calendar)
                            DayCell(
                                date: date,
                                info: infos[key],
                                hasNote: model.notes[key] != nil,
                                isToday: calendar.isDateInToday(date)
                            )
                            .onTapGesture { editing = key }
                            .popover(isPresented: Binding(
                                get: { editing == key },
                                set: { if !$0 { editing = nil } }
                            ), arrowEdge: .bottom) {
                                NoteEditor(dateKey: key, date: date, info: infos[key])
                                    .environment(model)
                            }
                        } else {
                            Color.clear.frame(height: 54)
                        }
                    }
                }
                HStack(spacing: 14) {
                    swatch(Palette.down, "前回より減")
                    swatch(Palette.up, "前回より増")
                    Label("メモあり", systemImage: "circle.fill").foregroundStyle(Palette.weight)
                    Spacer()
                    Text("日付をクリックしてメモ")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .labelStyle(.titleAndIcon)
                .imageScale(.small)
            }
        }
    }

    private func shift(_ months: Int) {
        if let d = calendar.date(byAdding: .month, value: months, to: month) { month = d }
    }

    private func swatch(_ color: Color, _ title: String) -> some View {
        Label { Text(title) } icon: { RoundedRectangle(cornerRadius: 3).fill(color.opacity(0.5)).frame(width: 10, height: 10) }
    }
}

private struct DayCell: View {
    let date: Date
    let info: DayInfo?
    let hasNote: Bool
    let isToday: Bool

    var body: some View {
        VStack(spacing: 2) {
            HStack(spacing: 3) {
                Text(date.formatted(.dateTime.day().locale(AppLocale.locale)))
                    .font(.caption.weight(isToday ? .bold : .regular))
                if hasNote {
                    Circle().fill(Palette.weight).frame(width: 5, height: 5)
                }
            }
            Text(info.map { Format.kg($0.weightKg, digits: 1) } ?? " ")
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, minHeight: 54)
        .background(fill, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(isToday ? Palette.weight : .clear, lineWidth: 1.5)
        )
        .contentShape(Rectangle())
        .help(help)
    }

    private var fill: Color {
        guard let info else { return Color.secondary.opacity(0.06) }
        guard let delta = info.delta else { return Palette.weight.opacity(0.14) }
        let strength = min(abs(delta) / 0.8, 1) * 0.45 + 0.12
        return (delta <= 0 ? Palette.down : Palette.up).opacity(strength)
    }

    private var help: String {
        guard let info else { return "" }
        return "\(Format.kg(info.weightKg)) kg" + (info.delta.map { "（\(Format.signed($0))）" } ?? "")
    }
}

/// Popover editor for a day's note and tags.
struct NoteEditor: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let dateKey: String
    let date: Date
    let info: DayInfo?

    @State private var note = DayNote(date: "", note: "", tags: [])
    @State private var customTag = ""

    static let presets = ["飲み会", "外食", "自炊", "運動", "筋トレ", "よく寝た", "寝不足", "体調不良", "旅行", "チートデイ"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(Format.day(date)).font(.headline)
                Spacer()
                if let info {
                    Text("\(Format.kg(info.weightKg)) kg").monospacedDigit()
                    if let d = info.delta {
                        Text(Format.signed(d)).foregroundStyle(Palette.color(for: Trend(d))).monospacedDigit()
                    }
                }
            }
            TextField("メモ（食べたもの、体調など）", text: $note.note, axis: .vertical)
                .lineLimit(3...6)
                .textFieldStyle(.roundedBorder)

            FlowTags(tags: Array(Set(Self.presets + note.tags)).sorted { order($0) < order($1) },
                     selected: Set(note.tags)) { tag in
                if let i = note.tags.firstIndex(of: tag) { note.tags.remove(at: i) } else { note.tags.append(tag) }
            }

            HStack {
                TextField("タグを追加", text: $customTag)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(addCustomTag)
                Button("追加", action: addCustomTag).disabled(customTag.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            HStack {
                Spacer()
                Button("キャンセル") { dismiss() }
                Button("保存") {
                    Task {
                        await model.save(note)
                        dismiss()
                    }
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 380)
        .onAppear { note = model.note(for: dateKey) }
    }

    private func order(_ tag: String) -> Int { Self.presets.firstIndex(of: tag) ?? Self.presets.count }

    private func addCustomTag() {
        let tag = customTag.trimmingCharacters(in: .whitespaces)
        guard !tag.isEmpty else { return }
        if !note.tags.contains(tag) { note.tags.append(tag) }
        customTag = ""
    }
}

private struct FlowTags: View {
    let tags: [String]
    let selected: Set<String>
    let toggle: (String) -> Void

    var body: some View {
        let columns = [GridItem(.adaptive(minimum: 80), spacing: 6)]
        LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
            ForEach(tags, id: \.self) { tag in
                let on = selected.contains(tag)
                Button { toggle(tag) } label: {
                    Text(tag)
                        .font(.callout)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 5)
                        .background(on ? Palette.weight.opacity(0.9) : Color.secondary.opacity(0.1), in: Capsule())
                        .foregroundStyle(on ? .white : .primary)
                }
                .buttonStyle(.plain)
            }
        }
    }
}
