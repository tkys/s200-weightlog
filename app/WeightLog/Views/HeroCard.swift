import SwiftUI

/// The big latest-weight card with deltas and the daemon's comment.
struct HeroCard: View {
    @Environment(AppModel.self) private var model
    @State private var shown: Double = 0

    var body: some View {
        Card(padding: 28) {
            if let summary = model.summary, let latest = summary.latest {
                content(summary, latest)
            } else {
                ContentUnavailableView(
                    "まだ記録がありません",
                    systemImage: "scalemass",
                    description: Text("体重計に乗ると、ここに結果が出ます")
                )
                .frame(maxWidth: .infinity, minHeight: 220)
            }
        }
        .onChange(of: model.summary?.latest?.weightKg, initial: true) { _, new in
            guard let new else { return }
            withAnimation(.spring(duration: 1.4, bounce: 0.2)) { shown = new }
        }
    }

    @ViewBuilder
    private func content(_ summary: Summary, _ latest: Reading) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 8) {
                Text("最新")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(Format.dateTime(latest.date))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                StatusBadge(reading: latest)
            }

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                CountingNumber(value: shown)
                    .font(.system(size: 84, weight: .bold, design: .rounded))
                    .foregroundStyle(latest.status.isIncluded ? .primary : .secondary)
                Text("kg")
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                DeltaChip(title: "前回比", delta: summary.deltaPrev)
                DeltaChip(title: "スタート比", delta: summary.deltaStart)
                DeltaChip(title: "トレンド 7日", delta: summary.deltaTrendWeek)
            }

            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "sparkles")
                    .foregroundStyle(Palette.trend)
                Text(summary.comment)
                    .font(.title3.weight(.medium))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.trend.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }
}

/// Small stat tiles next to the hero.
struct StatsGrid: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let s = model.summary
        Grid(horizontalSpacing: 12, verticalSpacing: 12) {
            GridRow {
                StatTile(title: "トレンド体重", value: Format.kg(s?.trendKg), unit: "kg", symbol: "waveform.path.ecg")
                StatTile(
                    title: "ペース",
                    value: Format.signed(s?.paceKgPerWeek),
                    unit: "kg/週",
                    symbol: Trend(s?.paceKgPerWeek).symbol,
                    tint: s?.paceKgPerWeek == nil ? nil : Palette.color(for: Trend(s?.paceKgPerWeek))
                )
            }
            GridRow {
                StatTile(
                    title: "目標まで",
                    value: goalRemaining(s),
                    unit: s?.goalKg == nil ? "" : "kg",
                    symbol: "flag.checkered",
                    caption: s?.etaDate.map { "予定 \(Format.day($0))" } ?? (s?.goalKg.map { "目標 \(Format.kg($0, digits: 1)) kg" })
                )
                StatTile(title: "連続記録", value: "\(s?.streakDays ?? 0)", unit: "日", symbol: "flame.fill",
                         tint: (s?.streakDays ?? 0) >= 3 ? Palette.trend : nil)
            }
            GridRow {
                StatTile(title: "BMI", value: s?.bmi.map { Format.kg($0, digits: 1) } ?? "–", unit: "", symbol: "figure.stand")
                StatTile(title: "最安値", value: Format.kg(s?.lowestKg), unit: "kg", symbol: "trophy.fill")
            }
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
        Card(padding: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Label(title, systemImage: symbol)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint ?? .secondary)
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(value)
                        .font(.system(size: 26, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                    Text(unit)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Text(caption ?? " ")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
