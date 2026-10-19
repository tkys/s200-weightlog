import SwiftUI

struct MainView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let error = model.errorMessage {
                    ErrorBanner(message: error)
                }
                HStack(alignment: .top, spacing: 16) {
                    HeroCard()
                        .frame(maxWidth: .infinity)
                    StatsGrid()
                        .frame(width: 360)
                }
                TrendChartView()
                HStack(alignment: .top, spacing: 16) {
                    CalendarCard()
                    RecentCard()
                        .frame(width: 360)
                }
            }
            .padding(20)
        }
        .background(
            LinearGradient(colors: [Palette.weight.opacity(0.06), Palette.trend.opacity(0.04), .clear],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        )
        .overlay(alignment: .top) {
            if let reaction = model.reaction {
                ReactionBanner(reaction: reaction)
                    .padding(.top, 16)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .overlay {
            if let celebration = model.celebration {
                CelebrationOverlay(celebration: celebration)
                    .allowsHitTesting(false)
            }
        }
        .animation(.spring(duration: 0.5), value: model.reaction)
        .toolbar {
            ToolbarItem(placement: .status) {
                ConnectionIndicator(isConnected: model.isConnected)
            }
            ToolbarItem {
                Button("再読み込み", systemImage: "arrow.clockwise") { Task { await model.reload() } }
            }
        }
        .navigationTitle("体重ログ")
    }
}

private struct ConnectionIndicator: View {
    let isConnected: Bool

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(isConnected ? Palette.down : .secondary)
                .frame(width: 8, height: 8)
            Text(isConnected ? "受信待機中" : "接続中…")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .help(isConnected ? "体重計に乗ると自動で記録されます" : "常駐プログラム (s200 run) に接続しています")
    }
}

private struct ErrorBanner: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .foregroundStyle(.orange)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
    }
}

/// Latest weigh-ins with one-click exclude / restore.
struct RecentCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "最近の記録", symbol: "list.bullet")
                let recent = Array(model.readings.suffix(14).reversed())
                if recent.isEmpty {
                    Text("まだ記録がありません").foregroundStyle(.secondary)
                }
                ForEach(Array(recent.enumerated()), id: \.element.id) { i, r in
                    let prev = recent[(i + 1)...].first { $0.status.isIncluded }
                    RecentRow(reading: r, delta: r.status.isIncluded ? prev.map { r.weightKg - $0.weightKg } : nil)
                    if i < recent.count - 1 { Divider() }
                }
            }
        }
    }
}

private struct RecentRow: View {
    @Environment(AppModel.self) private var model
    let reading: Reading
    let delta: Double?
    @State private var hovering = false

    var body: some View {
        HStack(spacing: 10) {
            Text(Format.dateTime(reading.date))
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(width: 130, alignment: .leading)
            Text("\(Format.kg(reading.weightKg))")
                .font(.callout.weight(.semibold))
                .monospacedDigit()
                .strikethrough(!reading.status.isIncluded)
                .foregroundStyle(reading.status.isIncluded ? .primary : .secondary)
            if let delta {
                Text(Format.signed(delta))
                    .font(.caption.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(Palette.color(for: Trend(delta)))
            }
            StatusBadge(reading: reading)
            Spacer()
            Button {
                Task { await model.toggleExcluded(reading) }
            } label: {
                Image(systemName: reading.status.isIncluded ? "eye.slash" : "arrow.uturn.backward")
            }
            .buttonStyle(.borderless)
            .help(reading.status.isIncluded ? "この記録を除外" : "記録に戻す")
            .opacity(hovering || !reading.status.isIncluded ? 1 : 0)
        }
        .onHover { hovering = $0 }
    }
}
