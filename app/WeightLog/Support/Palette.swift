import SwiftUI

enum Palette {
    static let weight = Color(red: 0.25, green: 0.47, blue: 0.98)
    static let trend = Color(red: 1.00, green: 0.52, blue: 0.20)
    static let goal = Color(red: 0.18, green: 0.72, blue: 0.48)
    static let down = Color(red: 0.16, green: 0.74, blue: 0.56)
    static let up = Color(red: 0.98, green: 0.42, blue: 0.32)
    static let excluded = Color.secondary.opacity(0.55)

    static func color(for trend: Trend) -> Color {
        switch trend {
        case .down: down
        case .flat: .secondary
        case .up: up
        }
    }

    static let confetti: [Color] = [weight, trend, goal, .pink, .yellow, .purple]
}

struct Card<Content: View>: View {
    var padding: CGFloat = 20
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.background.secondary, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(.separator.opacity(0.5), lineWidth: 0.5)
            )
    }
}
