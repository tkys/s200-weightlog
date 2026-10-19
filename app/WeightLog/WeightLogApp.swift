import SwiftUI

@main
struct WeightLogApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        Window("体重ログ", id: "main") {
            MainView()
                .environment(model)
                .frame(minWidth: 940, minHeight: 680)
        }
        .defaultSize(width: 1180, height: 860)

        MenuBarExtra {
            MenuBarView()
                .environment(model)
        } label: {
            MenuBarLabel()
                .environment(model)
                // The menu bar item exists for the whole app lifetime, so it owns the live connection.
                .task { await model.start() }
        }
        .menuBarExtraStyle(.window)

        Settings {
            SettingsView()
                .environment(model)
        }
    }
}
