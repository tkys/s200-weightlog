import SwiftUI

/// Drops in from the top when a new weigh-in arrives, counting up to the new value.
struct ReactionBanner: View {
    @Environment(AppModel.self) private var model
    let reaction: Reaction
    @State private var shown: Double = 0

    var body: some View {
        let included = reaction.reading.status.isIncluded
        HStack(spacing: 18) {
            Image(systemName: included ? "checkmark.seal.fill" : "eye.slash.circle.fill")
                .font(.system(size: 34))
                .foregroundStyle(included ? Palette.down : .secondary)
                .symbolEffect(.bounce, value: reaction.id)
            VStack(alignment: .leading, spacing: 4) {
                Text(included ? "記録しました" : "除外しました")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    CountingNumber(value: shown)
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                    Text("kg").foregroundStyle(.secondary)
                    if included {
                        DeltaChip(title: "前回比", delta: reaction.summary.deltaPrev)
                    }
                }
                Text(reaction.summary.comment)
                    .font(.callout)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            Button { model.reaction = nil } label: { Image(systemName: "xmark") }
                .buttonStyle(.borderless)
        }
        .padding(18)
        .frame(width: 560)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: .black.opacity(0.18), radius: 24, y: 10)
        .onAppear {
            shown = reaction.previousKg ?? reaction.reading.weightKg
            withAnimation(.easeOut(duration: 1.6).delay(0.2)) { shown = reaction.reading.weightKg }
        }
        .task(id: reaction.id) {
            try? await Task.sleep(for: .seconds(12))
            if model.reaction?.id == reaction.id { model.reaction = nil }
        }
    }
}

/// Confetti + headline for milestones. Removes itself after a few seconds.
struct CelebrationOverlay: View {
    @Environment(AppModel.self) private var model
    let celebration: Celebration
    @State private var start = Date.now
    @State private var particles: [Particle] = (0..<140).map { _ in Particle() }

    private let duration: TimeInterval = 4.5

    var body: some View {
        TimelineView(.animation) { timeline in
            let t = timeline.date.timeIntervalSince(start)
            ZStack {
                Canvas { ctx, size in
                    for p in particles {
                        let local = t - p.delay
                        guard local > 0 else { continue }
                        let x = p.x * size.width + sin(local * p.wobble) * 24
                        let y = -20 + local * p.speed * size.height * 0.45
                        guard y < size.height + 20 else { continue }
                        var c = ctx
                        c.opacity = max(0, 1 - t / duration * 0.9)
                        c.translateBy(x: x, y: y)
                        c.rotate(by: .radians(local * p.spin))
                        c.fill(Path(CGRect(x: -p.size / 2, y: -p.size / 4, width: p.size, height: p.size / 2)),
                               with: .color(p.color))
                    }
                }
                VStack(spacing: 8) {
                    Text("🎉")
                        .font(.system(size: 64))
                    ForEach(celebration.milestones, id: \.self) { m in
                        Text(m.title)
                            .font(.system(size: 34, weight: .heavy, design: .rounded))
                    }
                }
                .padding(.horizontal, 36)
                .padding(.vertical, 24)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
                .scaleEffect(min(1, 0.6 + t * 1.6))
                .opacity(t < duration - 0.6 ? 1 : max(0, (duration - t) / 0.6))
            }
        }
        .task(id: celebration.id) {
            start = .now
            particles = (0..<140).map { _ in Particle() }
            try? await Task.sleep(for: .seconds(duration))
            if model.celebration?.id == celebration.id { model.celebration = nil }
        }
    }

    struct Particle {
        let x = Double.random(in: 0...1)
        let delay = Double.random(in: 0...0.8)
        let speed = Double.random(in: 0.6...1.3)
        let wobble = Double.random(in: 2...6)
        let spin = Double.random(in: -8...8)
        let size = Double.random(in: 8...14)
        let color = Palette.confetti.randomElement()!
    }
}
