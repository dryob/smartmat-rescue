"""MQTT publisher + Home Assistant auto-discovery.

Disabled if env MQTT_HOST is empty.

Topics per device id DDDD:
  smartmat/DDDD/weight      (float, grams)
  smartmat/DDDD/battery     (float, 0..1)
  smartmat/DDDD/rssi        (int, dBm)
  smartmat/DDDD/last_seen   (ISO UTC timestamp)
  smartmat/DDDD/availability   online / offline  (retained)

Home Assistant auto-discovery configs published once per device under
  homeassistant/sensor/smartmat_DDDD_<kind>/config
  homeassistant/binary_sensor/smartmat_DDDD_online/config
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

LOG = logging.getLogger("smartmat.mqtt")

_ENABLED = bool(os.getenv("MQTT_HOST"))
HOST = os.getenv("MQTT_HOST", "")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USER = os.getenv("MQTT_USER") or None
PASS = os.getenv("MQTT_PASS") or None
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "smartmat-bridge")
PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "smartmat").rstrip("/")
DISCOVERY = os.getenv("MQTT_DISCOVERY", "1") not in ("0", "false", "")
DISCOVERY_PREFIX = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").rstrip("/")

_client = None
_announced: set[str] = set()
_lock = threading.Lock()

# set by start() — called on (re)connect to re-publish discovery for all known devices
_reannounce_cb = lambda: None  # noqa: E731


def _mk_client():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        LOG.warning("paho-mqtt not installed; MQTT disabled")
        return None

    # V2 API (paho-mqtt 2.x)
    c = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
    if USER:
        c.username_pw_set(USER, PASS)
    # LWT: announce offline if bridge dies (applies to bridge itself, not device availability)
    c.will_set(f"{PREFIX}/bridge/online", "0", qos=1, retain=True)

    def on_connect(cli, userdata, flags, rc, props=None):
        if rc == 0:
            LOG.info("MQTT connected to %s:%s", HOST, PORT)
            cli.publish(f"{PREFIX}/bridge/online", "1", qos=1, retain=True)
            # connection 建立後, 清空 announce cache 讓所有裝置重新 publish discovery
            # (避免 startup race: publish 發生在 connect 前, 訊息可能被丟)
            with _lock:
                _announced.clear()
            _reannounce_cb()
        else:
            LOG.warning("MQTT connect rc=%s", rc)

    def on_disconnect(cli, userdata, flags, rc, props=None):
        LOG.warning("MQTT disconnected rc=%s", rc)
        with _lock:
            _announced.clear()

    c.on_connect = on_connect
    c.on_disconnect = on_disconnect
    return c


def start(reannounce_cb=None) -> None:
    """reannounce_cb: called on (re)connect. Should iterate known devices
    and call on_device_seen for each (to republish HA discovery)."""
    global _client, _reannounce_cb
    if reannounce_cb:
        _reannounce_cb = reannounce_cb
    if not _ENABLED:
        LOG.info("MQTT disabled (set MQTT_HOST to enable)")
        return
    _client = _mk_client()
    if not _client:
        return
    try:
        _client.connect_async(HOST, PORT, keepalive=60)
        _client.loop_start()
        LOG.info("MQTT bridge started -> %s:%s prefix=%s discovery=%s",
                 HOST, PORT, PREFIX, DISCOVERY)
    except Exception:
        LOG.exception("MQTT connect failed; bridge disabled")
        _client = None


def _publish(topic: str, payload: str, retain: bool = False) -> None:
    if not _client:
        return
    try:
        _client.publish(topic, payload, qos=0, retain=retain)
    except Exception:
        LOG.exception("MQTT publish failed topic=%s", topic)


def _announce_device(device_id: str) -> None:
    if not DISCOVERY or not _client:
        return
    with _lock:
        if device_id in _announced:
            return
        _announced.add(device_id)

    dev_info = {
        "identifiers": [f"smartmat_{device_id}"],
        "name": f"SmartMat {device_id}",
        "manufacturer": "SmartMat",
        "model": "Light",
    }
    avail_topic = f"{PREFIX}/{device_id}/availability"

    def send(component: str, kind: str, cfg: dict[str, Any]) -> None:
        topic = f"{DISCOVERY_PREFIX}/{component}/smartmat_{device_id}_{kind}/config"
        base = {
            "availability_topic": avail_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "unique_id": f"smartmat_{device_id}_{kind}",
            "device": dev_info,
        }
        base.update(cfg)
        _publish(topic, json.dumps(base, separators=(",", ":")), retain=True)

    send("sensor", "weight", {
        "name": "Weight",
        "state_topic": f"{PREFIX}/{device_id}/weight",
        "unit_of_measurement": "g",
        "device_class": "weight",
        "state_class": "measurement",
        "suggested_display_precision": 0,
    })
    send("sensor", "battery", {
        "name": "Battery",
        "state_topic": f"{PREFIX}/{device_id}/battery",
        "unit_of_measurement": "%",
        "device_class": "battery",
        "state_class": "measurement",
        "value_template": "{{ (value | float * 100) | round(0) }}",
    })
    send("sensor", "rssi", {
        "name": "RSSI",
        "state_topic": f"{PREFIX}/{device_id}/rssi",
        "unit_of_measurement": "dBm",
        "device_class": "signal_strength",
        "state_class": "measurement",
        "entity_category": "diagnostic",
    })
    send("sensor", "last_seen", {
        "name": "Last seen",
        "state_topic": f"{PREFIX}/{device_id}/last_seen",
        "device_class": "timestamp",
        "entity_category": "diagnostic",
    })
    LOG.info("HA discovery announced for %s", device_id)


def on_measurement(
    device_id: str,
    weight_g: float | None,
    battery: float | None,
    rssi: int | None,
    measured_at_iso: str,
) -> None:
    if not _client:
        return
    _announce_device(device_id)
    _publish(f"{PREFIX}/{device_id}/availability", "online", retain=True)
    if weight_g is not None:
        _publish(f"{PREFIX}/{device_id}/weight", f"{weight_g:.2f}", retain=True)
    if battery is not None:
        _publish(f"{PREFIX}/{device_id}/battery", f"{battery:.3f}", retain=True)
    if rssi is not None:
        _publish(f"{PREFIX}/{device_id}/rssi", str(rssi), retain=True)
    _publish(f"{PREFIX}/{device_id}/last_seen", measured_at_iso, retain=True)


def on_device_seen(device_id: str) -> None:
    """Call on /s or /i (any device check-in) so HA sees device as online."""
    if not _client:
        return
    _announce_device(device_id)
    _publish(f"{PREFIX}/{device_id}/availability", "online", retain=True)
