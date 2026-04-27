"""Shared fixtures: spin up the SmartMat HTTP server on an ephemeral port
backed by a tmp SQLite DB, with MQTT disabled so tests don't need a broker."""
from __future__ import annotations

import importlib
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

# Make app/ importable.
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def server(tmp_path) -> Iterator[tuple[str, int]]:
    """Boot main.py against a tmp DB on an ephemeral port. Yields (host, port)."""
    db_path = tmp_path / "smartmat.db"
    port = _free_port()

    # Configure env BEFORE importing app modules so module-level reads pick it up.
    os.environ["SMARTMAT_DB"] = str(db_path)
    os.environ["PORT"] = str(port)
    os.environ["LOG_LEVEL"] = "WARNING"
    os.environ.pop("MQTT_HOST", None)  # ensure bridge stays disabled
    os.environ["SMARTMAT_O"] = "0"
    os.environ["SMARTMAT_MD"] = "0"

    # Force fresh import each test so module-level config picks up env.
    for mod in ("main", "mqtt_bridge"):
        sys.modules.pop(mod, None)
    main = importlib.import_module("main")

    main.db_init()
    server_obj = main.ThreadingHTTPServer(("127.0.0.1", port), main.Handler)
    t = threading.Thread(target=server_obj.serve_forever, daemon=True)
    t.start()

    # Wait for the listener to actually accept.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    yield ("127.0.0.1", port)

    server_obj.shutdown()
    server_obj.server_close()
