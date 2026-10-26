"""
Quality Monitor - Root Cause Analysis

Queries the PLM MCP server (fusion-manage-mcp) to find Change Orders
related to the product that triggered a quality alert.

The MES product code is the PLM DMS ID (stable 1:1 mapping). When the
product code is numeric we skip the search and call views/11 directly.
"""

import logging
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("quality-monitor.rca")

PLM_MCP_URL = os.getenv("PLM_MCP_URL", "http://localhost:8003/mcp")
PLM_ITEMS_WS_ID = int(os.getenv("PLM_ITEMS_WS_ID", "57"))


async def _call_tool(session: ClientSession, name: str, arguments: dict):
    result = await session.call_tool(name, arguments)
    # Unwrap the TextContent list that MCP returns
    if result.content and hasattr(result.content[0], "text"):
        import json
        return json.loads(result.content[0].text)
    return {}


async def fetch_change_orders(item_id: int) -> dict:
    """
    Fetch raw Change Orders dict for a PLM item by DMS ID.
    Called directly by the RCA agent tool.

    Returns the raw change_orders dict from the PLM MCP, or raises on error.
    """
    try:
        async with streamablehttp_client(PLM_MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await _call_tool(
                    session,
                    "get_item_change_orders",
                    {"ws_id": PLM_ITEMS_WS_ID, "item_id": item_id},
                )
    except* Exception as eg:
        # Unwrap ExceptionGroup from MCP TaskGroup and re-raise the first real cause
        raise eg.exceptions[0] from None


async def get_related_cos(product_code: str) -> str:
    """
    Look up a product in PLM and return a formatted summary of its related
    Change Orders, ready to drop into the Slack Related_COs field.

    Args:
        product_code: The product/part code from the quality event payload
                      (e.g. "Table")

    Returns:
        Human-readable string listing related COs, or a fallback message.
    """
    try:
        async with streamablehttp_client(PLM_MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # MES product code == PLM DMS ID when numeric — skip search
                if str(product_code).isdigit():
                    item_id = int(product_code)
                    ws_id = PLM_ITEMS_WS_ID
                    logger.info("Product code %s is a DMS ID — skipping search", product_code)
                else:
                    search_result = await _call_tool(
                        session,
                        "search_items_global",
                        {"query": product_code, "limit": 5},
                    )
                    items = search_result.get("results", []) or search_result.get("items", [])
                    if not items:
                        return f"No PLM item found matching product code '{product_code}'"
                    item = items[0]
                    item_id = item.get("dms_id") or item.get("id") or item.get("dmsId")
                    ws_id = item.get("workspace_id", PLM_ITEMS_WS_ID)
                    if not item_id:
                        return f"PLM search matched but could not resolve DMS ID for '{product_code}'"
                    logger.info("Resolved '%s' to DMS ID %s via search", product_code, item_id)

                # Step 2: get Change Orders related to this item via views/11
                cos_result = await _call_tool(
                    session,
                    "get_item_change_orders",
                    {"ws_id": ws_id, "item_id": int(item_id)},
                )

                cos = cos_result.get("change_orders", [])
                count = cos_result.get("change_order_count", 0)

                if not cos:
                    return f"No related Change Orders found for product {item_id}"

                lines = [f"{count} Change Order(s) linked to product {item_id}:"]
                for co in cos:
                    title = co.get("title") or f"CO id={co.get('co_id')}"
                    state = co.get("current_state") or "unknown state"
                    transition = co.get("target_transition", "")
                    effectivity = co.get("effectivity_date", "")
                    line = f"• {title}  [{state}]"
                    if transition:
                        line += f"  → {transition}"
                    if effectivity:
                        line += f"  (effective {effectivity[:10]})"
                    lines.append(line)

                return "\n".join(lines)

    except Exception as exc:
        logger.error("RCA lookup failed for product '%s': %s", product_code, exc)
        return f"RCA lookup failed: {exc}"
