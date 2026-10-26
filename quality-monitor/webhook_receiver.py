"""
Quality Monitor - Webhook Receiver

Listens for production event webhooks from Fusion Operations.
Detects quality issues (produced-waste or rework) and triggers
root cause analysis via the PLM and MES MCP servers.

Run:
    uv run uvicorn webhook_receiver:app --port 8002 --reload
"""

import json
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("quality-monitor")

app = FastAPI(title="Quality Monitor Webhook Receiver", version="0.1.0")

# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

# Minimum number of waste items to trigger an alert
WASTE_THRESHOLD = int(os.getenv("WASTE_THRESHOLD", "1"))

# Trigger on rework flag as well
REWORK_TRIGGERS_ALERT = os.getenv("REWORK_TRIGGERS_ALERT", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Quality signal extraction
# ---------------------------------------------------------------------------

def extract_quality_signals(payload: dict) -> dict:
    """
    Pull quality indicators out of a Fusion Operations production event payload.

    Returns a signals dict with:
        triggered     - bool: whether the alert threshold was met
        reasons       - list[str]: human-readable trigger descriptions
        waste_items   - list: the produced-waste array (may be empty)
        rework        - bool
        product       - dict: {id, code}
        operation     - str: operation code
        order         - dict: {id, code}
        worker        - str: worker name
        consumptions  - list: raw materials consumed
        event_time    - str: ISO timestamp of the event (end-time)
    """
    # Support both camelCase (real Fusion Operations) and kebab-case (sample payload)
    waste = payload.get("producedWaste") or payload.get("produced-waste") or []
    rework = payload.get("rework", False)
    product = payload.get("product", {})
    operation = payload.get("operation", {})
    order = payload.get("productionOrder") or payload.get("production-order") or {}
    worker = payload.get("worker", {})
    consumptions = payload.get("consumptions", [])
    end_time = payload.get("endTime") or payload.get("end-time") or datetime.now(timezone.utc).isoformat()

    reasons = []
    if waste and len(waste) >= WASTE_THRESHOLD:
        reasons.append(f"{len(waste)} waste item(s) recorded on operation '{operation.get('code', 'unknown')}'")
    if rework and REWORK_TRIGGERS_ALERT:
        reasons.append(f"rework flag set on production order '{order.get('code', 'unknown')}'")

    return {
        "triggered": len(reasons) > 0,
        "reasons": reasons,
        "waste_items": waste,
        "rework": rework,
        "product": product,
        "operation": operation.get("code", ""),
        "order": order,
        "worker": worker.get("name", "unknown"),
        "consumptions": consumptions,
        "event_time": end_time,
    }


def format_alert(signals: dict) -> str:
    """Format a human-readable alert summary for logging / downstream use."""
    lines = [
        "=" * 60,
        "QUALITY ALERT TRIGGERED",
        "=" * 60,
        f"  Time      : {signals['event_time']}",
        f"  Product   : {signals['product'].get('code', '?')} (id={signals['product'].get('id', '?')})",
        f"  Operation : {signals['operation']}",
        f"  Order     : {signals['order'].get('code', '?')} (id={signals['order'].get('id', '?')})",
        f"  Worker    : {signals['worker']}",
        "",
        "  Triggers:",
    ]
    for reason in signals["reasons"]:
        lines.append(f"    - {reason}")

    if signals["waste_items"]:
        lines.append("")
        lines.append("  Waste items:")
        for w in signals["waste_items"]:
            lines.append(f"    {json.dumps(w)}")

    if signals["consumptions"]:
        lines.append("")
        lines.append("  Consumed materials (RCA candidates):")
        for c in signals["consumptions"]:
            prod = c.get("product", {})
            lot = c.get("lot", {})
            lot_info = f"  lot={lot}" if lot else "  no lot recorded"
            lines.append(
                f"    product={prod.get('code', '?')} (id={prod.get('id', '?')})"
                f"  qty={c.get('quantity', '?')}{lot_info}"
            )

    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@app.post("/webhooks/production-event")
async def receive_production_event(request: Request) -> Response:
    """
    Receive a Fusion Operations production event webhook.

    Fusion Operations POSTs this when a production record is saved.
    We inspect 'produced-waste' and 'rework' to decide if a quality
    alert should fire.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = payload.get("id", "unknown")
    order_code = payload.get("production-order", {}).get("code", "unknown")
    product_code = payload.get("product", {}).get("code", "unknown")

    logger.info(
        "Received production event id=%s  order=%s  product=%s",
        event_id, order_code, product_code,
    )

    signals = extract_quality_signals(payload)

    if signals["triggered"]:
        alert_text = format_alert(signals)
        logger.warning(alert_text)
        # TODO: pass signals to rca_agent.py → Slack notifier
        return Response(
            content=json.dumps({
                "status": "alert_triggered",
                "event_id": event_id,
                "reasons": signals["reasons"],
                "product": signals["product"].get("code"),
                "order": signals["order"].get("code"),
            }),
            media_type="application/json",
            status_code=200,
        )
    else:
        logger.info("No quality threshold met — no alert for event id=%s", event_id)
        return Response(
            content=json.dumps({
                "status": "ok",
                "event_id": event_id,
                "alert": False,
            }),
            media_type="application/json",
            status_code=200,
        )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "quality-monitor",
        "waste_threshold": WASTE_THRESHOLD,
        "rework_triggers_alert": REWORK_TRIGGERS_ALERT,
    }
