# S200 体重計 BLE 調査メモ (2026-10-19)

## 前提の訂正
- 「HUAWEI S200」という体重計は見つからない。HUAWEI の現行は Scale 3 / 3 Pro（Hagrid/WSP 暗号化 GATT、CAK/C1/C2 が必要で難度高）。
- 「S200」は **Xiaomi スマート体重計 S200（MJTZC02YM / BLE名 yunmai.scales.ms106 等）** の可能性が高い。→ **2026-10-19 ユーザー確認済み: Xiaomi S200**。

## Xiaomi S200 のプロトコル要点
- 広告: Service Data UUID `0xFE95`（MiBeacon v4/v5）。product id = service data の byte 2–3 LE（`0x4C04` / `0x4DCB` / `0x45C9`、**実機 xiaomi.scales.ms114 は `0x4DCC`**（2026-10-19 確認、受信・復号成功）。macOS では scan に service_uuids フィルタを付けると受信できない。iPhone の Bluetooth が ON だと受信できなかった）。
- 計量確定時にだけ object `0x4E16` を **AES-128-CCM 暗号化**で送出。復号に **bindkey (BLE KEY, 32hex)** が必要。
  - nonce = MAC逆順(6) + payload[2..5](3) + 拡張カウンタ(3)、AAD=`0x11`、tag 4byte
  - 復号後 `0x4E16` (9 bytes): `profile_id u8 | weight u32 LE (kg×100, 0=降りた) | unix ts u32 LE`
- 体脂肪電極なし（体重のみ）。
- GATT 接続 + TOKEN(24hex) で本体メモリの未取得記録も取れるが、接続はスケールを起こし続け電池消耗/固まる事例あり。**パッシブ受信推奨**。
- bindkey/TOKEN/MAC は Xiaomi Home でペアリング後に PiotrMachowski/Xiaomi-cloud-tokens-extractor で取得。
- macOS(CoreBluetooth) は MAC を隠すため、MAC は手入力（抽出ツールの出力 or アイドル広告内の MAC）。

## 参考実装
- Bluetooth-Devices/xiaomi-ble (HA 公式パーサ, obj4e16, テストに実パケット+bindkey)
- faraga1/xiaomi-scale-s200-ble (プロトコル全容, scale_reader.py, webhook)
- zoup0512/BleWeightScale (Android, 広告復号, フォーマット表)
- kfirmaymon84/esp32-mirror-weight-tracker (ESP32, GATT 方式)
- HA Xiaomi BLE 統合 (2026.1〜 S200 パッシブ対応)
