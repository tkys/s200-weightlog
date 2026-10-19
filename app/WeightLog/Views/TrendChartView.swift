import Charts
import SwiftUI

enum ChartRange: String, CaseIterable, Identifiable {
    case week = "7日", month = "30日", quarter = "90日", year = "1年", all = "全期間"

    var id: Self { self }

    var days: Int? {
        switch self {
        case .week: 7
        case .month: 30
        case .quarter: 90
        case .year: 365
        case .all: nil
        }
    }
}

struct TrendChartView: View {
    @Environment(AppModel.self) private var model
    @State private var range: ChartRange = .month
    @State private var hovered: Reading?
    @State private var pinned: Reading?

    private var visible: [Reading] {
        guard let days = range.days else { return model.readings }
        let since = Date.now.addingTimeInterval(-Double(days) * 86400)
        return model.readings.filter { $0.date >= since }
    }

    private var selected: Reading? { hovered ?? pinned }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    SectionTitle(title: "推移", symbol: "chart.xyaxis.line")
                    Spacer()
                    Picker("期間", selection: $range) {
                        ForEach(ChartRange.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .frame(width: 320)
                }

                if visible.isEmpty {
                    ContentUnavailableView("この期間の記録はありません", systemImage: "chart.line.downtrend.xyaxis")
                        .frame(height: 300)
                } else {
                    chart
                        .frame(height: 300)
                    selectionBar
                }
            }
        }
        .onChange(of: model.readings) { _, readings in
            if let p = pinned { pinned = readings.first { $0.id == p.id } }
        }
    }

    private var chart: some View {
        let included = visible.filter { $0.status.isIncluded }
        return Chart {
            ForEach(included) { r in
                AreaMark(
                    x: .value("日時", r.date),
                    yStart: .value("下限", yDomain.lowerBound),
                    yEnd: .value("トレンド", r.trendKg ?? r.weightKg),
                    series: .value("系列", "area")
                )
                .interpolationMethod(.monotone)
                .foregroundStyle(
                    LinearGradient(colors: [Palette.trend.opacity(0.22), Palette.trend.opacity(0)],
                                   startPoint: .top, endPoint: .bottom)
                )
            }
            ForEach(included) { r in
                LineMark(x: .value("日時", r.date), y: .value("トレンド", r.trendKg ?? r.weightKg),
                         series: .value("系列", "trend"))
                    .interpolationMethod(.monotone)
                    .foregroundStyle(Palette.trend)
                    .lineStyle(StrokeStyle(lineWidth: 3, lineCap: .round))
            }
            ForEach(visible) { r in
                PointMark(x: .value("日時", r.date), y: .value("体重", r.weightKg))
                    .symbol(r.status.isIncluded ? BasicChartSymbolShape.circle : .cross)
                    .symbolSize(r.id == selected?.id ? 160 : 46)
                    .foregroundStyle(r.status.isIncluded ? Palette.weight : Palette.excluded)
            }
            if let goal = model.summary?.goalKg, yDomain.contains(goal) {
                RuleMark(y: .value("目標", goal))
                    .foregroundStyle(Palette.goal)
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("目標 \(Format.kg(goal, digits: 1))")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Palette.goal)
                    }
            }
            if let s = selected {
                RuleMark(x: .value("選択", s.date))
                    .foregroundStyle(.secondary.opacity(0.35))
            }
        }
        .chartYScale(domain: yDomain)
        .chartPlotStyle { $0.clipped() }
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle().fill(.clear).contentShape(Rectangle())
                    .onContinuousHover { phase in
                        switch phase {
                        case .active(let point): hovered = nearest(to: point, proxy: proxy, geo: geo)
                        case .ended: hovered = nil
                        }
                    }
                    .onTapGesture { point in
                        let hit = nearest(to: point, proxy: proxy, geo: geo)
                        pinned = (hit?.id == pinned?.id) ? nil : hit
                    }
            }
        }
    }

    @ViewBuilder
    private var selectionBar: some View {
        HStack(spacing: 12) {
            if let r = selected {
                Text(Format.dateTime(r.date))
                    .foregroundStyle(.secondary)
                Text("\(Format.kg(r.weightKg)) kg")
                    .font(.headline)
                    .monospacedDigit()
                if let t = r.trendKg, r.status.isIncluded {
                    Text("トレンド \(Format.kg(t)) kg")
                        .foregroundStyle(Palette.trend)
                }
                StatusBadge(reading: r)
                if let reason = r.reason, !r.status.isIncluded {
                    Text(reason).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Button(r.status.isIncluded ? "この記録を除外" : "記録に戻す",
                       systemImage: r.status.isIncluded ? "eye.slash" : "arrow.uturn.backward") {
                    Task { await model.toggleExcluded(r) }
                }
                .controlSize(.small)
            } else {
                Text("点にカーソルを合わせると詳細、クリックで固定して除外／戻すができます")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Legend()
            }
        }
        .frame(height: 24)
    }

    /// Y range from included readings (outliers would flatten the chart), padded a little.
    private var yDomain: ClosedRange<Double> {
        let values = visible.filter { $0.status.isIncluded }.flatMap { [$0.weightKg, $0.trendKg ?? $0.weightKg] }
        guard var lo = values.min(), var hi = values.max() else { return 0...100 }
        if let goal = model.summary?.goalKg, goal < lo, lo - goal <= 4 { lo = goal }
        if hi - lo < 2 {
            let mid = (hi + lo) / 2
            lo = mid - 1
            hi = mid + 1
        }
        let pad = (hi - lo) * 0.12
        return (lo - pad)...(hi + pad)
    }

    private func nearest(to point: CGPoint, proxy: ChartProxy, geo: GeometryProxy) -> Reading? {
        guard let plot = proxy.plotFrame else { return nil }
        let x = point.x - geo[plot].origin.x
        guard let date: Date = proxy.value(atX: x) else { return nil }
        return visible.min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
    }
}

private struct Legend: View {
    var body: some View {
        HStack(spacing: 14) {
            item(Palette.weight, "体重", "circle.fill")
            item(Palette.trend, "トレンド", "line.diagonal")
            item(Palette.excluded, "除外", "xmark")
            item(Palette.goal, "目標", "line.horizontal.3")
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    private func item(_ color: Color, _ title: String, _ symbol: String) -> some View {
        Label { Text(title) } icon: { Image(systemName: symbol).foregroundStyle(color) }
    }
}
