import SwiftUI

/// Latest weight, deltas and the daemon's comment in one compact row.
struct HeroCard: View {
    @Environment(AppModel.self) private var model
    @State private var shown: Double = 0

    var body: some View {
        Card(padding: 18) {
            if let summary = model.summary, let latest = summary.latest {
                content(summary, latest)
            } else {
                Label("まだ記録がありません。体重計に乗ると、ここに結果が出ます", systemImage: "scalemass")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 90)
            }
        }
        .onChange(of: model.summary?.latest?.weightKg, initial: true) { _, new in
            guard let new else { return }
            withAnimation(.spring(duration: 1.4, bounce: 0.2)) { shown = new }
        }
    }

    @ViewBuilder
    private func content(_ summary: Summary, _ latest: Reading) -> some View {
        HStack(alignment: .center, spacing: 24) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(Format.dateTime(latest.date))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    StatusBadge(reading: latest)
                }
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    CountingNumber(value: shown)
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .foregroundStyle(latest.status.isIncluded ? .primary : .secondary)
                    Text("kg")
                        .font(.system(size: 20, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .fixedSize()

            VStack(alignment: .leading, spacing: 6) {
                DeltaChip(title: "前回比", delta: summary.deltaPrev)
                DeltaChip(title: "スタート比", delta: summary.deltaStart)
            }
            .fixedSize()

            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "sparkles")
                    .foregroundStyle(Palette.trend)
                Text(summary.comment)
                    .font(.body.weight(.medium))
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.trend.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }
}

/// Four key numbers in one row; secondary stats ride along as captions.
struct StatsRow: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let s = model.summary
        HStack(spacing: 12) {
            StatTile(
                title: "トレンド体重", value: Format.kg(s?.trendKg), unit: "kg", symbol: "waveform.path.ecg",
                caption: s?.deltaTrendWeek.map { "7日で \(Format.signed($0)) kg" } ?? "日々の増減をならした値"
            )
            StatTile(
                title: "ペース", value: Format.signed(s?.paceKgPerWeek), unit: "kg/週",
                symbol: Trend(s?.paceKgPerWeek).symbol,
                caption: s?.paceKgPerWeek == nil ? "数日分の記録で表示" : "直近14日",
                tint: s?.paceKgPerWeek == nil ? nil : Palette.color(for: Trend(s?.paceKgPerWeek))
            )
            StatTile(
                title: "目標まで", value: goalRemaining(s), unit: s?.goalKg == nil ? "" : "kg",
                symbol: "flag.checkered",
                caption: s?.etaDate.map { "予定 \(Format.day($0))" }
                    ?? s?.goalKg.map { "目標 \(Format.kg($0, digits: 1)) kg" } ?? "設定で目標を入力"
            )
            StatTile(
                title: "連続記録", value: "\(s?.streakDays ?? 0)", unit: "日", symbol: "flame.fill",
                caption: [s?.bmi.map { "BMI \(Format.kg($0, digits: 1))" },
                          s?.lowestKg.map { "最安 \(Format.kg($0, digits: 1))" }]
                    .compactMap { $0 }.joined(separator: " · "),
                tint: (s?.streakDays ?? 0) >= 3 ? Palette.trend : nil
            )
        }
    }

    private func goalRemaining(_ s: Summary?) -> String {
        guard let goal = s?.goalKg, let trend = s?.trendKg else { return "–" }
        let rest = trend - goal
        return rest <= 0 ? "達成" : Format.kg(rest, digits: 1)
    }
}

struct StatTile: View {
    let title: String
    let value: String
    let unit: String
    let symbol: String
    var caption: String?
    var tint: Color?

    var body: some View {
        Card(padding: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Label(title, systemImage: symbol)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint ?? .secondary)
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(value)
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                    Text(unit)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(caption ?? " ")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
    }
}
