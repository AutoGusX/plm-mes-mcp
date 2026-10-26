"""
Fusion Manage MCP Server

Designed to run behind an API gateway such as Apigee (handles APS OAuth).
Run with --disable-auth for cloud deployment; auth context comes
from x-ads-token-data header injected by the proxy.

Local dev:
    uv run python -m src.server

Cloud (via uv):
    uv run python -m src.server --disable-auth
"""

import argparse
import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

from .auth import resolve_auth_context
from .client import FusionManageClient
from .tools import cross_system, items, reports, reporting, search as search_tools, workflows, workspaces

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "fusion-manage-mcp",
    instructions=(
        "You have access to Autodesk Fusion Manage (PLM). "
        "Use these tools to read and manage product lifecycle data: workspaces, items, "
        "attachments, workflow transitions, and reports. "
        "Always confirm destructive actions (workflow transitions, item creation) with the user."
    ),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    streamable_http_path="/mcp",
)


def _get_client(ctx) -> FusionManageClient:
    """
    Resolve auth context from MCP request headers and return a configured client.
    Headers are injected by Apigee in production; env vars used in dev.
    """
    headers = getattr(ctx, "request_headers", {}) or {}
    auth = resolve_auth_context(
        token_data_header=headers.get("x-ads-token-data"),
        gateway_secret_header=headers.get("x-ads-gateway-secret"),
    )
    return FusionManageClient(auth=auth)


# ------------------------------------------------------------------
# Workspace Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_workspaces(ctx: Context) -> list:
    """List all workspaces in the Fusion Manage tenant."""
    client = _get_client(ctx)
    return await workspaces.list_workspaces(client)


@mcp.tool()
async def get_workspace_sections(ctx: Context, ws_id: int) -> dict:
    """
    Get the field sections and structure of a workspace.
    Useful for discovering field IDs before creating or updating items.

    Args:
        ws_id: Workspace ID
    """
    client = _get_client(ctx)
    return await workspaces.get_workspace_sections(client, ws_id)


# ------------------------------------------------------------------
# Item Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_workspace_items(
    ctx: Context, ws_id: int, page: int = 1, page_size: int = 50
) -> dict:
    """
    List items in a workspace (paginated).

    Args:
        ws_id: Workspace ID
        page: Page number (default 1)
        page_size: Items per page (default 50, max 100)
    """
    client = _get_client(ctx)
    return await items.list_items(client, ws_id, page, page_size)


@mcp.tool()
async def get_workspace_item(ctx: Context, ws_id: int, item_id: int) -> dict:
    """
    Get a single item by ID.

    Args:
        ws_id: Workspace ID
        item_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await items.get_item(client, ws_id, item_id)


@mcp.tool()
async def search_workspace_items(
    ctx: Context,
    ws_id: int,
    search_text: str = "",
    field_filters: list[dict] | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "TITLE",
    sort_order: str = "ASC",
) -> dict:
    """
    Search items in a workspace with optional text search and field filters.

    Args:
        ws_id: Workspace ID
        search_text: Free text to search across item fields
        field_filters: List of {fieldID, value} filter objects
        page: Page number
        page_size: Results per page
        sort_field: Field ID to sort by (default TITLE)
        sort_order: ASC or DESC
    """
    client = _get_client(ctx)
    return await items.search_items(
        client, ws_id, search_text, field_filters or [], page, page_size, sort_field, sort_order
    )


@mcp.tool()
async def create_workspace_item(ctx: Context, ws_id: int, fields: list[dict]) -> dict:
    """
    Create a new item in a workspace.

    Args:
        ws_id: Workspace ID
        fields: List of {fieldId, value} objects. Use get_workspace_sections
                to discover available field IDs.

    Example fields:
        [{"fieldId": "TITLE", "value": "New Part"}, {"fieldId": "DESCRIPTION", "value": "..."}]
    """
    client = _get_client(ctx)
    return await items.create_item(client, ws_id, fields)


@mcp.tool()
async def update_workspace_item(
    ctx: Context, ws_id: int, item_id: int, fields: list[dict]
) -> dict:
    """
    Update fields on an existing item. Only supply fields to be changed.

    Args:
        ws_id: Workspace ID
        item_id: Item ID to update
        fields: List of {fieldId, value} objects to update
    """
    client = _get_client(ctx)
    return await items.update_item(client, ws_id, item_id, fields)


# ------------------------------------------------------------------
# Attachment Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_item_attachments(ctx: Context, ws_id: int, dms_id: int) -> list:
    """
    List all file attachments on an item.

    Args:
        ws_id: Workspace ID
        dms_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await items.list_attachments(client, ws_id, dms_id)


# ------------------------------------------------------------------
# Workflow Tools
# ------------------------------------------------------------------


