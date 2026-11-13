# 設計

## 全体像

```
 S200 ─BLE─▶ scanner.watch ─▶ mibeacon.decrypt_objects ─▶ WeightApp.ingest ─▶ Store (SQLite)
                                                              │
                                                              ├─▶ EventHub ─▶ SSE /api/stream ─▶ WeightLog.app
                                                              │            └─▶ DriveSync ─▶ Google Drive
                                                              └─ analysis（トレンド・外れ値・ペース・節目）
```

- **Python の常駐（`s200 run`）が中心**。受信・復号・保存・分析・API・Drive アップロードはすべてここで行い、pytest で検証する
- **SwiftUI アプリは表示とリアクションだけ**を担当し、ローカル API を読む。ほかのクライアント（スマホのショートカット、スクリプトなど）も同じ API を使える
- 常駐は launchd の LaunchAgent。`caffeinate -i` 経由で起動し、Mac のアイドルスリープを止める

## Python パッケージ（`s200/`）

| モジュール | 役割 |
|---|---|
| `mibeacon.py` | MiBeacon v5 の解析と AES-CCM 復号（[protocol.md](protocol.md)） |
| `scanner.py` | bleak で受信。体重計が目を覚ましたら `scale awake` をログ。10 分間フレームが来なければスキャナを作り直す。1 時間ごとに受信数を `heartbeat` でログ |
| `store.py` | SQLite。`PRAGMA user_version` でスキーマを移行。スレッド間で 1 接続を `RLock` で共有 |
| `analysis.py` | 純粋関数：トレンド、外れ値判定、乗り直しの統合、ペース、到達予定日、連続記録、節目、ひとことコメント |
| `web.py` | `ThreadingHTTPServer` による JSON API と SSE。`EventHub` が変更を各購読者に配る |
| `export.py` | Drive 向け CSV（純粋関数） |
| `drive.py` | Drive API v3 の最小クライアント、同期処理、バックグラウンドの同期スレッド |
| `config.py` / `cli.py` | `config.toml` の読み込み、`scan` / `run` / `drive auth` / `drive sync` |

## データベース（`weights.sqlite3`）

```sql
readings(id, ts, profile_id, weight_kg, received_at,
         status TEXT  -- 'ok' | 'outlier' | 'merged'
         reason TEXT, -- 除外の理由
         manual INT,  -- 1 = ユーザーが手動で切り替えた（自動判定で上書きしない）
         UNIQUE(ts, profile_id))
day_notes(date TEXT PRIMARY KEY, note TEXT, tags TEXT /* JSON 配列 */)
settings(key TEXT PRIMARY KEY, value TEXT /* JSON */)  -- height_cm, goal_kg, start_kg
```

記録は削除せず、除外は `status` で表します。

## 分析

| 項目 | 方法 |
|---|---|
| トレンド体重 | 時間を考慮した指数移動平均。`α = 1 − exp(−Δt / 10 日)`。`ok` の記録だけを使う |
| 外れ値 | `ok` の記録が 5 件以上たまってから有効。トレンドとの差が `max(2.0 kg, 4 × MAD)` を超えたら `outlier`。MAD は本人の日々のばらつき |
| 乗り直し | 10 分以内の記録は最後の 1 件を残し、それ以前を `merged` にする |
| ペース | 直近 14 日のトレンドを最小二乗で直線近似（kg/週） |
| 目標到達予定日 | (トレンド − 目標) ÷ ペース。減っていなければ出さない |
| 節目 | 最安値の更新、スタートから 1 kg 減るごと、連続 7/30/100/365 日、目標達成 |

`manual = 1` の記録は自動判定の対象外です。

## HTTP API（`127.0.0.1:8200`）

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/summary` | 最新値、前回比・スタート比・7 日のトレンド変化、トレンド、ペース、予定日、BMI、連続日数、コメント、節目 |
| GET | `/api/readings?since=<unix>` | 全記録（`status`・`reason`・各時点の `trend_kg` 付き） |
| PATCH | `/api/readings/{id}` | `{"status": "ok" \| "outlier"}`。手動の除外・復帰（`manual = 1`） |
| GET | `/api/notes?from=&to=` | 日ごとのメモ |
| GET / PUT | `/api/notes/{YYYY-MM-DD}` | `{"note": "...", "tags": [...]}`。空にすると削除 |
| GET / PUT | `/api/settings` | `height_cm` / `goal_kg` / `start_kg`（数値か null） |
| GET | `/api/drive` | Drive 同期の状態（`enabled`, `last_success`, `last_error`） |
| GET | `/api/stream` | SSE。`event: reading`（新しい記録と summary）、`event: changed`（編集後の summary）。15 秒ごとに ping |

ローカルホスト専用で、認証はありません。

## Google Drive 同期

- 権限は `drive.file`（このアプリが作ったファイルだけ）。OAuth のデスクトップアプリ方式で、更新トークンを `.drive/token.json`（権限 600）に保存
- `DriveSync` スレッドが `EventHub` を購読し、最後の変更から 60 秒後にまとめてアップロードする。起動時にも 1 回、日付が変わったらバックアップ
- スプレッドシートは CSV を変換付きで同じファイル ID に上書き（URL が変わらない）。ファイル ID は `.drive/state.json` に保存し、Drive で消された・ゴミ箱に入ったファイルは作り直す
- 失敗したら 1 分から最大 30 分まで間隔を延ばして再試行する。**記録は止めない**

## Mac アプリ（`app/`）

- XcodeGen（`project.yml`）、macOS 15、Swift 6、SwiftUI + Swift Charts。App Sandbox なし、ad-hoc 署名
- `AppModel`（`@Observable`）が状態を一元管理。起動時に API を読み、SSE を購読して切断時は自動で再接続
- 画面：ホーム（最新値・指標・グラフ）／カレンダー（メモ）／記録（一覧・除外）、メニューバー、設定
- 新しい記録が届くと：数字のカウントアップ → 差分 → コメント → 節目なら紙吹雪 → ウィンドウが裏なら通知

## テスト

- `uv run pytest`：復号（実パケット）、移行、分析の各パターン、API と SSE（実ソケット）、スキャナ（偽の BleakScanner）、Drive（メモリ上の偽 Drive）
- `xcodebuild test`：JSON のデコード、SSE の解析、表示用の整形、カレンダー計算
