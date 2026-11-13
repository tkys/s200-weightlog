# Google Drive 連携

記録を自分の Google Drive に自動でアップロードします。設定しなくても記録やアプリは問題なく動きます。

## できるもの（マイドライブ/体重ログ/）

| ファイル | 中身 | 用途 |
|---|---|---|
| `weights`（スプレッドシート）/ `weights.csv` | 全記録。列は `id, datetime, date, weight_kg, trend_kg, status, reason, profile_id` | 閲覧、分析 |
| `daily`（スプレッドシート）/ `daily.csv` | 1 日 1 行。列は `date, weight_kg, trend_kg, count, note, tags`。`weight_kg` はその日最後の有効な記録 | 食事・歩数のデータと `date` で突き合わせる、AI に読ませる |
| `backups/weights-YYYY-MM-DD.sqlite3` | 1 日 1 回のデータベースのスナップショット（直近 30 個） | バックアップ |

- 最後の変更（記録・除外・メモ）から 60 秒待ってまとめてアップロードします
- スプレッドシートは毎回中身が入れ替わるだけで、URL は変わりません。スマホにブックマークできます
- 除外した記録は `weights` には `status` 付きで残り、`daily` の集計には入りません
- 権限は **`drive.file`**（このアプリが作ったファイルだけ）。Drive のほかのファイルは読めません

## 初期設定

Google Cloud で**自分用の** OAuth クライアントを作ります（10〜15 分）。

### 1. プロジェクトと API

1. [Google Cloud Console](https://console.cloud.google.com/) で新しいプロジェクトを作る
2. 「API とサービス → ライブラリ」で **Google Drive API** を有効にする

### 2. Google Auth Platform（OAuth 同意画面）

1. **ブランディング**：アプリ名、ユーザーサポートメール、デベロッパーの連絡先を入力
2. **対象**：ユーザーの種類は「外部」
3. **データアクセス**：「スコープを追加または削除」で `https://www.googleapis.com/auth/drive.file` を追加して保存
4. **クライアント**：「クライアントを作成」で種類を **デスクトップアプリ** にして作成し、JSON をダウンロード

### 3. 公開ステータスを決める

| | 本番環境に公開（おすすめ） | テスト中のまま |
|---|---|---|
| 認証の有効期間 | 取り消すまで有効 | **7 日で切れる**（毎週 `s200 drive auth` が必要） |
| 必要なもの | ホームページとプライバシーポリシーの URL | 「対象 → テストユーザー」に自分のアカウントを追加 |
| Google の審査 | 不要（`drive.file` は機密性の高いスコープではない） | 不要 |

**本番環境に公開するには**、ブランディングに次を入力しないと「アプリを公開」ボタンが押せません。

- アプリケーションのホームページ
- プライバシーポリシーのリンク
- 承認済みドメイン（上の 2 つの URL のドメイン。GitHub Pages なら `<ユーザー名>.github.io`）

このリポジトリの [`docs/`](.) には紹介ページ（`index.html`）とプライバシーポリシー（`privacy.html`）が入っています。
**フォークして自分の GitHub Pages で公開し、連絡先などを自分のものに書き換えて使ってください**（リポジトリの Settings → Pages → Branch: `main` / `/docs`）。

入力して保存したら、「対象 → アプリを公開 → 確認」で本番環境にします。
ロゴは設定しないでください（ロゴを入れると審査が必要になります）。

### 4. 認証

```bash
cp ~/Downloads/client_secret_*.json .drive/client_secret.json   # .drive/ は git 管理外
uv run s200 drive auth
```

ブラウザが開くので、アカウントを選んで許可します。
「このアプリは Google で確認されていません」と出たら「詳細 → （アプリ名）に移動」で進みます（自分で作った未審査のアプリなので想定どおりです）。
`.drive/token.json` ができれば完了です。

### 5. 有効にする

`config.toml` の `[drive]` を `enabled = true` にして、1 回手動で上げてから常駐を再起動します。

```bash
uv run s200 drive sync        # uploaded 体重ログ/weights ... と出れば OK
scripts/launchd.sh restart
```

`config.toml` の `[drive]` では、フォルダ名（`folder`）、バックアップを残す数（`backup_keep`）、待ち時間（`debounce_seconds`）も変えられます。

## 状態の確認

- アプリの設定（⌘,）の「Google Drive」の行：最終同期の時刻、またはエラー
- `curl http://127.0.0.1:8200/api/drive`
- `logs/s200.log` の `drive sync:` の行

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `invalid_grant` / 認証エラー | 認証が切れた・取り消された。テスト中のまま 7 日経った場合も同じ。`uv run s200 drive auth` → `scripts/launchd.sh restart` |
| 「アプリを公開」が押せない | ブランディングのホームページ・プライバシーポリシー・承認済みドメインが未入力 |
| `access_denied`（テスト中） | 「対象 → テストユーザー」に自分のアカウントが入っていない |
| ネットが切れていた | 何もしなくてよい。1〜30 分間隔で再試行し、つながったらまとめて上がる |
| Drive でファイルを消した | 次の同期で作り直される（URL は変わる） |
| 最初からやり直したい | `.drive/state.json` を消すと、次の同期で新しいフォルダに作り直す |

## 無効にする・アクセスを取り消す

- `config.toml` で `enabled = false` → `scripts/launchd.sh restart`
- Google 側のアクセスは [サードパーティ接続の管理](https://myaccount.google.com/connections) から取り消せます
- ローカルの認証情報は `.drive/` を消せば消えます