@mcp.tool()
async def get_workflow_history(ctx: Context, ws_id: int, dms_id: int) -> dict:
    """
    Get the full workflow/lifecycle history of an item.

    Args:
        ws_id: Workspace ID
        dms_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await workflows.get_history(client, ws_id, dms_id)


@mcp.tool()
async def transition_workflow(
    ctx: Context,
    ws_id: int,
    dms_id: int,
    transition_id: int,
    step: int,
    comments: str = "",
) -> dict:
    """
    Move an item to the next workflow state.

    Args:
        ws_id: Workspace ID
        dms_id: Item (DMS) ID
        transition_id: Transition ID (from workflow definition)
        step: Target step number (must be current step + 1)
        comments: Optional transition comment
    """
    client = _get_client(ctx)
    return await workflows.transition(client, ws_id, dms_id, transition_id, step, comments)


# ------------------------------------------------------------------
# Report Tools
# ------------------------------------------------------------------


@mcp.tool()
async def get_report(ctx: Context, report_id: int) -> dict:
    """
    Retrieve report data by report ID.

    Args:
        report_id: Report ID (visible in Fusion Manage Reports admin)
    """
    client = _get_client(ctx)
    return await reports.get_report(client, report_id)


# ------------------------------------------------------------------
# Cross-System Tools (PLM ↔ MES Orchestration)
# ------------------------------------------------------------------


@mcp.tool()
async def get_released_parts(
    ctx: Context, ws_id: int, page: int = 1, page_size: int = 50
) -> dict:
    """
    Get all items currently in 'Released' lifecycle state from a workspace.
    Used for BOM Sync and Change Impact Analysis — identifies which parts
    are approved for production.

    Args:
        ws_id: Workspace ID (typically the Parts & Assemblies workspace)
        page: Page number
        page_size: Results per page
    """
    client = _get_client(ctx)
    return await cross_system.get_released_parts(client, ws_id, page, page_size)


@mcp.tool()
async def get_items_changed_since(
    ctx: Context, ws_id: int, since_date: str, page: int = 1, page_size: int = 50
) -> dict:
    """
    Find items modified on or after a given date.
    Used for Root Cause Analysis — correlate engineering changes with
    production defect spikes.

    Args:
        ws_id: Workspace ID
        since_date: ISO 8601 date (e.g. '2024-11-11T00:00:00Z')
        page: Page number
        page_size: Results per page
    """
    client = _get_client(ctx)
    return await cross_system.get_items_changed_since(client, ws_id, since_date, page, page_size)


@mcp.tool()
async def get_item_by_number(ctx: Context, ws_id: int, item_number: str) -> dict:
    """
    Find a specific item by its part/item number.
    Entry point for Change Impact Analysis — look up an ECO or part by number.

    Args:
        ws_id: Workspace ID
        item_number: The part or ECO number to find
    """
    client = _get_client(ctx)
    return await cross_system.get_item_by_number(client, ws_id, item_number)


@mcp.tool()
async def get_eco_details(ctx: Context, eco_ws_id: int, eco_id: int) -> dict:
    """
    Get full Engineering Change Order details including workflow history
    and all attached documents/drawings.
    Used as the entry point for Change Impact Analysis.

    Args:
        eco_ws_id: ECO workspace ID
        eco_id: ECO item ID
    """
    client = _get_client(ctx)
    return await cross_system.get_eco_details(client, eco_ws_id, eco_id)


@mcp.tool()
async def get_bom_for_item(ctx: Context, ws_id: int, item_id: int) -> dict:
    """
    Get an item with its full BOM relationships.
    Used for BOM Sync — fetch PLM BOM before pushing to Fusion Operations.

    Args:
        ws_id: Workspace ID
        item_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await cross_system.get_bom_for_item(client, ws_id, item_id)


@mcp.tool()
async def get_item_change_orders(ctx: Context, ws_id: int, item_id: int) -> dict:
    """
    Get Change Orders related to a specific item via views/11.

    When called on a part/assembly, returns the COs that list this item
    as an affected item. Used in quality Root Cause Analysis — given a
    part that produced waste, find which recent COs were made against it.

    Args:
        ws_id:   Workspace ID of the part (e.g. 57 for Items)
        item_id: DMS ID of the part
    """
    client = _get_client(ctx)
    return await cross_system.get_item_change_orders(client, ws_id, item_id)


