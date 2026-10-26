"""
Quality Monitor - Slack Notifier

Posts quality alerts to a Slack workflow trigger.

Expected payload shape (defined by the Slack workflow):
    {
        "Message": str,
        "Related_COs": str,
        "Related_Productions": str
    }
"""

import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("quality-monitor.slack")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# Slack Workflow triggers drop non-ASCII Unicode silently.
# Map the most common offenders to plain ASCII equivalents.
_UNICODE_MAP = {
    "\u2192": "->",   # →  rightward arrow
    "\u2190": "<-",   # ←  leftward arrow
    "\u2014": "--",   # —  em dash
    "\u2013": "-",    # –  en dash
    "\u2022": "-",    # •  bullet
    "\u00B7": "-",    # ·  middle dot
    "\u2019": "'",    # '  right single quote
    "\u2018": "'",    # '  left single quote
    "\u201C": '"',    # "  left double quote
    "\u201D": '"',    # "  right double quote
    "\u2026": "...",  # …  ellipsis
}


def _clean(text: str) -> str:
    """Replace Unicode characters that Slack Workflow triggers render as '?'."""
    for char, replacement in _UNICODE_MAP.items():
        text = text.replace(char, replacement)
    return text


def _format_message(signals: dict) -> str:
    product = signals["product"].get("code", "unknown")
    operation = signals["operation"] or "unknown"
    order = signals["order"].get("code", "unknown")
    worker = signals["worker"]
    reasons = "\n".join(f"• {r}" for r in signals["reasons"])
    return (
        f"*Quality alert on product `{product}`*\n"
        f"Operation: {operation} | Order: {order} | Worker: {worker}\n\n"
        f"{reasons}"
    )


def _format_related_productions(signals: dict) -> str:
    order = signals["order"]
    consumptions = signals["consumptions"]

    lines = [f"• Order {order.get('code', '?')} (id={order.get('id', '?')})"]
    if consumptions:
        lines.append("  Consumed materials:")
        for c in consumptions:
            prod = c.get("product", {})
            lot = c.get("lot") or {}
            lot_str = f"  lot={lot}" if lot else ""
            lines.append(
                f"    - {prod.get('code', '?')} qty={c.get('quantity', '?')}{lot_str}"
            )
    return "\n".join(lines)


async def send_quality_alert(
    signals: dict,
    related_cos: str = "Pending RCA - no change orders identified yet",
    message: str = None,
) -> bool:
    """
    Send a quality alert to Slack.

    Args:
        signals: Output of extract_quality_signals() from webhook_receiver.py
        related_cos: Change order context (populated by RCA agent)
        message: AI-crafted message text; falls back to _format_message if not provided

    Returns:
        True if the message was accepted by Slack, False otherwise.
    """
    payload = {
        "Message": _clean(message if message else _format_message(signals)),
        "Related_COs": _clean(related_cos),
        "Related_Productions": _clean(_format_related_productions(signals)),
    }

    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL is not set - skipping Slack alert")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
        if resp.status_code == 200:
            logger.info("Slack alert sent for order=%s", signals["order"].get("code"))
            return True
        else:
            logger.error(
                "Slack rejected the alert: status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except Exception as exc:
        logger.error("Failed to send Slack alert: %s", exc)
        return False
