"""Audit fix #2/#6/#7: malformed inputs return 4xx, not 500."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def _post(host: str, port: int, path: str, body: bytes, headers=None):
    req = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=body,
        method="POST",
        headers=headers or {"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(host: str, port: int, path: str):
    try:
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=2) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_measurement_missing_id_returns_400(server) -> None:
    host, port = server
    code, _ = _post(host, port, "/v1/device/version2/m", b'{"md":[]}')
    assert code == 400


def test_measurement_md_not_a_list_returns_400(server) -> None:
    host, port = server
    code, _ = _post(host, port, "/v1/device/version2/m", b'{"id":"X","md":"oops"}')
    assert code == 400


def test_measurement_with_garbage_md_entries_skips_them(server) -> None:
    """Non-dict md entries should be skipped, not crash."""
    host, port = server
    payload = json.dumps(
        {"id": "WGOOD", "md": ["junk", 42, {"w": "100"}]}
    ).encode()
    code, _ = _post(host, port, "/v1/device/version2/m", payload)
    assert code == 200


def test_measurements_invalid_limit_returns_400(server) -> None:
    host, port = server
    code, _ = _get(host, port, "/measurements?limit=foo")
    assert code == 400


def test_measurements_default_limit_works(server) -> None:
    host, port = server
    code, body = _get(host, port, "/measurements")
    assert code == 200
    data = json.loads(body)
    assert "measurements" in data and "count" in data


def test_oversized_content_length_rejected(server) -> None:
    """Body claim of 100 MB should be rejected up-front, not buffered."""
    import socket
    sock = socket.create_connection((server[0], server[1]), timeout=2)
    try:
        sock.sendall(
            b"POST /v1/device/version2/m HTTP/1.1\r\n"
            b"Host: x\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 104857600\r\n"
            b"\r\n"
        )
        # Don't send body; server should reject before reading it.
        sock.settimeout(2)
        head = sock.recv(4096)
        assert head.startswith(b"HTTP/1.1 413"), head[:80]
    finally:
        sock.close()


def test_invalid_content_length_rejected(server) -> None:
    import socket
    sock = socket.create_connection((server[0], server[1]), timeout=2)
    try:
        sock.sendall(
            b"POST /v1/device/version2/m HTTP/1.1\r\n"
            b"Host: x\r\n"
            b"Content-Length: notanumber\r\n"
            b"\r\n"
        )
        sock.settimeout(2)
        head = sock.recv(4096)
        assert head.startswith(b"HTTP/1.1 400"), head[:80]
    finally:
        sock.close()
