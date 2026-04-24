"""SmartMat Lite fake API — pure Python stdlib.

用 http.server (HTTP/1.0 + Title-Case headers) 而不是 uvicorn，因為
ESP8266 HTTPClient 對 HTTP/1.1 + 全小寫 headers 的回應處理有問題 —
裝置會重複打 /s 但從不前進到 /sd / /m。

參考: https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import mqtt_bridge

LOG = logging.getLogger("smartmat")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DB_PATH = Path(os.getenv("SMARTMAT_DB", "/data/smartmat.db"))
POLL_INTERVAL = int(os.getenv("SMARTMAT_POLL_INTERVAL", "300"))
UPSTREAM_BASE = os.getenv(
    "SMARTMAT_UPSTREAM_BASE",
    "http://measure.lite.smartmat.io/v1/device/version2",
)
PORT = int(os.getenv("PORT", "80"))


# ---------- DB ----------

def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init() -> None:
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id          TEXT PRIMARY KEY,
                wv          TEXT,
                mv          TEXT,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS measurements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   TEXT NOT NULL,
                weight_g    REAL,
                battery     REAL,
                power       INTEGER,
                rssi        INTEGER,
                measured_at TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_measurements_device_time
                ON measurements (device_id, measured_at);
            """
        )


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_device(device_id: str, wv: str | None, mv: str | None) -> None:
    now = now_utc_str()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO devices (id, wv, mv, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                wv = COALESCE(excluded.wv, devices.wv),
                mv = COALESCE(excluded.mv, devices.mv),
                last_seen = excluded.last_seen
            """,
            (device_id, wv, mv, now, now),
        )


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_iso_utc(s: str) -> str:
    """裝置傳 '2026-04-24 00:15:53' (UTC)，轉 HA 要的 ISO8601 with Z."""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- HTTP handler ----------

class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 + keep-alive 模擬真實雲端 (envoy) 回應
    # Node.js 版用這種格式證實能讓裝置正常走 cycle
    protocol_version = "HTTP/1.1"
    server_version = "envoy"
    sys_version = ""

    def version_string(self) -> str:
        # 預設會回 "envoy " (尾空格)，去掉
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        LOG.info("%s - %s", self.address_string(), format % args)

    def do_POST(self) -> None:  # noqa: N802
        self._route()

    def do_GET(self) -> None:  # noqa: N802
        self._route()

    # ---- dispatch ----

    def _route(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body_bytes = b""
        if self.command == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            if n > 0:
                body_bytes = self.rfile.read(n)

        if path.startswith("/v1/device/"):
            # 裝置除錯: 連 headers 一起紀錄
            hdrs = {k: v for k, v in self.headers.items()}
            LOG.info("%s %s headers=%s body=%s", self.command, path, hdrs, body_bytes.decode(errors="replace"))

        try:
            data = json.loads(body_bytes) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}

        try:
            if path == "/v1/device/version2/s":
                self._settings(data)
            elif path == "/v1/device/version2/sd":
                self._sync_time()
            elif path == "/v1/device/version2/m":
                self._measurement(data)
            elif path == "/v1/device/version2/i":
                self._info(data)
            elif path == "/":
                self._dashboard()
            elif path == "/devices":
                self._list_devices()
            elif path == "/measurements":
                self._list_measurements(parse_qs(parsed.query))
            elif path == "/healthz":
                self._send_json({"status": "ok"})
            else:
                self._send_text("OK", 200)
        except Exception:
            LOG.exception("handler error")
            self._send_text("internal error", 500)

    # ---- device endpoints (match article verbatim) ----

    def _info(self, data: dict[str, Any]) -> None:
        device_id = data.get("id")
        if device_id:
            upsert_device(device_id, data.get("wv"), data.get("mv"))
            mqtt_bridge.on_device_seen(device_id)
        # 文章 Python 版對 /i 回 '""' (JSON 空字串) + application/json
        self._send_json_raw('""')

    def _settings(self, data: dict[str, Any]) -> None:
        device_id = data.get("id")
        if device_id:
            upsert_device(device_id, data.get("wv"), data.get("mv"))
            mqtt_bridge.on_device_seen(device_id)
        # 文章的 /s response 一字不差
        # 原文是穩態 capture；有些 ESP 韌體可能把 o:1 視為「伺服器 ready，去量測」
        # 若仍不行，換成 md:1 或反過來
        o_flag = int(os.getenv("SMARTMAT_O", "0"))
        md_flag = int(os.getenv("SMARTMAT_MD", "0"))
        body = (
            '{"i":' + str(POLL_INTERVAL)
            + ',"c":"' + UPSTREAM_BASE + '"'
            + ',"mr":0,"mrd":"","fr":0,"frd":""'
            + ',"o":' + str(o_flag)
            + ',"md":' + str(md_flag)
            + '}'
        )
        self._send_json_raw(body)

    def _sync_time(self) -> None:
        body = '{"d":"' + now_utc_str() + '","tz":"UTC"}'
        self._send_json_raw(body)

    def _measurement(self, data: dict[str, Any]) -> None:
        device_id = data.get("id")
        if device_id:
            upsert_device(device_id, None, None)

        received = now_utc_str()
        battery = _to_float(data.get("b"))
        power = _to_int(data.get("p"))
        rssi = _to_int(data.get("r"))
        rows = []
        latest_weight = None
        latest_measured_at = None
        for md in data.get("md", []) or []:
            try:
                weight = float(md.get("w")) if md.get("w") is not None else None
            except (TypeError, ValueError):
                weight = None
            measured_at = md.get("d") or received
            rows.append((device_id, weight, battery, power, rssi, measured_at, received))
            # 最新一筆是 list 的最後？不一定，但 md_entries 通常是時序。
            # 安全起見保留「最晚 measured_at」的那筆
            if weight is not None and (latest_measured_at is None or measured_at > latest_measured_at):
                latest_weight = weight
                latest_measured_at = measured_at
        if rows:
            with db_connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO measurements
                        (device_id, weight_g, battery, power, rssi, measured_at, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            # 推送最新一筆到 MQTT (舊 backlog 不個別推)
            if device_id and latest_weight is not None:
                mqtt_bridge.on_measurement(
                    device_id=device_id,
                    weight_g=latest_weight,
                    battery=battery,
                    rssi=rssi,
                    measured_at_iso=_to_iso_utc(latest_measured_at or received),
                )

        body = '{"m":"OK","d":"' + received + '","tz":"UTC"}'
        self._send_json_raw(body)

    # ---- dashboard / JSON API ----

    def _list_devices(self) -> None:
        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    d.id, d.wv, d.mv, d.first_seen, d.last_seen,
                    (SELECT weight_g FROM measurements WHERE device_id=d.id ORDER BY id DESC LIMIT 1) AS last_weight,
                    (SELECT battery  FROM measurements WHERE device_id=d.id ORDER BY id DESC LIMIT 1) AS last_battery,
                    (SELECT rssi     FROM measurements WHERE device_id=d.id ORDER BY id DESC LIMIT 1) AS last_rssi,
                    (SELECT COUNT(*) FROM measurements WHERE device_id=d.id) AS total_measurements
                FROM devices d
                ORDER BY d.last_seen DESC
                """
            ).fetchall()

        now = datetime.now(timezone.utc)
        devices = []
        for r in rows:
            last_seen = datetime.strptime(r["last_seen"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            age_sec = int((now - last_seen).total_seconds())
            if age_sec < POLL_INTERVAL * 2:
                status = "online"
            elif age_sec < POLL_INTERVAL * 6:
                status = "stale"
            else:
                status = "offline"
            devices.append({**dict(r), "age_seconds": age_sec, "status": status})
        self._send_json({"devices": devices, "count": len(devices), "poll_interval": POLL_INTERVAL})

    def _list_measurements(self, qs: dict[str, list[str]]) -> None:
        limit = max(1, min(int((qs.get("limit") or ["50"])[0]), 500))
        device_id = (qs.get("device_id") or [None])[0]
        with db_connect() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM measurements WHERE device_id=? ORDER BY id DESC LIMIT ?",
                    (device_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM measurements ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        self._send_json({"measurements": [dict(r) for r in rows], "count": len(rows)})

    def _dashboard(self) -> None:
        self._send_bytes(_DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8", 200)

    # ---- send helpers ----

    def _send_bytes(self, body: bytes, content_type: str, status: int) -> None:
        # 自己組 response 避開 Python 預設 header 順序
        # 匹配真實 envoy cloud: Date, Content-Type, Content-Length, Connection, x-envoy-*, server
        import email.utils as _eu
        self.log_request(status)
        self.wfile.write(f"HTTP/1.1 {status} {self.responses[status][0]}\r\n".encode())
        date_val = _eu.formatdate(timeval=None, localtime=False, usegmt=True)
        hdrs = [
            ("Date", date_val),
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Connection", "keep-alive"),
            ("x-envoy-upstream-service-time", "10"),
            ("server", "envoy"),
        ]
        for k, v in hdrs:
            self.wfile.write(f"{k}: {v}\r\n".encode())
        self.wfile.write(b"\r\n")
        self.wfile.write(body)

    def _send_json_raw(self, body_str: str) -> None:
        self._send_bytes(body_str.encode("utf-8"), "application/json; charset=utf-8", 200)

    def _send_json(self, obj: Any) -> None:
        self._send_json_raw(json.dumps(obj, separators=(",", ":")))

    def _send_text(self, body_str: str, status: int) -> None:
        self._send_bytes(body_str.encode("utf-8"), "text/plain; charset=utf-8", status)


_DASHBOARD_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>SmartMat Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
         background:#0e1116; color:#d7dde4; margin:0; padding:20px; }
  h1 { font-size:18px; margin:0 0 16px; color:#fff; }
  .sub { color:#8a94a3; font-size:12px; margin-bottom:20px; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding:8px 10px; border-bottom:1px solid #222831; text-align:left; font-size:13px; }
  th { color:#8a94a3; font-weight:normal; text-transform:uppercase; letter-spacing:.05em; font-size:11px; }
  .badge { padding:2px 8px; border-radius:10px; font-size:11px; }
  .online  { background:#1e3a28; color:#7cd992; }
  .stale   { background:#3a2f1e; color:#d9b17c; }
  .offline { background:#3a1e1e; color:#d97c7c; }
  .empty { color:#8a94a3; padding:30px 0; text-align:center; }
  tr:hover td { background:#161b22; }
  .footer { margin-top:20px; color:#8a94a3; font-size:11px; }
  a { color:#7cb9d9; }
</style>
</head>
<body>
<h1>SmartMat Dashboard</h1>
<div class="sub">自動重新整理 每 15 秒 · poll interval <span id="pi">-</span>s</div>
<table>
  <thead>
    <tr>
      <th>狀態</th><th>Device ID</th><th>重量 (g)</th><th>電量</th><th>RSSI</th>
      <th>最後一次</th><th>上傳數</th><th>fw/hw</th>
    </tr>
  </thead>
  <tbody id="tbody"><tr><td class="empty" colspan="8">讀取中…</td></tr></tbody>
</table>
<div class="footer">
  JSON: <a href="/devices">/devices</a> · <a href="/measurements">/measurements</a>
</div>
<script>
async function refresh() {
  const r = await fetch('/devices'); const data = await r.json();
  document.getElementById('pi').textContent = data.poll_interval;
  const tb = document.getElementById('tbody');
  if (!data.devices.length) {
    tb.innerHTML = '<tr><td class="empty" colspan="8">尚無裝置連線，把 SmartMat 插電等 5 分鐘。</td></tr>';
    return;
  }
  tb.innerHTML = data.devices.map(d => {
    const w = d.last_weight == null ? '-' : d.last_weight.toFixed(1);
    const b = d.last_battery == null ? '-' : (d.last_battery*100).toFixed(0) + '%';
    const rssi = d.last_rssi == null ? '-' : d.last_rssi;
    const age = d.age_seconds < 60 ? d.age_seconds+'s'
              : d.age_seconds < 3600 ? Math.round(d.age_seconds/60)+'m'
              : Math.round(d.age_seconds/3600)+'h';
    return `<tr>
      <td><span class="badge ${d.status}">${d.status}</span></td>
      <td>${d.id}</td><td>${w}</td><td>${b}</td><td>${rssi}</td>
      <td>${d.last_seen} UTC (${age} ago)</td>
      <td>${d.total_measurements}</td>
      <td>${d.wv || '-'} / ${d.mv || '-'}</td>
    </tr>`;
  }).join('');
}
refresh(); setInterval(refresh, 15000);
</script>
</body>
</html>
"""


def _reannounce_all() -> None:
    """MQTT (re)connect 時呼叫，把 DB 裡所有裝置重新 publish discovery。"""
    try:
        with db_connect() as conn:
            for row in conn.execute("SELECT id FROM devices"):
                mqtt_bridge.on_device_seen(row["id"])
    except Exception:
        LOG.exception("reannounce failed")


def main() -> None:
    db_init()
    mqtt_bridge.start(reannounce_cb=_reannounce_all)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    LOG.info("SmartMat fake API on :%d (db=%s, poll=%ss)", PORT, DB_PATH, POLL_INTERVAL)
    server.serve_forever()


if __name__ == "__main__":
    main()
