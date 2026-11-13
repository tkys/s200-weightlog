import SwiftUI

enum Pane: String, CaseIterable, Identifiable {
    case home = "ホーム", calendar = "カレンダー", records = "記録"

    var id: Self { self }

    var symbol: String {
        switch self {
        case .home: "house"
        case .calendar: "calendar"
        case .records: "list.bullet.rectangle"
        }
    }
}

struct MainView: View {
    @Environment(AppModel.self) private var model
    @State private var pane: Pane

    init(pane: Pane = .home) {
        _pane = State(initialValue: pane)
    }

    var body: some View {
        NavigationSplitView {
            List(Pane.allCases, selection: $pane) { p in
                Label(p.rawValue, systemImage: p.symbol).tag(p)
            }
            .navigationSplitViewColumnWidth(min: 150, ideal: 170, max: 220)
        } detail: {
            VStack(spacing: 12) {
                if let error = model.errorMessage {
                    ErrorBanner(message: error)
                }
                switch pane {
                case .home: HomeView()
                case .calendar: CalendarCard()
                case .records: RecordsView()
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(
                LinearGradient(colors: [Palette.weight.opacity(0.05), Palette.trend.opacity(0.03), .clear],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
            )
            .navigationTitle(pane.rawValue)
            .toolbar {
                ToolbarItem(placement: .status) {
                    ConnectionIndicator(isConnected: model.isConnected)
                }
                ToolbarItem {
                    Button("再読み込み", systemImage: "arrow.clockwise") { Task { await model.reload() } }
                }
            }
        }
        .overlay(alignment: .top) {
            if let reaction = model.reaction {
                ReactionBanner(reaction: reaction)
                    .padding(.top, 12)
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
    }
}

/// Everything that matters at a glance, sized to fit without scrolling.
struct HomeView: View {
    var body: some View {
        VStack(spacing: 12) {
            HeroCard()
            StatsRow()
            TrendChartView()
                .frame(maxHeight: .infinity)
        }
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
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
    }
}
