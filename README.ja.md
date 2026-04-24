# SmartMat Light Rescue Server

[繁體中文](README.md) · [English](README.en.md) · **日本語**

**2025-09-30 にサービス終了した** [SmartMat Light](https://service.lite.smartmat.io/) を自宅サーバーで蘇らせるプロジェクトです。デバイスの改造は不要 — `measure.lite.smartmat.io` の DNS 応答をこのサーバーに向けるだけで、既存デバイスがそのまま動き続けます。

> 本家は [@kitazaki さんの Qiita 記事](https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04) の逆解析を元にしています。原著者は Raspberry Pi を Wi-Fi AP 化して Python / Node.js / Node-RED サーバーを立てる方式。本プロジェクトは **NAS + Docker (macvlan)** 構成にし、家の Wi-Fi をそのまま使えるようにしました。

## 機能

- デバイスが必要とする 4 エンドポイント (`/i`, `/s`, `/sd`, `/m`) を実装
- 測定データを SQLite に保存 (weight / battery / rssi / timestamps)
- 複数デバイス対応、`device_id` で識別
- dnsmasq コンテナ内蔵 — ホスト単位の DNS 上書きに対応しないルーター (TP-Link Deco など) でも動作
- HTML ダッシュボードでリアルタイム監視
- JSON API (`/devices`, `/measurements`) で他システムと連携可能
- **MQTT + Home Assistant 自動検出**対応 — 各 SmartMat に 4 個の sensor (weight / battery / rssi / last_seen) が自動で出現

## 構成

```
 SmartMat デバイス
      │  家の Wi-Fi に接続
      ▼
 ルーター (DHCP で NAS の dnsmasq IP を DNS として配布)
      │
      ├─── DNS 問い合わせ ──▶ dnsmasq container (NAS macvlan IP A, port 53)
      │                          └─ measure.lite.smartmat.io → IP B
      │
      └─── HTTP POST ──────▶ smartmat container (NAS macvlan IP B, port 80)
                                 ├─ stdlib HTTP server
                                 ├─ SQLite /data/smartmat.db
                                 └─ MQTT publish → Home Assistant
```

両コンテナは Docker **macvlan** で LAN 上に独自 IP を持つので、NAS ホストの 80 / 53 ポートを占有しません。

## デプロイ手順 (Synology NAS の例)

### 前提

- NAS に Docker / Container Manager がある
- macvlan ネットワークを作成済み (この compose は `VBR-LAN1` という名前を想定)
- ルーターで DHCP が配布する DNS を変更できる

### 設定

```bash
git clone https://github.com/<YOU>/smartmat-rescue.git /volume1/docker/smartmat
cd /volume1/docker/smartmat
cp .env.example .env
vi .env      # 必須: DNSMASQ_IP / SMARTMAT_IP / DNS_TARGET_IP。任意: MQTT_*
```

**IP の選び方：**
- `DNSMASQ_IP`, `SMARTMAT_IP`: **DHCP 範囲外**の LAN IP を 2 つ
- `DNS_TARGET_IP`: 本番 = `SMARTMAT_IP`。開発中は Windows の IP に一時的に変更可能

### 起動

```bash
sudo docker compose up -d --build
sudo docker compose logs -f
```

成功時のログ例：
```
smartmat     | SmartMat fake API on :80 (db=/data/smartmat.db, poll=300s)
smartmat-dns | dnsmasq ... started
smartmat     | MQTT connected to <your_HA_ip>:1883   (MQTT 設定時)
```

### ルーター側で DHCP の DNS を変更

DHCP が配布する **Primary DNS** を `DNSMASQ_IP` に。Secondary は `8.8.8.8` を入れておく (NAS 停止時も他のデバイスはインターネット接続可能)。

- **TP-Link Deco**: More → Advanced → **DHCP Server** (IPv4/DNS Server ではない — それは Deco 自身の上流 DNS)
- ASUS/Merlin: LAN → DHCP Server
- OpenWrt: DHCP and DNS → DHCP option `6,<DNSMASQ_IP>`

デバイスが次に Wi-Fi に再接続したタイミング (通常 ~5 分) で新 DNS を取得。電源を入れ直せば即時反映。

### 動作確認

```bash
# LAN 内のどこからでも:
nslookup measure.lite.smartmat.io <DNSMASQ_IP>    # <SMARTMAT_IP> が返れば OK
curl http://<SMARTMAT_IP>/healthz                  # {"status":"ok"}
```

ブラウザで `http://<SMARTMAT_IP>/` を開くとダッシュボード。

## MQTT / Home Assistant

`.env` で MQTT 設定：
```
MQTT_HOST=192.168.xx.xx
MQTT_USER=xxx
MQTT_PASS=xxx
```

サーバー再起動後、HA (`Settings → Devices & Services → MQTT`) に SmartMat が自動で追加されます。各デバイスに 4 つの sensor：
- `sensor.smartmat_<id>_weight` (g)
- `sensor.smartmat_<id>_battery` (%)
- `sensor.smartmat_<id>_rssi` (dBm)
- `sensor.smartmat_<id>_last_seen` (timestamp)

MQTT トピック: `smartmat/<id>/weight` など、retained。

## ハマりどころ

以下 2 つが**両方揃っていないと**デバイスは `/s` で止まり続け、`/sd` / `/m` に進みません：

### 1. DNS TTL を ≥ 1 にする

dnsmasq の `--address=` や `host-record` のデフォルト TTL は **0**。ESP8266 の HTTPClient は TTL=0 を受け取ると次回の DNS 解決で失敗します。本プロジェクトは `local-ttl=60 auth-ttl=60` + host-record 末尾に TTL=60 を明示。@kitazaki さんも同じ罠に遭遇、記事に記録。

### 2. HTTP レスポンスを envoy クラウドと byte-for-byte 一致させる

HTTP 仕様上は余裕があるのに、ESP8266 の parser が厳格です：

- ヘッダ順：`Date → Content-Type → Content-Length → Connection → x-envoy-upstream-service-time → server`
- 大小文字：`server: envoy` (小文字)、`Content-Type` (Title-Case)
- **末尾空白禁止** (Python の `version_string()` はデフォルトで空白を付けるので override が必要)
- `/i` は `""` (JSON 空文字列) + `application/json; charset=utf-8` を返す。`OK` 平文ではダメ

`app/main.py` の `_send_bytes` は Python の `send_response()` / `send_header()` を使わず、生バイト列を直接 socket に書いています。

技術詳細と UART デバッグログの抜粋は [docs/PROTOCOL.md](docs/PROTOCOL.md) を参照。

## プロジェクト構成

```
smartmat-rescue/
├── app/
│   ├── main.py              # stdlib HTTP server + dashboard + JSON API
│   ├── mqtt_bridge.py       # MQTT publish + HA discovery
│   └── requirements.txt     # paho-mqtt のみ
├── dnsmasq/
│   └── Dockerfile           # alpine + dnsmasq (multi-arch)
├── scripts/
│   ├── dev.ps1              # Windows dev server
│   ├── setup-dev-port80.ps1 # Windows port 80 forward (管理者)
│   ├── teardown-dev-port80.ps1
│   ├── simulate_device.py   # デバイス呼び出しのシミュレーター
│   └── raw_proxy.py         # TCP レベルデバッグ用 proxy
├── docs/
│   └── PROTOCOL.md          # デバイス API プロトコル参考資料
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Windows 開発モード (任意)

シミュレーターで反復開発：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\scripts\dev.ps1                                    # port 8080
# 別ウィンドウで:
.venv\Scripts\python.exe scripts\simulate_device.py --loop --interval 10
```

実機を Windows (NAS ではなく) に向ける E2E テスト：

1. 管理者 PowerShell: `.\scripts\setup-dev-port80.ps1` (port 80 → 8080 と firewall 許可)
2. NAS の `.env` で `DNS_TARGET_IP=<Windows の IP>` に一時変更、`docker compose up -d dnsmasq`
3. Windows: `.\scripts\dev.ps1`
4. 終了時は NAS の `.env` を元に戻す。portproxy は永続化されているので、不要なら `teardown-dev-port80.ps1` で削除。

## クレジット

- [@kitazaki](https://github.com/kitazaki) — SmartMat API の逆解析、TTL バグの発見、UART デバッグログ の共有
- [SmartMat / infolens Inc.](https://www.smartmat.io/) — オリジナルデバイス

## ライセンス

Apache License 2.0 — [kitazaki/smartmat](https://github.com/kitazaki/smartmat) と同じ。

**本プロジェクトは非公式・サードパーティによる救済プロジェクトです。infolens 株式会社との関連・支援・承認関係は一切ありません。**
