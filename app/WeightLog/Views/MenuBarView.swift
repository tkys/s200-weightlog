import Charts
import SwiftUI

struct MenuBarLabel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if let latest = model.summary?.latest {
            let trend = Trend(model.summary?.paceKgPerWeek)
            Image(systemName: trend.symbol)
            Text(Format.kg(latest.weightKg, digits: 1))
        } else {
            Image(systemName: "scalemass")
        }
    }
}

struct MenuBarView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let s = model.summary, let latest = s.latest {
                HStack(alignment: .firstTextBaseline) {
                    Text(Format.kg(latest.weightKg))
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .monospacedDigit()
                    Text("kg").foregroundStyle(.secondary)
                    Spacer()
                    Text(Format.relative(latest.date))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 6) {
                    DeltaChip(title: "前回", delta: s.deltaPrev)
                    if let pace = s.paceKgPerWeek {
                        DeltaChip(title: "週", delta: pace)
                    }
                }
                sparkline
                Text(s.comment)
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("まだ記録がありません").foregroundStyle(.secondary)
            }
            Divider()
            HStack {
                Button("ウィンドウを開く") {
                    openWindow(id: "main")
                    NSApp.activate()
                }
                .keyboardShortcut("o")
                Spacer()
                SettingsLink { Image(systemName: "gearshape") }
                Button { NSApp.terminate(nil) } label: { Image(systemName: "power") }
                    .help("体重ログを終了（記録は常駐プログラムが続けます）")
            }
            .buttonStyle(.borderless)
        }
        .padding(16)
        .frame(width: 300)
    }

    private var sparkline: some View {
        let since = Date.now.addingTimeInterval(-30 * 86400)
        let points = model.readings.filter { $0.status.isIncluded && $0.date >= since }
        return Chart(points) { r in
            LineMark(x: .value("日時", r.date), y: .value("トレンド", r.trendKg ?? r.weightKg))
                .interpolationMethod(.monotone)
                .foregroundStyle(Palette.trend)
            PointMark(x: .value("日時", r.date), y: .value("体重", r.weightKg))
                .symbolSize(14)
                .foregroundStyle(Palette.weight)
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartYScale(domain: .automatic(includesZero: false))
        .frame(height: 56)
    }
}
