"""Raw TCP proxy that logs every byte going both directions.

Device -> portproxy 80->8080 -> THIS PROXY (8080) -> python server (8082)

Lets us see exactly what the device sends after /s — is it closing the TCP,
does it try /sd on the same socket, or silently goes idle.
"""
from __future__ import annotations

import datetime
import socket
import sys
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8080
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8082


def log(line: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {line}", flush=True)


def pipe(conn_id: int, src: socket.socket, dst: socket.socket, direction: str) -> None:
    try:
        while True:
            try:
                data = src.recv(4096)
            except OSError:
                break
            if not data:
                log(f"conn#{conn_id} {direction} EOF")
                break
            snippet = data[:400].decode("latin-1", errors="replace").replace("\r", "\\r").replace("\n", "\\n\n")
            log(f"conn#{conn_id} {direction} {len(data)} bytes\n{snippet}")
            try:
                dst.sendall(data)
            except OSError as e:
                log(f"conn#{conn_id} {direction} send err: {e}")
                break
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(conn_id: int, client: socket.socket, client_addr) -> None:
    log(f"conn#{conn_id} OPEN from {client_addr}")
    backend = socket.socket()
    try:
        backend.connect((BACKEND_HOST, BACKEND_PORT))
    except OSError as e:
        log(f"conn#{conn_id} backend connect err: {e}")
        client.close()
        return

    t1 = threading.Thread(target=pipe, args=(conn_id, client, backend, "C->S"), daemon=True)
    t2 = threading.Thread(target=pipe, args=(conn_id, backend, client, "S->C"), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    client.close()
    backend.close()
    log(f"conn#{conn_id} CLOSED")


def main() -> None:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((LISTEN_HOST, LISTEN_PORT))
    listener.listen(16)
    log(f"proxy listening on {LISTEN_HOST}:{LISTEN_PORT} -> {BACKEND_HOST}:{BACKEND_PORT}")
    conn_id = 0
    while True:
        client, addr = listener.accept()
        conn_id += 1
        threading.Thread(target=handle, args=(conn_id, client, addr), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
