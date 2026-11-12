# 体重ログ v2：SwiftUI ネイティブ Mac アプリへの作り直し

## Context
Xiaomi S200 → Mac mini の自動記録は完成済み（Python 常駐 `s200 run` を launchd で起動。BLE 受信 → SQLite → HTTP API）。現在の画面（Chart.js の HTML ＋ pywebview）は仮のもの。ユーザーの希望は次の4点：
1. **乗った瞬間のリアクション**：即時反映、変化量、通知、節目の演出、ひとことコメント
2. **外れ値の自動除外**：データは残して、グラフや平均から外す。ワンタップで戻せる
3. **トレンドと予測**：トレンド体重、週あたりのペース、目標到達予定日
4. **カレンダーとメモ**：記録した日、連続日数、日ごとのメモとタグ

将来は食事や歩数などの外部データ連携もありえるので、拡張しやすい形にしておく（今回は作らない）。

## 方針（アーキテクチャ）
- **Python 常駐をバックエンドとして残す**。BLE 受信は実機で動作確認済みなので触らない。判定と集計（外れ値・トレンド・連続日数・節目）は Python 側で行い、pytest で検証する。iPhone や Web から見る場合も同じ API を使い回せる。
- **SwiftUI アプリは表示とリアクション担当**。ウィンドウとメニューバー常駐（`MenuBarExtra`）を持ち、localhost の API を読む。新しい記録は SSE（Server-Sent Events）で即時に受け取る。
- 連携先が増えたら、`/api` に種類ごとのエンドポイントを足していく前提にする。日付ごとのメモ表（`day_notes`）を、日単位で集約する土台として使う。

## バックエンド変更（`s200/`）
### store.py：スキーマ移行（`PRAGMA user_version` で管理）
- `readings` に列を追加：`status TEXT DEFAULT 'ok'`（`ok` / `outlier` / `merged`）、`reason TEXT`、`manual INTEGER DEFAULT 0`（ユーザーが手動で切り替えたら1。自動判定で上書きしない）
- `day_notes(date TEXT PRIMARY KEY, note TEXT, tags TEXT /*JSON*/)` を追加
- `settings(key PRIMARY KEY, value)` を追加：`height_cm`・`goal_kg`・`start_kg` をアプリから編集できるようにする（`config.toml` の値を初期値にする）
- 既存の 74.40 / 74.60 の2件はそのまま引き継ぐ

### analysis.py（新規・純粋関数）
- **トレンド体重**：時間で重みを付ける指数移動平均。`α = 1 - exp(-Δt / 10日)`、除外された記録は使わない
- **外れ値判定**（追加時に実行）：
  - 判定対象の記録が5件以上たまってから有効にする
  - トレンドとの差が `max(2.0 kg, 4 × MAD)` を超えたら `outlier`
  - 10分以内に連続で乗った場合は最後の1件を残し、それ以前を `merged` にする
  - `manual=1` の記録は判定しない
- **ペース**：直近14日のトレンドを最小二乗で直線近似し、kg/週を出す
- **目標到達予定日**：(トレンド − 目標) ÷ ペース。減っていなければ出さない
- **連続記録日数**、**最安値**、**スタートからの変化**
- **節目判定**：最安値の更新、スタートから 1 kg 減るごと、連続 7 / 30 / 100 日、目標達成
- **ひとことコメント**：テンプレートで作る。例：「+0.2 kg、でもトレンドは -0.3 kg/週。順調です」

### web.py：API 追加
- `GET /api/summary` … 最新値、各種の差分（前回比・トレンド比・スタート比）、トレンド、ペース、予定日、連続日数、コメント、節目
- `GET /api/readings` … `status`・`reason`・各時点のトレンド値を含める
- `PATCH /api/readings/{id}` … `{"status":"ok"|"outlier"}`（`manual=1` になる）
- `GET/PUT /api/notes/{YYYY-MM-DD}`、`GET /api/notes?from=&to=`
- `GET/PUT /api/settings`
- `GET /api/stream` … SSE。新しい記録や変更があったら `event: reading` で summary を送る。接続を保つため15秒ごとに ping を送る
- `ThreadingHTTPServer` のまま実装する。イベントは `queue.Queue` で各 SSE 接続へ配る
- `cli.py` の `on_reading` を変更：保存 → 判定 → 配信

