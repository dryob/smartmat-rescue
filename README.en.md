# SmartMat Lite Rescue Server

[繁體中文](README.md) · **English** · [日本語](README.ja.md)

A self-hosted cloud replacement for [SmartMat Lite](https://service.lite.smartmat.io/) weight-measuring auto-reorder mats, keeping them working **after the official service shutdown on 2025-09-30**. No device modification required — just redirect the DNS of `measure.lite.smartmat.io` to this server.

> Based on the excellent reverse-engineering work in [@kitazaki's Qiita article](https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04). The original uses a Raspberry Pi as a Wi-Fi access point with Python / Node.js / Node-RED servers. This project uses **NAS + Docker (macvlan)** so you can keep using your existing home Wi-Fi without setting up a separate AP.

## Features

- **4 device endpoints** (`/i`, `/s`, `/sd`, `/m`) with byte-for-byte envoy-compatible responses (see [Gotchas](#gotchas))
- **SQLite storage** for all measurements (weight / battery / rssi / timestamps)
- **Multi-device** support — all SmartMats share one server, distinguished by device id
- **Built-in dnsmasq container** to solve the DNS override problem for routers like TP-Link Deco that don't support per-hostname DNS rewriting
- **HTML Dashboard** for live device status
- **JSON API** (`/devices`, `/measurements`) for integration
- **MQTT + Home Assistant auto-discovery** — each SmartMat appears automatically with 4 sensors (weight / battery / rssi / last_seen)

## Architecture

```
 SmartMat device
      │  joins your home Wi-Fi
      ▼
 Router (DHCP hands out DNS = NAS's dnsmasq IP)
      │
      ├─── DNS query ──▶ dnsmasq container  (NAS macvlan IP A, port 53)
      │                     └─ measure.lite.smartmat.io → IP B
      │
      └─── HTTP POST ──▶ smartmat container (NAS macvlan IP B, port 80)
                            ├─ stdlib HTTP server
                            ├─ SQLite /data/smartmat.db
                            └─ MQTT publish → Home Assistant
```

Both containers use Docker **macvlan**, each taking its own LAN IP — no port conflicts with the NAS host (port 80 / 53 stay free on the host).

## Quick Deploy (Synology NAS example)

### Prerequisites

- NAS with Docker / Container Manager
- macvlan network already created (this compose expects name `VBR-LAN1` — adjust if different)
- A router that lets you change the DHCP-advertised DNS

### Configure

```bash
git clone https://github.com/<YOU>/smartmat-rescue.git /volume1/docker/smartmat
cd /volume1/docker/smartmat
cp .env.example .env
vi .env      # required: DNSMASQ_IP / SMARTMAT_IP / DNS_TARGET_IP; optional: MQTT_*
```

**Picking IPs:**
- `DNSMASQ_IP`, `SMARTMAT_IP`: two LAN IPs **outside the DHCP pool**
- `DNS_TARGET_IP`: in production = `SMARTMAT_IP`; during dev can point at your Windows dev machine

### Start

```bash
sudo docker compose up -d --build
sudo docker compose logs -f
```

Expected success lines:
```
smartmat     | SmartMat fake API on :80 (db=/data/smartmat.db, poll=300s)
smartmat-dns | dnsmasq ... started
smartmat     | MQTT connected to <your_HA_ip>:1883   (if MQTT configured)
```

### Change router DHCP DNS

Change the DHCP-advertised **Primary DNS** to `DNSMASQ_IP`, keep Secondary = `8.8.8.8` (so other devices still have DNS if the NAS goes down).

- **TP-Link Deco**: More → Advanced → **DHCP Server** (NOT IPv4/DNS Server, which is just Deco's own upstream)
- ASUS/Merlin: LAN → DHCP Server
- OpenWrt: DHCP and DNS → DHCP option `6,<DNSMASQ_IP>`

Devices will pick up the new DNS next time they reassociate (power-cycle to force immediately).

### Verify

```bash
# from any LAN client:
nslookup measure.lite.smartmat.io <DNSMASQ_IP>    # should return <SMARTMAT_IP>
curl http://<SMARTMAT_IP>/healthz                  # should return {"status":"ok"}
```

Open `http://<SMARTMAT_IP>/` for the dashboard.

## MQTT / Home Assistant

In `.env` set MQTT broker info:
```
MQTT_HOST=192.168.xx.xx
MQTT_USER=xxx
MQTT_PASS=xxx
```

After server restart, HA (`Settings → Devices & Services → MQTT`) will auto-discover each SmartMat with 4 sensors:
- `sensor.smartmat_<id>_weight` (g)
- `sensor.smartmat_<id>_battery` (%)
- `sensor.smartmat_<id>_rssi` (dBm)
- `sensor.smartmat_<id>_last_seen` (timestamp)

MQTT topic pattern: `smartmat/<id>/weight` etc., retained.

## Gotchas

Two things **must both be correct** for devices to progress past the initial `/s` call. If either is off, the device can POST `/s` successfully but will never follow up with `/sd` or `/m`:

### 1. DNS TTL must be ≥ 1

dnsmasq defaults to TTL=0 for `--address=` / `host-record` responses. ESP8266's HTTPClient fails on subsequent DNS resolution if TTL=0. This project sets `local-ttl=60 auth-ttl=60` + explicit TTL in host-record. @kitazaki hit this same bug and documented it.

### 2. HTTP response must byte-for-byte match the real envoy cloud

Not an HTTP spec requirement — ESP8266's HTTP parser is strict about:

- Header order: `Date → Content-Type → Content-Length → Connection → x-envoy-upstream-service-time → server`
- Case: `server: envoy` (lowercase s), `Content-Type` (Title-Case)
- **No trailing spaces** (Python's default `version_string()` adds one — must override)
- `/i` must return `""` (JSON empty string) with `application/json; charset=utf-8`, NOT plain text `OK`

`app/main.py`'s `_send_bytes` bypasses Python's `send_response()` / `send_header()` conventions and writes raw bytes to the socket.

Full technical detail and device UART debug log excerpts in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Project Layout

```
smartmat-rescue/
├── app/
│   ├── main.py              # stdlib HTTP server + dashboard + JSON API
│   ├── mqtt_bridge.py       # MQTT publish + HA discovery
│   └── requirements.txt     # paho-mqtt only
├── dnsmasq/
│   └── Dockerfile           # alpine + dnsmasq (multi-arch)
├── scripts/
│   ├── dev.ps1              # Windows local dev server
│   ├── setup-dev-port80.ps1 # Windows port 80 forward (admin)
│   ├── teardown-dev-port80.ps1
│   ├── simulate_device.py   # device call simulator
│   └── raw_proxy.py         # TCP-level debug proxy
├── docs/
│   └── PROTOCOL.md          # device API protocol reference
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Windows Dev (optional)

To iterate on server code with a simulator:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\scripts\dev.ps1                                    # port 8080
# in another window:
.venv\Scripts\python.exe scripts\simulate_device.py --loop --interval 10
```

To end-to-end test with real devices pointing at Windows (not NAS):

1. Admin PowerShell: `.\scripts\setup-dev-port80.ps1` (forwards 80 → 8080 + firewall rule)
2. On NAS, temporarily set `DNS_TARGET_IP=<your Windows IP>` in `.env`, then `docker compose up -d dnsmasq`
3. Windows: `.\scripts\dev.ps1`
4. When done, revert `.env` on NAS. The port forward is persistent — `teardown-dev-port80.ps1` removes it if desired.

## Credits

- [@kitazaki](https://github.com/kitazaki) — the Qiita article that reverse-engineered the SmartMat API + discovered the TTL bug + provided UART debug logs
- [SmartMat / infolens Inc.](https://www.smartmat.io/) — original device hardware

## License

Apache License 2.0 — matches [kitazaki/smartmat](https://github.com/kitazaki/smartmat).

**This is an unofficial third-party rescue project. Not affiliated with, endorsed by, or supported by infolens Inc.**
