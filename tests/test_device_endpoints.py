"""Byte-level tests on the 4 device endpoints — the ESP8266 firmware is strict
about HTTP response shape, so these regressions matter even though the server
"works" by spec."""
from __future__ import annotations

import socket
from typing import Tuple


def _http(host: str, port: int, raw: bytes, timeout: float = 2.0) -> bytes:
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        s.settimeout(timeout)
        s.sendall(raw)
        chunks = []
        while True:
            try:
                buf = s.recv(8192)
            except socket.timeout:
                break
            if not buf:
                break
            chunks.append(buf)
        return b"".join(chunks)
    finally:
        s.close()


def _split(resp: bytes) -> Tuple[bytes, bytes]:
    head, _, body = resp.partition(b"\r\n\r\n")
    return head, body


def test_settings_response_matches_envoy(server) -> None:
    """/s response: HTTP/1.1, Title-Case Content-Type, lowercase server: envoy,
    Content-Length: 111, body byte-identical to article's capture."""
    host, port = server
    body = b'{"id":"WTEST","wv":"2.08","mv":"15"}'
    raw = (
        b"POST /v1/device/version2/s HTTP/1.1\r\n"
        b"Host: x\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n"
        b"\r\n" + body
    )
    head, resp_body = _split(_http(host, port, raw))
    assert head.startswith(b"HTTP/1.1 200 OK"), head[:80]
    assert b"Content-Type: application/json; charset=utf-8" in head
    assert b"Content-Length: 111" in head
    assert b"Connection: keep-alive" in head
    assert b"server: envoy" in head           # lowercase 's'
    # NO trailing space after envoy (Python's default version_string adds one).
    # head was split on \r\n\r\n so it ends right after the last header value.
    assert b"server: envoy " not in head, "server header has trailing space"
    expected_body = (
        b'{"i":300,"c":"http://measure.lite.smartmat.io/v1/device/version2",'
        b'"mr":0,"mrd":"","fr":0,"frd":"","o":0,"md":0}'
    )
    assert resp_body[: len(expected_body)] == expected_body


def test_info_returns_empty_json_string(server) -> None:
    """/i must return literal '""' (2 bytes, JSON empty string), not 'OK'."""
    host, port = server
    body = b'{"id":"WTEST"}'
    raw = (
        b"POST /v1/device/version2/i HTTP/1.1\r\n"
        b"Host: x\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"\r\n" + body
    )
    head, resp_body = _split(_http(host, port, raw))
    assert b"Content-Type: application/json; charset=utf-8" in head
    assert resp_body[:2] == b'""'


def test_sd_returns_iso_utc(server) -> None:
    """/sd returns {"d":"YYYY-MM-DD HH:MM:SS","tz":"UTC"}."""
    host, port = server
    raw = b"GET /v1/device/version2/sd HTTP/1.1\r\nHost: x\r\n\r\n"
    head, resp_body = _split(_http(host, port, raw))
    assert head.startswith(b"HTTP/1.1 200 OK")
    body = resp_body[: int(_content_length(head))]
    assert body.startswith(b'{"d":"')
    assert b'"tz":"UTC"' in body


def test_unknown_path_returns_404(server) -> None:
    """Audit fix: previously returned 200 OK for any unknown path."""
    host, port = server
    raw = b"GET /random/junk HTTP/1.1\r\nHost: x\r\n\r\n"
    head, _ = _split(_http(host, port, raw))
    assert head.startswith(b"HTTP/1.1 404")


def _content_length(head: bytes) -> int:
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            return int(line.split(b":", 1)[1].strip())
    return -1
