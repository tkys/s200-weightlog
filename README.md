# s200 — Xiaomi スマート体重計 S200 の体重を Mac で自動記録

体重計に乗るだけで、Mac mini が BLE 広告（暗号化された MiBeacon）を受信して SQLite に記録し、
`http://localhost:8200/` で推移グラフ（7日移動平均・目標線・BMI）を表示します。
体重計とは接続しない（パッシブ受信）ので、体重計の電池や動作に影響しません。

プロトコルの調査結果は [RESEARCH.md](RESEARCH.md)。

## 1. 鍵の取得（初回のみ）

S200 の体重データは AES-CCM で暗号化されていて、復号には体重計ごとの **BLE KEY (bindkey)** が必要です。

1. スマホの **Xiaomi Home** アプリで S200 を追加（ペアリング）する。
   サーバー地域はアプリで選んだもの（日本なら通常 `jp`）を覚えておく。
2. Mac で [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) を実行し、
   Xiaomi アカウントでログインする。
3. 出力される体重計の項目から次の 2 つを控える：
   - **BLE KEY**：32 桁の16進（`TOKEN` は 24 桁で別物。取り違えに注意）
   - **MAC**：`AA:BB:CC:DD:EE:FF` 形式

> 体重計をリセットして再ペアリングすると BLE KEY は変わります。そのときは取り直してください。

## 2. 設定

```bash
cp config.example.toml config.toml   # config.toml は git 管理外
```

`bindkey` / `mac` / `height_cm` / `goal_kg` を記入します。家族で使う場合は `profile_id` で
自分のユーザー番号だけを記録できます（番号は実際に乗って記録されたログで確認できます）。

## 3. 動かす

```bash
uv sync
uv run s200 scan --seconds 60   # 体重計に乗って FE95 広告が流れるか確認（product=0x4c04 等）
uv run s200 run                 # 記録 + ダッシュボード (http://localhost:8200/)
```

初回は macOS が Bluetooth の利用許可を求めます（システム設定 → プライバシーとセキュリティ → Bluetooth）。

### Mac アプリ（WeightLog）

常駐 (`s200 run`) の API を読む SwiftUI アプリです。メニューバーに最新の体重を常時表示し、
乗った瞬間にリアクション（カウントアップ・ひとこと・節目の紙吹雪・通知）を出します。

```bash
cd app
xcodegen generate
xcodebuild -project WeightLog.xcodeproj -scheme WeightLog -derivedDataPath build build
open build/Build/Products/Debug/WeightLog.app
```

外れ値（家族が乗った・荷物を持っていた等）は自動で「除外」され、グラフの点や最近の記録から戻せます。
身長・目標・スタート体重はアプリの設定（⌘,）で変更できます。

### ログイン時に自動起動（任意）

```bash
mkdir -p logs
cp launchd/com.user.s200.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.s200.plist
tail -f logs/s200.log
```

launchd 経由だと Bluetooth の許可ダイアログが出ずに受信できない場合があります。その場合は
ターミナルで `uv run s200 run` を一度実行して許可を与えるか、ターミナルからの起動を「ログイン項目」に登録してください。

## 4. Google Drive 連携（任意）

記録を自分の Google Drive の「体重ログ」フォルダへ自動でアップロードします。最後の変更から 60 秒待ってまとめて上げ、1 日 1 回はデータベースも丸ごとバックアップします。

| ファイル | 中身 |
|---|---|
| `weights`（スプレッドシート）/ `weights.csv` | 全記録。列は `id, datetime, date, weight_kg, trend_kg, status, reason, profile_id` |
| `daily`（スプレッドシート）/ `daily.csv` | 1 日 1 行。列は `date, weight_kg, trend_kg, count, note, tags`。食事や歩数のデータと `date` で突き合わせられる |
| `backups/weights-YYYY-MM-DD.sqlite3` | 日次バックアップ（直近 30 個） |

スプレッドシートは毎回中身が入れ替わるだけで URL は変わらないので、スマホにブックマークしておけます。
アクセス権は `drive.file`（このアプリが作ったファイルだけ）なので、Drive のほかのファイルは読めません。

### 初期設定（初回のみ・10 分ほど）

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成し、「API とサービス → ライブラリ」で **Google Drive API** を有効にする
2. 「OAuth 同意画面」を設定する
   - ユーザーの種類は「外部」、スコープに `.../auth/drive.file` を追加
   - **「アプリを公開」で本番環境にする**。テスト中のままだと、認証が 7 日で切れる（`drive.file` は審査不要）
3. 「認証情報 → 認証情報を作成 → OAuth クライアント ID」で種類を **デスクトップアプリ** にして作成し、JSON をダウンロードする
4. その JSON を `.drive/client_secret.json` として置く（`.drive/` は git 管理外）
5. 認証する。ブラウザが開くので許可する（「確認されていないアプリ」と出たら「詳細 → 移動」）

   ```bash
   uv run s200 drive auth
   ```
6. `config.toml` の `[drive]` を `enabled = true` にして、一度手動で上げてみる → 常駐プログラムを再起動する

   ```bash
   uv run s200 drive sync
   launchctl kickstart -k gui/$(id -u)/com.user.s200
   ```

同期の状態は、アプリの設定（⌘,）の「Google Drive」の行と `logs/s200.log` の `drive sync:` で確認できます。
ネットにつながらなくても記録は止まらず、つながったら自動で再送します。

## トラブルシュート

| 症状 | 確認すること |
|---|---|
| `scan` に何も出ない | 体重計に乗って数値が確定するまで待つ／Mac との距離／Bluetooth 許可 |
| 広告は出るが記録されない | BLE KEY と TOKEN の取り違え、MAC の誤り、再ペアリングで鍵が変わっていないか |
| 乗ったのに記録されないことがある | `logs/s200.log` に乗った時刻の `scale awake` があるか。無ければ Mac に信号が届いていない（Mac のスリープ、iPhone の Xiaomi Home が先に受け取った）。常駐は `caffeinate -i` で Mac のスリープを止めて動く |
| Drive に上がらない | 設定画面のエラー表示を見る。`invalid_grant` なら認証切れ（同意画面が「テスト中」のまま 7 日経った等）→ `uv run s200 drive auth` をやり直す |
| 同じ計測が何度も来る | 正常。体重計は同じ値を繰り返し流すので `(時刻, ユーザー番号)` で重複を除いています |

## 開発

```bash
uv run pytest      # xiaomi-ble の実パケット（62.25 kg）で復号を検証
uv run ruff check .
```