## SwiftUI アプリ（`app/`、XcodeGen で作成、macOS 15 以降、Swift 6）
```
app/project.yml
app/WeightLog/
  WeightLogApp.swift        # WindowGroup + MenuBarExtra + Settings
  Models/ API.swift         # Codable（Summary, Reading, DayNote, Settings）
  Services/ APIClient.swift # URLSession async
            EventStream.swift  # SSE（URLSession.bytes の行読み）、切断したら自動で再接続
            Notifier.swift     # UserNotifications
  AppModel.swift            # @Observable、状態を一元管理
  Views/ DashboardView.swift      # ヒーロー数字 (.contentTransition(.numericText()))、差分チップ、コメント
         TrendChartView.swift     # Swift Charts：点・トレンド線・目標線。除外した点は灰色の×で表示、クリックで切り替え
         CalendarView.swift       # 月のヒートマップ、連続日数。日付クリックでメモ編集
         NoteEditor.swift         # メモとタグ（飲み会/運動/体調不良 などのプリセット＋自由入力）
         MenuBarView.swift        # 最新値、傾向の矢印、ミニグラフ、「ウィンドウを開く」
         CelebrationOverlay.swift # Canvas の紙吹雪（節目のときだけ表示）
         SettingsView.swift       # 身長・目標・スタート体重、ログイン時に起動（SMAppService）
WeightLogTests/             # Swift Testing
```
- 新しい記録が届いたら：ヒーロー数字がカウントアップ → 差分チップを表示 → コメントを表示 → 節目なら紙吹雪 → ウィンドウが裏にあるときは通知
- App Sandbox は使わない（個人用アプリで localhost に接続するため）。署名はローカル署名（Sign to Run Locally）

## 実装順
1. PLAN.md に設計を保存（CLAUDE.md のルール）、ここまでの v1 を git commit
2. store の移行と analysis.py ＋ pytest
3. web の API と SSE ＋ pytest（SSE は実際にソケットで受信して確かめる）
4. launchd の常駐を再起動して、実データで `/api/summary` を確認
5. XcodeGen でプロジェクトを作成 → モデルと API クライアント ＋ Swift Testing（JSON デコード、日付の扱い）
6. 各画面（ダッシュボード → グラフ → カレンダーとメモ → メニューバー → 演出 → 設定）
7. `xcodebuild build test` → アプリを起動 → 実際に体重計に乗ってリアクションを確認
8. pywebview の仮 UI（`desktop.py`）と `static/index.html` は削除する（API 確認用に最小の HTML だけ残すかは実装時に判断）

## Verification
- `uv run pytest`：移行（既存データの引き継ぎ）、トレンド計算、外れ値の各パターン（他の人が乗った、荷物を持った、連続計測、データが少ない期間、手動で戻した記録が再判定されない）、ペースと予定日、節目、API、SSE の配信
- `xcodebuild -scheme WeightLog test`：デコードとコメント表示の処理
- 実機：体重計に乗る → 数秒でアプリの数字が更新される／通知が出る／メニューバーの値が変わる。グラフの点をクリックして除外 → 戻す。メモを保存 → 再起動しても残っている
- テスト結果はコミットメッセージに記録する

## リスクと注意
- XcodeBuildMCP は接続に失敗しているため、`xcodebuild` を直接使う
- スクリーンショットが撮れない（画面収録の許可がない）ので、見た目の確認はユーザーにお願いする
- SSE の接続が切れても、アプリ側で再接続し、summary を再取得するので取りこぼさない


---

# v3: 体重ログ → Google Drive 自動アップロード

## Context
今の体重記録は Mac mini の SQLite（`weights.sqlite3`）にしかない。Google Drive に自動で上げて、次の4つに使えるようにする。
- **バックアップ**
- **スマホなどで見る**
- **スプレッドシートで分析**
- **ほかのサービスや AI との連携**（食事・歩数と日付で突き合わせる）

決めたこと：
- **Drive API で直接アップロードする。** Drive のデスクトップアプリは入っていない。
- 権限は **`drive.file`** にする。このアプリが作ったファイルしか触れず、Drive のほかのファイルは見えない。

## Drive 上の構成（マイドライブ/体重ログ/）
| ファイル | 中身 | 用途 |
|---|---|---|
| `weights`（スプレッドシート）＋ `weights.csv` | 全記録：`id, datetime, date, weight_kg, trend_kg, status, reason, profile_id` | 閲覧、分析 |
| `daily`（スプレッドシート）＋ `daily.csv` | 1日1行：`date, weight_kg`（その日最後の有効な記録）`, trend_kg, count, note, tags` | AI 連携。`date` をキーにして、食事・歩数と結合する |
| `backups/weights-YYYY-MM-DD.sqlite3` | 1日1回の DB のスナップショット。直近30個を残す | バックアップ |

- 列名は英語の snake_case にする。AI やほかのツールが読みやすく、あとから変わらないため。
- スプレッドシートは、CSV を「変換付き」で同じファイル ID に上書きする。中身は全部入れ替わり、URL は変わらない（Drive API の仕様で確認済み）。
- CSV ファイルは、変換せずにそのまま置く。

## 仕組み
- **`s200/export.py`**（新規、副作用なし）：`readings_csv(rows)` と `daily_csv(rows, notes)` を作る。
  - 既存の `analysis.with_trend` と `analysis.local_date` を使う。
  - 除外した記録は `daily` の集計に含めない。
