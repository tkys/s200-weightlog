import SwiftUI

/// A number that counts from its old value to the new one when animated.
struct CountingNumber: View, Animatable {
    var value: Double
    var digits: Int = 2

    nonisolated var animatableData: Double {
        get { value }
        set { value = newValue }
    }

    var body: some View {
        Text(Format.kg(value, digits: digits))
            .monospacedDigit()
    }
}

/// "前回比 -0.20 kg" style pill, colored by direction.
struct DeltaChip: View {
    let title: String
    let delta: Double?
    var unit = "kg"

    var body: some View {
        let trend = Trend(delta)
        HStack(spacing: 6) {
            Text(title)
                .foregroundStyle(.secondary)
            if delta != nil {
                Image(systemName: trend.symbol)
                    .font(.caption.weight(.bold))
                Text("\(Format.signed(delta)) \(unit)")
                    .monospacedDigit()
                    .fontWeight(.semibold)
            } else {
                Text("–")
            }
        }
        .font(.callout)
        .foregroundStyle(delta == nil ? .secondary : Palette.color(for: trend))
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Palette.color(for: trend).opacity(delta == nil ? 0.06 : 0.12), in: Capsule())
    }
}

struct StatusBadge: View {
    let reading: Reading

    var body: some View {
        switch reading.status {
        case .ok:
            EmptyView()
        case .outlier, .merged:
            Label(reading.status == .merged ? "統合" : "除外中", systemImage: "eye.slash")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(.quaternary, in: Capsule())
                .help(reading.reason ?? "")
        }
    }
}

struct SectionTitle: View {
    let title: String
    var symbol: String?

    var body: some View {
        Label {
            Text(title)
        } icon: {
            if let symbol { Image(systemName: symbol) }
        }
        .font(.headline)
    }
}
