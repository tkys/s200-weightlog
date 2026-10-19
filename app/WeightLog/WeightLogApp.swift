import SwiftUI

@main
struct WeightLogApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        Window("体重ログ", id: "main") {
            MainView()
                .environment(model)
                .frame(minWidth: 880, minHeight: 600)
        }
        .defaultSize(width: 1120, height: 760)

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