- **`s200/drive.py`**（新規）
  - `DriveClient(session)`：最小限の REST ラッパー。
    - `ensure_folder`：フォルダを探し、なければ作る
    - `upload`：新規作成は multipart、更新は media でファイル ID に上書き。変換の指定もできる
    - `list_children`、`delete`
  - **ファイル ID は `.drive/state.json` に保存する。** 保存した ID が 404 になったら（ユーザーが Drive で消したら）作り直す。
  - `sync_once(store, client, state, now)`：4つのファイルを上げる。その日のバックアップがまだなければ、DB のスナップショット（`sqlite3` の backup API で一時ファイルに書き出す）も上げる。30個を超えた古いバックアップは消す。
  - `DriveSync`：別スレッドで動く。
    - `app.hub`（SSE と同じ配信の仕組み）を購読し、`reading` / `changed` イベントで「更新あり」にする。
    - **最後の変更から60秒待ってからまとめてアップロードする。** 乗り直しや連続した編集を1回にまとめるため。起動時にも1回同期する。
    - 日付が変わったらバックアップを取る。
    - 失敗したら警告をログに出し、1分から最大30分まで間隔を延ばしながら再試行する。**BLE の受信や記録は止めない。**
    - 状態（最終成功時刻、最後のエラー）を持つ。
- **認証**：`google-auth` と `google-auth-oauthlib` を使う。InstalledAppFlow でブラウザから一度だけ認証し、更新トークンを `.drive/token.json`（権限 600）に保存する。REST の呼び出しには `AuthorizedSession` を使う。重い `google-api-python-client` は入れない。
- **`config.toml`** に `[drive]` を追加する：`enabled`、`folder = "体重ログ"`、`backup_keep = 30`、`debounce_seconds = 60`。
- **CLI**
  - `s200 drive auth`：初回の認証。ユーザーが自分で実行する。
  - `s200 drive sync`：今すぐ1回同期する。確認用。
  - `s200 run`：`enabled` でトークンがあれば `DriveSync` を起動する。なければ、ログに「無効」と出すだけ。
- **API とアプリ**
  - `GET /api/drive` で同期の状態を返す。
  - SwiftUI の設定画面に「Google Drive：最終同期 11:25 ／ エラー内容」を1行出す。
- `.gitignore` に `.drive/` を追加する。

## ユーザー側の初期設定（README に手順を書く。所要10分ほど）
1. Google Cloud Console でプロジェクトを作り、Google Drive API を有効にする。
2. OAuth 同意画面を設定する（外部、スコープは `drive.file`）。
   - **「本番環境に公開」にする。** テスト中のままだと、トークンが7日で切れてしまう。`drive.file` は審査不要の権限なので、公開しても審査は入らない。
3. 認証情報で OAuth クライアント（デスクトップアプリ）を作り、JSON を `.drive/client_secret.json` に置く。
4. `! uv run s200 drive auth` を実行してブラウザで許可する。そのあと常駐プログラムを再起動する。

## 実装順
1. `export.py` ＋ テスト
2. `drive.py`（クライアント、`sync_once`、`DriveSync`）＋ テスト。偽の HTTP セッションを使う：
   - 2回目は更新になる
   - 404 なら作り直す
   - バックアップを世代管理する
   - 連続したイベントが1回のアップロードにまとまる
   - 失敗したら再試行する
3. `config` / `cli` / `web` の変更 ＋ テスト（`[drive]` の読み込み、`/api/drive`）
4. Swift 側：`DriveStatus` のデコードと設定画面の表示 ＋ Swift Testing
5. README を更新し、コミットする（テスト結果を記録する）
6. ユーザーが認証したら、`s200 drive sync` を実際に動かして確認し、常駐プログラムを再起動する

## 確認方法
- `.venv/bin/pytest`（web のテストはローカルポートを使うので、サンドボックス外で実行する）、`ruff check`、`xcodebuild test`
- 実際の Drive で確認すること：
  - `s200 drive sync` で、Drive に「体重ログ」フォルダと5つのファイルができる
  - スプレッドシートを開いて中身を確認する
  - 体重計に乗ると、60秒ほどでシートが更新される
  - アプリで記録を除外すると、`daily` から消える
  - 設定画面に最終同期時刻が出る
- Drive でファイルを消したあと、次の同期で作り直される

## 注意
- アップロードするのは体重とメモだけ。行き先は本人の Drive で、権限は `drive.file`（このアプリが作ったファイルだけ）。
- 秘密情報（`client_secret.json`、`token.json`）は `.drive/` に置き、git に入れない。
- 認証にはブラウザ操作とローカルポートが要るので、`s200 drive auth` はユーザーに実行してもらう。
