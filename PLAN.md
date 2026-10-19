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
