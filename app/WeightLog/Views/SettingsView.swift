import ServiceManagement
import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var draft = BodySettings()
    @State private var launchAtLogin = SMAppService.mainApp.status == .enabled
    @State private var launchError: String?
    @State private var saved = false

    var body: some View {
        Form {
            Section("からだ") {
                TextField("身長", value: $draft.heightCm, format: .number, prompt: Text("170"))
                    .help("cm")
                TextField("目標体重", value: $draft.goalKg, format: .number, prompt: Text("65.0"))
                    .help("kg")
                TextField("スタート体重", value: $draft.startKg, format: .number,
                          prompt: Text(model.summary?.startKg.map { Format.kg($0, digits: 1) } ?? "最初の記録"))
                    .help("空欄なら最初の記録を使います")
            }
            Section("一般") {
                Toggle("ログイン時に起動", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { _, on in setLaunchAtLogin(on) }
                if let launchError {
                    Text(launchError).font(.caption).foregroundStyle(.orange)
                }
                LabeledContent("常駐プログラム") {
                    Text(model.isConnected ? "接続中" : "未接続")
                        .foregroundStyle(model.isConnected ? Palette.down : .secondary)
                }
            }
            HStack {
                if saved {
                    Label("保存しました", systemImage: "checkmark").foregroundStyle(Palette.down)
                }
                Spacer()
                Button("保存") {
                    Task {
                        await model.save(draft)
                        saved = true
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(draft == model.settings)
            }
        }
        .formStyle(.grouped)
        .frame(width: 420)
        .onAppear { draft = model.settings }
        .onChange(of: draft) { saved = false }
    }

    private func setLaunchAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            launchError = nil
        } catch {
            launchError = "設定できませんでした：\(error.localizedDescription)"
            launchAtLogin = SMAppService.mainApp.status == .enabled
        }
    }
}
