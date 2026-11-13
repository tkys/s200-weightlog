# Xiaomi S200 の BLE プロトコル

S200 は計量が確定すると、暗号化した計測値を BLE の広告（advertisement）に載せて数十秒間くり返し発信します。
本プロジェクトはこの広告を受け取るだけで、体重計には接続しません。実装は [`s200/mibeacon.py`](../s200/mibeacon.py)。

## 広告の形式（MiBeacon v5）

- Service Data の UUID `0xFE95` に載る（Advertised Service UUID の一覧には入らない）
- 先頭のバイト列：

| オフセット | 長さ | 内容 |
|---|---|---|
| 0 | 2 | Frame control（LE）。bit3 暗号化、bit4 MAC あり、bit5 capability あり、bit6 object あり、bit12–15 バージョン（5） |
| 2 | 2 | Product id（LE） |
| 4 | 1 | Frame counter（新しいイベントごとに +1） |
| 5 | 6 | MAC（逆順。bit4 のとき） |
| | 1 | Capability（bit5 のとき） |
| | n | 暗号化された object（bit6 のとき） |
| 末尾 −7 | 3 | 拡張カウンタ |
| 末尾 −4 | 4 | MIC（認証タグ） |

### Product id

| id | 備考 |
|---|---|
| `0x4DCC` | `xiaomi.scales.ms114`。本プロジェクトの実機で確認 |
| `0x4C04` / `0x4DCB` / `0x45C9` | xiaomi-ble などで S200 系として扱われている id |

## 復号（AES-128-CCM）

- 鍵：体重計ごとの **bindkey**（BLE KEY、16 バイト）。Xiaomi Home でペアリング後、Xiaomi のクラウドから取得する
- nonce（12 バイト）= MAC 逆順（6）+ data[2:5]（product id と counter, 3）+ 拡張カウンタ（3）
- AAD = `0x11`、タグ長 4 バイト
- 復号結果は TLV の並び：`type u16 LE | length u8 | value`

## Object

| type | 長さ | 内容 |
|---|---|---|
| `0x4E16` | 9 | 体重。`profile_id u8 | weight u32 LE（kg × 100。0 は降りた） | unix time u32 LE`（体重計の時計） |
| `0x6623` | 1 | 状態通知。約 50 分ごとに送られる。体重ではないので無視する |

- 同じ計測が何度も届くので、`(時刻, profile_id)` で重複を除く
- 体重計の時計は Mac より 1〜2 分遅れていることがある
- 体脂肪などの電極は無く、体重のみ

## 受信側の注意（macOS）

- **CoreBluetooth は相手の MAC アドレスを隠す**（端末ごとの UUID になる）。nonce に MAC が要るので、設定で MAC を与える。広告に MAC が入っているフレームではそれも使う
- **bleak の `service_uuids` フィルタを付けると受信できない**。macOS ではフィルタが Advertised Service UUID にしか効かず、S200 は `0xFE95` を Service Data にしか載せないため。フィルタ無しで受けて、コールバック内で絞り込む
- **スマホの Xiaomi Home が Bluetooth を使える状態だと、スマホが先に計測値を受け取り、Mac に届かないことがある**
- **Mac がスリープすると受信が止まる**。常駐は `caffeinate -i` で起動する
- 体重計は乗られていない間はほぼ眠っていて（50 分ごとの状態通知を除く）、乗ると目を覚まして連続で広告を出す

## 接続（GATT）方式について

TOKEN（24 桁）を使って GATT で接続すると、本体メモリに残っている未取得の記録も読めます。
ただし接続は体重計を起こし続けて電池を消耗させ、固まる事例もあるため、本プロジェクトでは使っていません。

## 参考実装

- [Bluetooth-Devices/xiaomi-ble](https://github.com/Bluetooth-Devices/xiaomi-ble) — Home Assistant 公式のパーサ（object `0x4E16`）。テストの実パケットと bindkey を本プロジェクトのテストでも使用
- [faraga1/xiaomi-scale-s200-ble](https://github.com/faraga1/xiaomi-scale-s200-ble) — プロトコルの全容
- [zoup0512/BleWeightScale](https://github.com/zoup0512/BleWeightScale) — Android での広告復号
- [kfirmaymon84/esp32-mirror-weight-tracker](https://github.com/kfirmaymon84/esp32-mirror-weight-tracker) — ESP32、GATT 方式
- [PiotrMachowski/Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) — bindkey の取得
