# SmartMat Lite protocol notes

本文件整理 SmartMat Lite 裝置的 API 協定細節，供本專案實作參考。
內容主要來自 **@kitazaki** 的文章的技術部分 (Wireshark 抓包 + 裝置 UART debug log)。

> **來源 (原文)：**
> <https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04>
> *環境の変化と戦う④(スマートマットの文鎮化を回避)* — by [@kitazaki](https://qiita.com/kitazaki)
>
> 完整背景、作者的原 Python / Node.js / Node-RED 實作請點上面連結。

---

## 裝置通訊序列

### 初回連線

* `POST /v1/device/version2/i` — 裝置資訊送出 (boot register)
* `GET  /v1/device/version2/sd` — 時刻同步

### 2 回目以降 (每次醒來)

* `POST /v1/device/version2/s` — 裝置資訊送出 (settings query)
* `GET  /v1/device/version2/sd` — 時刻同步
* `POST /v1/device/version2/m` — 重量測量資料送出

之後裝置會下 `POWER_OFF_CMD` 進入深度睡眠，週期依 `/s` response 裡的 `i` 欄位 (秒)。

---

## 真實雲端 response (從裝置 UART debug log 捕獲)

以下是本專案 `app/main.py` 要 **byte-by-byte 對齊**的目標。header 順序、大小寫、值格式都不能差。

### /s response

```
HTTP/1.1 200 OK
Date: Mon, 15 Sep 2025 09:17:58 GMT
Content-Type: application/json; charset=utf-8
Content-Length: 111
Connection: keep-alive
x-envoy-upstream-service-time: 96
server: envoy

{"i":300,"c":"http://measure.lite.smartmat.io/v1/device/version2","mr":0,"mrd":"","fr":0,"frd":"","o":0,"md":0}
```

裝置會 parse 下列欄位 (從 debug log 推論):
| JSON 欄位 | 裝置內部名稱 | 意義 |
|---|---|---|
| `i` | freq | 上傳間隔 (秒)  |
| `c` | New URL | 雲端 base URL |
| `mr` | MCU RST | MCU reset flag (0=no) |
| `mrd` | MCU RST DATE | |
| `fr` | FAC RST | factory reset flag |
| `frd` | FAC RST DATE | |
| `o` | OTA REQ | OTA 請求 flag |
| `md` | (unknown) | 觀察值為 0 |

### /sd response

```
HTTP/1.1 200 OK
Date: Mon, 15 Sep 2025 09:17:59 GMT
Content-Type: application/json; charset=utf-8
Content-Length: 38
Connection: keep-alive
x-envoy-upstream-service-time: 2
server: envoy

{"d":"2025-09-15 09:17:59","tz":"UTC"}
```

### /m request

裝置 POST 到 server：
```json
{"id":"W42200500161","md":[{"w":"1480.00","d":"2025-09-15 09:17:57"}],"b":"0.43","p":"0","r":"-40"}
```

| 欄位 | 意義 |
|---|---|
| `id` | 裝置序號 (e.g. W42...) |
| `md[].w` | 重量 (字串浮點, 克) |
| `md[].d` | 量測時間 (UTC, 裝置自己的 RTC) |
| `b` | 電池 (0.00 ~ 1.00) |
| `p` | power flag (充電?) |
| `r` | Wi-Fi RSSI (dBm) |

多筆 backlog 時 `md` array 可能含好幾筆。server 的 /m response:
```
{"m":"OK","d":"2025-09-15 09:18:00","tz":"UTC"}
```

---

## 救命關鍵 1: DNS TTL

原作者踩到這坑 (`デバイス情報の送信は正常に行われるが、時刻情報の取得で止まる`) —
`/s` 能過但 `/sd` 打不出來。

**原因**：dnsmasq 預設對 `/etc/hosts` 和 `--address=` 的 DNS 回應 **TTL=0**，
ESP8266 HTTPClient 拿到 TTL=0 後下次 DNS 查詢失敗。

**修法**：dnsmasq 加參數 `local-ttl=60` (或更高)。本專案用 60。

---

## 救命關鍵 2: HTTP response byte-for-byte 對齊 envoy

本專案作者實測：以上 TTL 修完後，如果 response header 跟 envoy 雲端不 byte-exact match，
裝置會 **連 `/sd` 都不打**、困在 `/s` 重試循環 (~45 秒間隔)。

Python `BaseHTTPRequestHandler` 預設產出的 response 對不起來，因為：

| 差異 | Python stdlib 預設 | 真實雲端 |
|---|---|---|
| Header 順序 | Server → Date → ... | Date → Content-Type → ... → server (最後) |
| `Server` 值 | `BaseHTTP/0.6 Python/3.12` + 尾空格 | `envoy` (小寫字首) |
| `server` 大小寫 | `Server:` (Title-Case) | `server:` (小寫) |
| Content-Type 大小寫 | 取決於 `send_header` 呼叫 | `Content-Type:` (Title-Case) |

所以 `app/main.py` 的 `_send_bytes` 不用 `send_response` / `send_header`，直接寫 raw bytes：

```python
self.wfile.write(f"HTTP/1.1 {status} OK\r\n".encode())
self.wfile.write(b"Date: ...\r\n")
self.wfile.write(b"Content-Type: application/json; charset=utf-8\r\n")
self.wfile.write(b"Content-Length: N\r\n")
self.wfile.write(b"Connection: keep-alive\r\n")
self.wfile.write(b"x-envoy-upstream-service-time: 10\r\n")
self.wfile.write(b"server: envoy\r\n")
self.wfile.write(b"\r\n")
self.wfile.write(body)
```

### `/i` 特殊值

`/i` response 必須是 `""` (literal JSON 空字串, 2 bytes) + `application/json; charset=utf-8`，
不能是 `OK` plain text。

---

## 裝置正常一輪的 UART debug log (供對照)

抓自 @kitazaki 的文章。GND + D_TXD 接 USB serial (9600 bps)。

```
INF|cloud_api.c:392|CALL:get_mat_setting
DBG|cloud_api.c:97|pack data:{"id":"W42200500161","wv":"2.08","mv":"15"}
DBG|http.c:256|URL=http://measure.lite.smartmat.io/v1/device/version2/s
INF|http.c:92|DNS CALLBACK
INF|http.c:309|send success!
... (response) ...
DBG|cloud_api.c:480|get_frequency_rev_hand
DBG|cloud_api.c:495|freq=300
DBG|cloud_api.c:502|OTA REQ=0
DBG|cloud_api.c:507|New URL=http://measure.lite.smartmat.io/v1/device/version2
DBG|basic_infor.c:131|URL has no change
DBG|cloud_api.c:515|MCU RST=0
DBG|cloud_api.c:544|FAC RST=0
DBG|http.c:256|URL=http://measure.lite.smartmat.io/v1/device/version2/sd
INF|http.c:309|send success!
... (response) ...
DBG|cloud_api.c:611|Date field=2025-09-15 09:17:59
DBG|cloud_api.c:715|send_mesure_data_to_cloud
INF|cloud_api.c:226|Send measured data
DBG|cloud_api.c:230|POST DATA={"id":"W42200500161","md":[{"w":"1480.00","d":"2025-09-15 09:17:57"}],"b":"0.43","p":"0","r":"-40"}
DBG|http.c:256|URL=http://measure.lite.smartmat.io/v1/device/version2/m
INF|http.c:309|send success!
... (response) ...
INF|data_save.c:133|clear success
INF|usart_data_hand.c:1584|POWER_OFF_CMD -> MCU
```

注意：完成一輪後裝置 **進入深度睡眠** (POWER_OFF_CMD)，不是常駐上線。
所以 server 看到裝置 request 的週期 ≈ `/s` response 裡 `i` 欄位的秒數。

---

## 裝置 HTTP request 欄位

裝置打 `/s` 時送的 request:
```
POST /v1/device/version2/s HTTP/1.1
Accept: */*
Content-Length: 43
Content-Type: application/json
X-SS-Key: 443190d1f417c680837cf6388dc191bb
Host: measure.lite.smartmat.io
Connection: Keep-Alive

{"id":"W42200500161","wv":"2.08","mv":"15"}
```

- `X-SS-Key`: 寫死在 firmware 的 API key，所有 SmartMat Lite 共用同一個
- `wv`: firmware version (觀察到 2.08)
- `mv`: hardware version (觀察到 15)

server 端不驗證 `X-SS-Key` 也照常運作。

---

## 參考

- Qiita 原文：<https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04>
- 原作者 repo：<https://github.com/kitazaki/smartmat> (Apache 2.0)