@mcp.tool()
async def get_approved_suppliers_for_item(ctx: Context, ws_id: int, item_id: int) -> dict:
    """
    Get approved supplier information for an item.
    Used in Supplier Exception Handling — find qualified alternates
    when a supplier cannot meet a spec.

    Args:
        ws_id: Workspace ID
        item_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await cross_system.get_approved_suppliers_for_item(client, ws_id, item_id)


@mcp.tool()
async def get_item_sourcing(ctx: Context, ws_id: int, item_id: int) -> dict:
    """
    Get the full Approved Manufacturer/Supplier List (AML) for an item,
    including all supplier quotes with lead times and unit prices.

    Use this during Change Impact Analysis to determine realistic lead time
    for a purchased part — the default quote's leadTime is the primary source.

    Returns:
      suppliers[]: supplier name, part numbers, quotes[]
      quotes[]:    lead_time_days, unit_price, min_qty, max_qty,
                   is_default, bom_assemblies (which assemblies the quote applies to)
      min_lead_time_days:     shortest lead time across all suppliers/quotes
      default_lead_time_days: lead time on the designated default quote

    Args:
        ws_id:   Workspace ID (57 for Items)
        item_id: Item (DMS) ID
    """
    client = _get_client(ctx)
    return await cross_system.get_item_sourcing(client, ws_id, item_id)


# ------------------------------------------------------------------
# Reporting Tools
# ------------------------------------------------------------------


@mcp.tool()
async def generate_cia_pptx(
    ctx: Context,
    co: dict,
    affected_items: list,
    at_risk: list,
    output_path: str = "",
) -> dict:
    """
    Generate a PowerPoint (PPTX) Change Impact Analysis report.

    Produces a 6-slide deck with:
      1. Title slide (CO title, urgency badge, link to CO in Fusion Manage)
      2. Change Order summary (affected items with hyperlinks)
      3. Item detail & AML sourcing (suppliers, quotes, lead times)
      4. Production order impact table (risk color-coded, BOM ancestry noted)
      5. Lead time vs. order timeline (visual bar)
      6. Recommendations & next actions

    All PLM items are hyperlinked directly to Fusion Manage.

    Args:
        co:             dict — title, current_state, co_id, ws_id
        affected_items: list — one entry per affected item, each with:
                          dms_id, ws_id, title, transition, from_rel, to_rel,
                          effectivity, ops_code, procurement, material,
                          dimensions, mass_kg, pdm_status, pdm_revision,
                          plm_lifecycle, where_used[], sourcing{}
        at_risk:        list — from get_active_orders_at_risk, each with:
                          part, parent, order_code, risk, match_type,
                          status, active, pct, due, days_until_due
        output_path:    optional file path; defaults to a temp .pptx file

    Returns:
        {"success": true, "file_path": "<absolute path to .pptx>"}
    """
    tenant = os.getenv("FUSION_MANAGE_TENANT", "")
    return await reporting.generate_cia_pptx(
        tenant=tenant,
        co=co,
        affected_items=affected_items,
        at_risk=at_risk,
        output_path=output_path or None,
    )


# ------------------------------------------------------------------
# Search Tools
# ------------------------------------------------------------------


@mcp.tool()
async def search_all(
    ctx: Context,
    query: str,
    revision: int = 1,
    limit: int = 50,
    workspace_filter: int | None = None,
) -> dict:
    """
    Full-text search across all Fusion Manage workspaces.

    Args:
        query: Free-text search string (part number, description, etc.)
        revision: 1=latest only (default), 2=all revisions, 3=working/unreleased
        limit: Max results to return (default 50)
        workspace_filter: Optionally narrow to a specific workspace ID
    """
    client = _get_client(ctx)
    return await search_tools.search(client, query, revision, limit, workspace_filter)


@mcp.tool()
async def search_items_global(
    ctx: Context,
    query: str,
    revision: int = 1,
    limit: int = 50,
) -> dict:
    """
    Full-text search restricted to the Parts & Assemblies workspace (WS 57).
    Best for BOM sync, part lookup, and change impact analysis.

    Args:
        query: Free-text search string (part number, description, etc.)
        revision: 1=latest only (default), 2=all revisions, 3=working/unreleased
        limit: Max results to return (default 50)
    """
    client = _get_client(ctx)
    return await search_tools.search_items(client, query, revision, limit)


@mcp.tool()
async def search_change_orders(
    ctx: Context,
    query: str,
    limit: int = 50,
) -> dict:
    """
    Full-text search restricted to the Change Orders workspace (WS 84).

    Args:
        query: Search string (ECO number, title, etc.)
        limit: Max results to return (default 50)
    """
    client = _get_client(ctx)
    return await search_tools.search_change_orders(client, query, limit)


@mcp.tool()
async def search_non_conformances(
    ctx: Context,
    query: str,
    limit: int = 50,
) -> dict:
    """
    Full-text search restricted to the Non Conformances workspace (WS 98).

    Args:
        query: Search string (NCR number, description, etc.)
        limit: Max results to return (default 50)
    """
    client = _get_client(ctx)
    return await search_tools.search_non_conformances(client, query, limit)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fusion Manage MCP Server")
    parser.add_argument(
        "--disable-auth",
        action="store_true",
        help="Disable MCP-level auth (Apigee handles it in production)",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run with stdio transport (for Claude desktop / local MCP clients)",
    )
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        logger.info(
            "Starting fusion-manage-mcp on %s:%d (auth_disabled=%s)",
            os.getenv("HOST", "0.0.0.0"),
            int(os.getenv("PORT", "8000")),
            args.disable_auth,
        )
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
