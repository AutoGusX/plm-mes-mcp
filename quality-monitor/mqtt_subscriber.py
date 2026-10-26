"""
Quality Monitor - MQTT Subscriber

Connects to the Autodesk Tandem Connect MQTT broker and subscribes to
AgenticAI/# to receive Fusion Operations quality events.

Detects quality issues (produced-waste or rework) and triggers
root cause analysis via the PLM and MES MCP servers.

Run:
    uv run python mqtt_subscriber.py
"""

import atexit
import json
import logging
import os
import sys
import tempfile
import threading
import queue

import asyncio

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from webhook_receiver import extract_quality_signals, format_alert

load_dotenv()

# ---------------------------------------------------------------------------
# Single-instance guard via PID file
# ---------------------------------------------------------------------------

_PID_FILE = os.path.join(tempfile.gettempdir(), "quality-monitor.pid")


def _is_process_alive(pid: int) -> bool:
    """Return True if a process with the given PID is currently running."""
    import subprocess
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return False  # can't determine — treat as dead


def _check_single_instance() -> None:
    if not os.path.exists(_PID_FILE):
        return
    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return  # corrupt file — proceed
    if _is_process_alive(pid):
        print(
            f"ERROR: mqtt_subscriber is already running (PID {pid}).\n"
            f"Stop it first, or delete {_PID_FILE} to force a restart.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Stale PID file from a previous crash
    logging.getLogger("quality-monitor.mqtt").warning(
        "Stale PID file found (PID %d no longer running) — proceeding.", pid
    )


def _write_pid() -> None:
    with open(_PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid() -> None:
    try:
        os.unlink(_PID_FILE)
    except FileNotFoundError:
        pass


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("quality-monitor.mqtt")

BROKER_HOST = os.getenv("MQTT_BROKER_HOST")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "AgenticAI/#")

# ---------------------------------------------------------------------------
# Alert worker — runs async RCA + Slack on a dedicated background thread
# so paho's network loop (PINGREQ/PINGRESP) is never blocked.
# ---------------------------------------------------------------------------

_alert_queue: queue.Queue = queue.Queue()


def _alert_worker():
    """Background thread: drains the alert queue and runs async work."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        item = _alert_queue.get()
        if item is None:
            break
        topic, signals = item
        try:
            loop.run_until_complete(_process_alert(topic, signals))
        except Exception as exc:
            logger.error("Alert worker error: %s", exc, exc_info=True)
        finally:
            _alert_queue.task_done()


async def _process_alert(topic: str, signals: dict):
    # Write raw event data — RCA and Slack are handled by the Claude Code monitoring session
    entry = {
        "topic": topic,
        "product": signals["product"],
        "operation": signals["operation"],
        "order": signals["order"],
        "reasons": signals["reasons"],
        "waste_items": signals["waste_items"],
        "consumptions": signals["consumptions"],
        "event_time": signals["event_time"],
    }
    alerts_path = os.path.join(tempfile.gettempdir(), "quality-alerts.jsonl")
    with open(alerts_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    logger.info("Alert written to %s — awaiting Claude RCA", alerts_path)


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("Connected to broker %s:%d", BROKER_HOST, BROKER_PORT)
        client.subscribe(MQTT_TOPIC, qos=1)
        logger.info("Subscribed to topic: %s", MQTT_TOPIC)
    else:
        logger.error("Connection refused — reason code: %s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        logger.warning("Unexpected disconnect (reason=%s) — will reconnect", reason_code)


def on_message(client, userdata, msg):
    topic = msg.topic
    logger.info("Message received on topic: %s (%d bytes)", topic, len(msg.payload))
    try:
        _handle_message(topic, msg.payload)
    except Exception as exc:
        logger.error("Unhandled error in message handler: %s", exc, exc_info=True)


def _handle_message(topic, raw_payload):

    try:
        outer = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("Failed to parse message payload: %s", exc)
        return

    # Broker wraps the event: {"title": "...", "data": "<json string>"}
    raw_data = outer.get("data", outer)
    if isinstance(raw_data, str):
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse inner data field: %s", exc)
            return
    else:
        payload = raw_data

    logger.info(
        "waste=%s  rework=%s  keys=%s",
        payload.get("producedWaste") or payload.get("produced-waste"),
        payload.get("rework"),
        list(payload.keys()),
    )
    signals = extract_quality_signals(payload)

    if signals["triggered"]:
        logger.warning(format_alert(signals))
        _alert_queue.put((topic, signals))
    else:
        logger.info(
            "No quality threshold met — order=%s product=%s",
            signals["order"].get("code", "?"),
            signals["product"].get("code", "?"),
        )


def on_subscribe(client, userdata, mid, reason_codes, properties):
    granted = [str(rc) for rc in reason_codes]
    logger.info("Subscription confirmed — granted QoS: %s", granted)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    _check_single_instance()
    _write_pid()
    atexit.register(_remove_pid)

    if not BROKER_HOST:
        logger.error("MQTT_BROKER_HOST is not set — check your .env file")
        sys.exit(1)
    if not MQTT_USERNAME or not MQTT_PASSWORD:
        logger.error("MQTT_USERNAME / MQTT_PASSWORD are not set — check your .env file")
        sys.exit(1)

    # Start the background alert worker thread (processes RCA + Slack
    # off the paho network thread so PINGREQ/PINGRESP are never blocked)
    worker = threading.Thread(target=_alert_worker, daemon=True)
    worker.start()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="quality-monitor-persistent",
        clean_session=False,
    )
    client.tls_set()  # mqtts requires TLS
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_subscribe = on_subscribe
    client.reconnect_delay_set(min_delay=2, max_delay=30)

    logger.info("Connecting to %s:%d as user '%s'...", BROKER_HOST, BROKER_PORT, MQTT_USERNAME)

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as exc:
        logger.error("Could not connect to broker: %s", exc)
        sys.exit(1)

    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        logger.info("Shutting down")
        client.disconnect()
        _alert_queue.put(None)  # signal worker to exit
        worker.join(timeout=5)
        _remove_pid()


if __name__ == "__main__":
    main()
