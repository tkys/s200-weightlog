import AppKit
import Foundation
import SwiftUI
import Testing
@testable import WeightLog

/// Renders README screenshots from demo data; skipped unless asked for.
///
///     scripts/screenshots.sh   # demo data → docs/images/*.png
///
/// Windows are drawn straight into bitmaps (no screen recording), so this
/// works headless and never shows the real data.
@MainActor
@Suite(.enabled(if: Screenshots.fixtures != nil, "set SCREENSHOT_FIXTURES to render screenshots"))
struct ScreenshotTests {
    @Test func renderAll() async throws {
        let model = try Screenshots.demoModel()
        let window = CGSize(width: 1120, height: 760)

        for dark in [false, true] {
            let suffix = dark ? "dark" : "light"
            try await Screenshots.window(MainView(pane: .home), model, title: "ホーム", size: window,
                                         dark: dark, name: "home-\(suffix)")
        }
        try await Screenshots.window(MainView(pane: .calendar), model, title: "カレンダー", size: window,
                                     dark: false, name: "calendar-light")
        try await Screenshots.window(MainView(pane: .records), model, title: "記録", size: window,
                                     dark: false, name: "records-light")
        try await Screenshots.view(MenuBarView().frame(width: 320), model, dark: false,
                                   name: "menubar-light")

        model.reaction = try Screenshots.reaction(model)
        try await Screenshots.window(MainView(pane: .home), model, title: "ホーム", size: window,
                                     dark: false, name: "reaction-light")
    }
}

/// Draws as the active window (blue selection, enabled-looking controls).
final class SnapshotWindow: NSWindow {
    override var isKeyWindow: Bool { true }
    override var isMainWindow: Bool { true }
}

@MainActor
enum Screenshots {
    nonisolated static var fixtures: URL? {
        ProcessInfo.processInfo.environment["SCREENSHOT_FIXTURES"].map { URL(fileURLWithPath: $0) }
    }

    static var output: URL {
        let path = ProcessInfo.processInfo.environment["SCREENSHOT_OUT"] ?? NSTemporaryDirectory()
        return URL(fileURLWithPath: path)
    }

    static func load<T: Decodable>(_ type: T.Type, _ name: String) throws -> T {
        let data = try Data(contentsOf: fixtures!.appending(path: name))
        return try WireCoding.decoder().decode(T.self, from: data)
    }

    /// A model filled from the fixtures; its API points nowhere so nothing reaches the daemon.
    static func demoModel() throws -> AppModel {
        let model = AppModel(api: APIClient(baseURL: URL(string: "http://127.0.0.1:9")!))
        let readings = try load(ReadingsResponse.self, "readings.json")
        model.summary = try load(Summary.self, "summary.json")
        model.readings = readings.readings
        model.settings = readings.settings
        model.notes = Dictionary(uniqueKeysWithValues: try load(NotesResponse.self, "notes.json")
            .notes.map { ($0.date, $0) })
        model.isConnected = true
        return model
    }

    static func reaction(_ model: AppModel) throws -> Reaction {
        struct Fixture: Decodable { let reading: Reading; let previousKg: Double }
        let f = try load(Fixture.self, "reaction.json")
        return Reaction(reading: f.reading, summary: model.summary!, previousKg: f.previousKg)
    }

    /// A full window, title bar and toolbar included.
    static func window(
        _ view: some View, _ model: AppModel, title: String, size: CGSize, dark: Bool, name: String
    ) async throws {
        let controller = NSHostingController(
            rootView: view.environment(model).environment(\.locale, AppLocale.locale))
        controller.sceneBridgingOptions = [.toolbars, .title]
        let window = SnapshotWindow(
            contentRect: CGRect(origin: .zero, size: size),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered, defer: false)
        window.contentViewController = controller
        window.title = title
        window.toolbarStyle = .unified
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.setContentSize(size)
        // Far off any screen: it must be ordered in to get a toolbar, but nobody sees it.
        window.setFrameOrigin(NSPoint(x: -20_000, y: -20_000))
        window.orderFrontRegardless()
        defer { window.close() }
        try await settle()
        if let image = windowServerImage(window) {
            print("screenshot \(name): window server \(image.width)x\(image.height)")
            try write(NSBitmapImageRep(cgImage: image), name: name)
            return
        }
        let frameView = window.contentView!.superview!
        flattenEffects(frameView)
        try await Task.sleep(for: .seconds(0.5))
        try write(frameView, name: name)
    }

    /// Just the view, sized to fit (for the menu bar popover).
    static func view(_ view: some View, _ model: AppModel, dark: Bool, name: String) async throws {
        let host = NSHostingView(
            rootView: view.environment(model).environment(\.locale, AppLocale.locale).fixedSize())
        host.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        host.setFrameSize(host.fittingSize)
        let window = NSWindow(contentRect: host.bounds, styleMask: [.borderless], backing: .buffered,
                              defer: false)
        window.contentView = host
        window.backgroundColor = dark ? .windowBackgroundColor : .white
        window.setFrameOrigin(NSPoint(x: -20_000, y: -20_000))
        window.orderFrontRegardless()
        defer { window.close() }
        try await settle()
        try write(host, name: name)
    }

    /// Let layout, charts and the count-up animations finish.
    private static func settle() async throws {
        try await Task.sleep(for: .seconds(4))
    }

    /// Vibrancy blends with whatever is behind the window, which a bitmap
    /// capture cannot see; blend within the window instead so it draws.
    private static func flattenEffects(_ view: NSView) {
        if let effect = view as? NSVisualEffectView {
            effect.blendingMode = .withinWindow
            effect.state = .active
        }
        view.subviews.forEach(flattenEffects)
    }

    private typealias CreateWindowImage =
        @convention(c) (CGRect, UInt32, UInt32, UInt32) -> Unmanaged<CGImage>?

    /// Our own window as the window server composites it (glass sidebar and
    /// toolbar included). The API is hidden from the macOS 15 SDK, so look it up.
    private static func windowServerImage(_ window: NSWindow) -> CGImage? {
        guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGWindowListCreateImage")
        else { return nil }
        let create = unsafeBitCast(symbol, to: CreateWindowImage.self)
        let includingWindow: UInt32 = 1 << 3, boundsIgnoreFraming: UInt32 = 1 << 0
        let bestResolution: UInt32 = 1 << 3
        guard let image = create(.null, includingWindow, UInt32(window.windowNumber),
                                 boundsIgnoreFraming | bestResolution)?.takeRetainedValue(),
              image.width > 1 else { return nil }
        return image
    }

    private static func write(_ view: NSView, name: String) throws {
        let rep = try #require(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: rep)
        try write(rep, name: name)
    }

    private static func write(_ rep: NSBitmapImageRep, name: String) throws {
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        try png.write(to: output.appending(path: "\(name).png"))
    }
}
