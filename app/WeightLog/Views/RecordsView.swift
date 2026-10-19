import SwiftUI

/// All weigh-ins, newest first, with exclude / restore.
struct RecordsView: View {
    @Environment(AppModel.self) private var model
    @State private var showExcluded = true

    private struct Row: Identifiable {
        let reading: Reading
        let delta: Double?
        var id: Int { reading.id }
    }

    private var rows: [Row] {
        var out: [Row] = []
        var previous: Reading?
        for r in model.readings {
            let delta = r.status.isIncluded ? previous.map { r.weightKg - $0.weightKg } : nil
            if r.status.isIncluded { previous = r }
            if showExcluded || r.status.isIncluded { out.append(Row(reading: r, delta: delta)) }
        }
        return out.reversed()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("\(model.readings.count) 件")
                    .foregroundStyle(.secondary)
                Spacer()
                Toggle("除外した記録も表示", isOn: $showExcluded)
                    .toggleStyle(.switch)
                    .controlSize(.small)
            }
            Table(rows) {
                TableColumn("日時") { row in
                    Text(Format.dateTime(row.reading.date))
                }
                .width(min: 150, ideal: 170)
                TableColumn("体重") { row in
                    Text("\(Format.kg(row.reading.weightKg)) kg")
                        .monospacedDigit()
                        .fontWeight(.semibold)
                        .strikethrough(!row.reading.status.isIncluded)
                        .foregroundStyle(row.reading.status.isIncluded ? .primary : .secondary)
                }
                .width(90)
                TableColumn("前回比") { row in
                    Text(row.delta.map { Format.signed($0) } ?? "")
                        .monospacedDigit()
                        .foregroundStyle(Palette.color(for: Trend(row.delta)))
                }
                .width(70)
                TableColumn("トレンド") { row in
                    Text(row.reading.trendKg.map { Format.kg($0) } ?? "")
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
                .width(70)
                TableColumn("状態") { row in
                    HStack(spacing: 6) {
                        StatusBadge(reading: row.reading)
                        if let reason = row.reading.reason, !row.reading.status.isIncluded {
                            Text(reason).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
                TableColumn("") { row in
                    Button(row.reading.status.isIncluded ? "除外" : "戻す") {
                        Task { await model.toggleExcluded(row.reading) }
                    }
                    .controlSize(.small)
                }
                .width(60)
            }
        }
    }
}
