import ServiceManagement
import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var draft = BodySettings()
    @State private var launchAtLogin = SMAppService.mainApp.status == .enabled
    @State private var launchError: String?
    @State private var saved = false
    @State private var drive: DriveStatus?

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
                LabeledContent("Google Drive") { driveLabel }
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
        .task {
            // Poll while the window is open; the upload runs in the daemon.
            while !Task.isCancelled {
                drive = try? await APIClient.local.driveStatus()
                try? await Task.sleep(for: .seconds(10))
            }
        }
        .onChange(of: draft) { saved = false }
    }

    @ViewBuilder
    private var driveLabel: some View {
        switch drive?.line {
        case nil:
            Text("–").foregroundStyle(.secondary)
        case .off:
            Text("オフ（config.toml の [drive]）").foregroundStyle(.secondary)
        case .waiting:
            Text("同期待ち").foregroundStyle(.secondary)
        case .synced(let date):
            Text("最終同期 \(Format.relative(date))").foregroundStyle(Palette.down)
        case .error(let message):
            Text(message)
                .font(.caption)
                .foregroundStyle(.orange)
                .lineLimit(2)
                .help(message)
        }
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
