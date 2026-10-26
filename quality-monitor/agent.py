"""
Quality Monitor - RCA Agent

Uses Claude with all tools from both PLM (Fusion Manage) and MES
(Fusion Operations) MCP servers to analyse a quality event and
craft the Slack alert message.

Tool discovery is dynamic: at startup the agent lists tools from
both servers, so no hard-coded tool definitions are needed here.
"""

import contextlib
import json
import logging
import os

import anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("quality-monitor.agent")

PLM_MCP_URL = os.getenv("PLM_MCP_URL", "http://localhost:8003/mcp")
MES_MCP_URL = os.getenv("MES_MCP_URL", "http://localhost:8001/mcp")

SYSTEM_PROMPT = """\
You are a manufacturing quality analyst with access to both PLM (Fusion Manage) \
and MES (Fusion Operations) systems.

When given a quality event:
1. Call get_item_change_orders (PLM) with ws_id=57 and the product DMS ID to fetch \
linked Change Orders.
2. If consumed materials are listed, check their Change Orders too (they may be the \
root cause).
3. Analyse whether any recent or in-flight COs could explain the quality issue.
4. Return your response in exactly this format:

SLACK_MESSAGE:
<2-4 sentence summary for a Slack channel - product, operation, order, \
what went wrong, and a brief root-cause hypothesis if the COs suggest one>

RELATED_COS:
<Formatted list of Change Orders with state and relevance, \
or "No related Change Orders found">

Important: use only plain ASCII characters. Do not use arrows (->), \
em dashes (--), bullets (*), or any Unicode. \
Keep language concise and factual. Do not invent data."""


def _mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP tool definition to Anthropic SDK format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


@contextlib.asynccontextmanager
async def _mcp_sessions():
    """
    Open PLM and MES MCP sessions and yield
    (plm_session, mes_session, all_tools, tool_map).
    """
    async with streamablehttp_client(PLM_MCP_URL) as (plm_read, plm_write, _):
        async with ClientSession(plm_read, plm_write) as plm_session:
            await plm_session.initialize()
            async with streamablehttp_client(MES_MCP_URL) as (mes_read, mes_write, _):
                async with ClientSession(mes_read, mes_write) as mes_session:
                    await mes_session.initialize()

                    plm_tools = (await plm_session.list_tools()).tools
                    mes_tools = (await mes_session.list_tools()).tools

                    all_tools = [_mcp_tool_to_anthropic(t) for t in plm_tools + mes_tools]
                    tool_map = {t.name: plm_session for t in plm_tools}
                    tool_map.update({t.name: mes_session for t in mes_tools})

                    logger.info(
                        "MCP sessions ready: %d PLM tools, %d MES tools",
                        len(plm_tools), len(mes_tools),
                    )
                    yield plm_session, mes_session, all_tools, tool_map


def _build_event_prompt(signals: dict) -> str:
    product = signals["product"]
    consumptions = signals.get("consumptions", [])
    waste = signals.get("waste_items", [])

    lines = [
        f"Product: {product.get('code', '?')} (DMS ID: {product.get('id', '?')})",
        f"Operation: {signals['operation']}",
        f"Production Order: {signals['order'].get('code', '?')} (id={signals['order'].get('id', '?')})",
        f"Worker: {signals['worker']}",
        f"Event Time: {signals['event_time']}",
        "",
        "Quality triggers:",
    ]
    for r in signals["reasons"]:
        lines.append(f"  - {r}")

    if waste:
        lines.append("")
        lines.append("Waste items:")
        for w in waste:
            waste_code = w.get("waste", {}).get("code", "?")
            lines.append(f"  - {waste_code}  qty={w.get('quantity', '?')}")

    if consumptions:
        lines.append("")
        lines.append("Consumed materials (root-cause candidates):")
        for c in consumptions:
            prod = c.get("product", {})
            lot = c.get("lot") or {}
            lot_str = f"  lot={lot}" if lot else ""
            lines.append(
                f"  - {prod.get('code', '?')} (id={prod.get('id', '?')})"
                f"  qty={c.get('quantity', '?')}{lot_str}"
            )

    return "\n".join(lines)


async def run_rca_agent(signals: dict) -> dict:
    """
    Run the RCA agent for a quality event.

    Returns:
        {
            "slack_message": str,   # AI-crafted alert text for the Message field
            "related_cos":  str,    # Formatted CO list for the Related_COs field
        }
    """
    try:
        async with _mcp_sessions() as (_, __, all_tools, tool_map):
            client = anthropic.AsyncAnthropic()
            messages = [{"role": "user", "content": _build_event_prompt(signals)}]

            for _ in range(8):
                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=all_tools,
                    messages=messages,
                )

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            session = tool_map.get(block.name)
                            if session:
                                try:
                                    result = await session.call_tool(block.name, block.input)
                                    if result.content and hasattr(result.content[0], "text"):
                                        result_text = result.content[0].text
                                    else:
                                        result_text = json.dumps({"error": "empty response"})
                                except Exception as exc:
                                    logger.error("Tool %s failed: %s", block.name, exc)
                                    result_text = json.dumps({"error": str(exc)})
                            else:
                                result_text = json.dumps({"error": f"Unknown tool: {block.name}"})

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })
                    messages.append({"role": "user", "content": tool_results})

                elif response.stop_reason == "end_turn":
                    full_text = "".join(
                        block.text for block in response.content if hasattr(block, "text")
                    )
                    return _parse_agent_response(full_text, signals)

    except Exception as exc:
        logger.error("RCA agent failed: %s", exc, exc_info=True)
        return _fallback(signals)

    logger.warning("RCA agent loop exhausted without end_turn")
    return _fallback(signals)


def _parse_agent_response(text: str, signals: dict) -> dict:
    """Split the agent's SLACK_MESSAGE / RELATED_COS sections."""
    if "SLACK_MESSAGE:" in text and "RELATED_COS:" in text:
        parts = text.split("RELATED_COS:", 1)
        slack_message = parts[0].replace("SLACK_MESSAGE:", "").strip()
        related_cos = parts[1].strip()
    elif "SLACK_MESSAGE:" in text:
        slack_message = text.split("SLACK_MESSAGE:", 1)[1].strip()
        related_cos = "No Change Order analysis available"
    else:
        slack_message = text.strip()
        related_cos = "No Change Order analysis available"

    return {"slack_message": slack_message, "related_cos": related_cos}


def _fallback(signals: dict) -> dict:
    product = signals["product"].get("code", "?")
    order = signals["order"].get("code", "?")
    reasons = "\n".join(f"- {r}" for r in signals["reasons"])
    return {
        "slack_message": (
            f"*Quality alert on product `{product}`*\n"
            f"Operation: {signals['operation']} | Order: {order} | Worker: {signals['worker']}\n\n"
            f"{reasons}"
        ),
        "related_cos": "RCA agent did not complete - check logs",
    }
