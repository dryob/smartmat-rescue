# SmartMat Lite Rescue Server

**繁體中文** · [English](README.en.md) · [日本語](README.ja.md)

為 [SmartMat Lite](https://service.lite.smartmat.io/) 自建的本地替代雲端伺服器，在官方服務 **2025-09-30 終止後**讓裝置繼續運作。裝置不需改機，只要把 `measure.lite.smartmat.io` 的 DNS 導到這台服務就接上了。

> 本專案基於 [@kitazaki 的 Qiita 文章](https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04)。原作者示範用 Raspberry Pi 當 Wi-Fi AP + Python/Node.js/Node-RED server。此版改用 **NAS + Docker (macvlan)**，讓家裡沿用現有 Wi-Fi 不用另外架 AP。

## 功能

- **4 個裝置端點** (`/i`, `/s`, `/sd`, `/m`)，回應格式 byte-by-byte 對齊原 envoy cloud (詳見 [Gotchas](#gotchas))
- **SQLite 儲存**所有測量 (`weight / battery / rssi / timestamps`)
- **多台裝置**共用同一台 server，用 device id 區分
- **內建 dnsmasq 容器**，解決 TP-Link Deco 等不支援單域名 DNS 覆寫的 router
- **HTML Dashboard** 即時看裝置狀態
- **JSON API** (`/devices`, `/measurements`) 給其他系統用
- **MQTT + Home Assistant auto-discovery**，HA 自動跳出每台 SmartMat 的 sensor (weight / battery / rssi / last_seen)

## 架構

```
 SmartMat 裝置
      │  連家中 Wi-Fi
      ▼
 Router (DHCP 派 DNS = NAS 的 dnsmasq IP)
      │
      ├─── DNS 查詢 ───▶ dnsmasq container  (NAS macvlan IP A, port 53)
      │                     └─ measure.lite.smartmat.io → IP B
      │
      └─── HTTP POST ──▶ smartmat container (NAS macvlan IP B, port 80)
                            ├─ FastAPI-like stdlib server
                            ├─ SQLite /data/smartmat.db
                            └─ MQTT publish → Home Assistant
```

兩個容器用 Docker **macvlan** 各拿一個 LAN IP，不搶 NAS host 的 80/53 port。

## 快速佈署 (Synology NAS 為例)

### 前置

- NAS 有 Docker / Container Manager
- 已建好 macvlan 網路 (本專案 compose 預期名稱 `VBR-LAN1`，不同請修改)
- Router 支援改 DHCP 推出的 DNS

### 設定

```bash
git clone https://github.com/<YOU>/smartmat-rescue.git /volume1/docker/smartmat
cd /volume1/docker/smartmat
cp .env.example .env
vi .env      # 必填: DNSMASQ_IP / SMARTMAT_IP / DNS_TARGET_IP; 選填: MQTT_*
```

**IP 挑選：**
- `DNSMASQ_IP`, `SMARTMAT_IP`: 挑兩個 **DHCP 範圍外**的 LAN IP
- `DNS_TARGET_IP`: 正式部署 = `SMARTMAT_IP`, dev 時可指向 Windows 本機 IP

### 啟動

```bash
sudo docker compose up -d --build
sudo docker compose logs -f
```

看到下面訊息代表 OK：
```
smartmat     | SmartMat fake API on :80 (db=/data/smartmat.db, poll=300s)
smartmat-dns | dnsmasq ... started
smartmat     | MQTT connected to <your_HA_ip>:1883   (若有設 MQTT)
```

### Router 改 DNS

把 DHCP Server 推出的 **Primary DNS** 改成 `DNSMASQ_IP`，Secondary 設 `8.8.8.8` (NAS 掛掉時家裡其他裝置還能上網)。

- **TP-Link Deco**: More → Advanced → **DHCP Server** (不是 IPv4/DNS Server，那是 Deco 自己對外用的)
- ASUS/Merlin: LAN → DHCP Server
- OpenWrt: DHCP and DNS → DHCP option `6,<DNSMASQ_IP>`

裝置下次醒來 (~5 分鐘) 就會打到新 server。拔插電可以立即觸發。

### 驗證

```bash
# 從任何 LAN 裝置:
nslookup measure.lite.smartmat.io <DNSMASQ_IP>    # 應回 <SMARTMAT_IP>
curl http://<SMARTMAT_IP>/healthz                  # 應回 {"status":"ok"}
```

打開 `http://<SMARTMAT_IP>/` 看 dashboard。

## MQTT / Home Assistant

`.env` 裡填 MQTT broker 資訊：
```
MQTT_HOST=192.168.xx.xx
MQTT_USER=xxx
MQTT_PASS=xxx
```

server 重啟後 HA (`Settings → Devices & Services → MQTT`) 會自動出現每台 SmartMat，各 4 個 sensor：
- `sensor.smartmat_<id>_weight` (g)
- `sensor.smartmat_<id>_battery` (%)
- `sensor.smartmat_<id>_rssi` (dBm)
- `sensor.smartmat_<id>_last_seen` (timestamp)

MQTT topic: `smartmat/<id>/weight` 等，retained。

## Gotchas (救命關鍵)

本作者實測，以下兩點**必須同時正確**，否則裝置 POST `/s` 可以成功但永遠不會進到 `/sd` 和 `/m`（5 個 SmartMat 全卡住）：

### 1. DNS TTL 必須 ≥ 1

預設 dnsmasq 對 `--address=` / `host-record` 的 TTL 是 **0**，ESP8266 的 HTTPClient 看到 TTL=0 會在第二次 DNS 查詢時失敗。本專案 dnsmasq 參數已設 `local-ttl=60 auth-ttl=60` + host-record 末欄 60。

原作者的文章也踩到這個坑並記錄。

### 2. HTTP response 必須 byte-for-byte 對齊 real envoy cloud

這不是 HTTP spec 的要求 — 是 ESP8266 firmware 的 HTTP parser 太嚴。具體：

- Header 順序：`Date → Content-Type → Content-Length → Connection → x-envoy-upstream-service-time → server`
- Case：`server: envoy` (小寫 s)、`Content-Type` (Title-Case)
- **不能有尾空格** (Python 預設 `version_string()` 會加空格要 override)
- `/i` 必須回 `""` (JSON 空字串) + `application/json; charset=utf-8`，不能回 `OK` plain text

本專案 `app/main.py` 的 `_send_bytes` 繞過 Python `send_response()` / `send_header()` 的 convention，直接寫 raw bytes 到 socket。

完整技術細節與裝置 UART debug log 見 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

## 專案結構

```
smartmat/
├── app/
│   ├── main.py              # stdlib HTTP server + dashboard + JSON API
│   ├── mqtt_bridge.py       # MQTT publish + HA discovery
│   └── requirements.txt     # paho-mqtt only
├── dnsmasq/
│   └── Dockerfile           # alpine + dnsmasq (多架構支援)
├── scripts/
│   ├── dev.ps1              # Windows 本機 dev server
│   ├── setup-dev-port80.ps1 # Windows port 80 forward (admin)
│   ├── teardown-dev-port80.ps1
│   ├── simulate_device.py   # 模擬裝置呼叫測 server
│   └── raw_proxy.py         # TCP 層 debug 工具 (看裝置送什麼)
├── docs/
│   └── PROTOCOL.md          # API 協定技術細節 (來源: @kitazaki 文章)
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Windows 本機開發（optional）

要改 code 用 simulator 迭代：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\scripts\dev.ps1                                    # port 8080
# 另開視窗:
.venv\Scripts\python.exe scripts\simulate_device.py --loop --interval 10
```

要讓真實裝置打 Windows (而不是 NAS) 做 end-to-end 測：

1. Admin PowerShell: `.\scripts\setup-dev-port80.ps1` (port 80 → 8080 + firewall)
2. NAS 的 `.env` 暫時改 `DNS_TARGET_IP=<你的 Windows IP>`; `docker compose up -d dnsmasq`
3. Windows: `.\scripts\dev.ps1`
4. 結束時改回原值，`teardown-dev-port80.ps1` 可選 (portproxy 持久化)

## 致謝

- [@kitazaki](https://github.com/kitazaki) 的 Qiita 文章：逆向 SmartMat API + 發現 TTL 坑 + 提供 debug log 
- [SmartMat / infolens Inc.](https://www.smartmat.io/)：原裝置硬體

## License

Apache License 2.0 — 與 [kitazaki/smartmat](https://github.com/kitazaki/smartmat) 一致。

**This is an unofficial third-party rescue project. Not affiliated with, endorsed by, or supported by infolens Inc.**
