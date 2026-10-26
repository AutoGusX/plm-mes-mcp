"""
Fusion Operations MCP Server

Designed to run behind an API gateway such as Apigee (handles APS OAuth).
Fusion Operations API uses its own token system (API_KEY:API_SECRET),
managed internally by FusionOpsTokenManager.

Local dev:
    uv run python -m src.server

Cloud:
    uv run python -m src.server --disable-auth
"""

import argparse
import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

from .auth import create_token_manager, validate_gateway_secret
from .client import FusionOperationsClient
from .tools import clients_suppliers, cross_system, inventory, production_orders, products, sales_purchase_orders

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Token manager is shared across all requests (handles auto-refresh)
_token_manager = create_token_manager()

mcp = FastMCP(
    "fusion-operations-mcp",
    instructions=(
        "You have access to Autodesk Fusion Operations (MES). "
        "Use these tools to manage manufacturing execution: production orders, products, "
        "BOMs, sales and purchase orders, inventory movements, clients, and suppliers. "
        "Rate limit: 120 requests/minute. Always confirm before creating or deleting records."
    ),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8001")),
    streamable_http_path="/mcp",
)


def _get_client(ctx) -> FusionOperationsClient:
    """Validate gateway secret and return a configured API client."""
    headers = getattr(ctx, "request_headers", {}) or {}
    validate_gateway_secret(headers.get("x-ads-gateway-secret"))
    return FusionOperationsClient(token_manager=_token_manager)


# ------------------------------------------------------------------
# Production Order Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_production_orders(
    ctx: Context,
    page: int = 1,
    page_size: int = 25,
    code: str | None = None,
    due_date_before: str | None = None,
    due_date_after: str | None = None,
) -> dict:
    """
    List production orders with optional filters.

    Args:
        page: Page number
        page_size: Results per page (max 25 default)
        code: Filter by order code
        due_date_before: ISO 8601 date — orders due before this date
        due_date_after: ISO 8601 date — orders due after this date
    """
    client = _get_client(ctx)
    return await production_orders.list_orders(
        client, page, page_size, code, due_date_before, due_date_after
    )


@mcp.tool()
async def get_production_order(ctx: Context, order_id: str) -> dict:
    """
    Get a single production order by ID.

    Args:
        order_id: Production order ID
    """
    client = _get_client(ctx)
    return await production_orders.get_order(client, order_id)


@mcp.tool()
async def create_production_order(
    ctx: Context,
    code: str,
    product_id: str,
    quantity: float,
    due_date: str,
    notes: str = "",
) -> dict:
    """
    Create a new production order.

    Args:
        code: Unique order code (e.g. PO-2024-001)
        product_id: Product ID to manufacture
        quantity: Quantity to produce
        due_date: ISO 8601 due date (e.g. 2024-12-31T00:00:00Z)
        notes: Optional notes
    """
    client = _get_client(ctx)
    return await production_orders.create_order(
        client, code, product_id, quantity, due_date, notes
    )


@mcp.tool()
async def update_production_order(ctx: Context, order_id: str, data: dict) -> dict:
    """
    Update an existing production order.

    Args:
        order_id: Production order ID to update
        data: Fields to update (code, quantity, due_date, notes, etc.)
    """
    client = _get_client(ctx)
    return await production_orders.update_order(client, order_id, data)


@mcp.tool()
async def delete_production_order(ctx: Context, order_id: str) -> dict:
    """
    Delete a production order.

    Args:
        order_id: Production order ID to delete
    """
    client = _get_client(ctx)
    return await production_orders.delete_order(client, order_id)


@mcp.tool()
async def activate_production_order(ctx: Context, order_id: str) -> dict:
    """
    Activate (release) a production order to the shop floor.

    Args:
        order_id: Production order ID to activate
    """
    client = _get_client(ctx)
    return await production_orders.activate_order(client, order_id)


@mcp.tool()
async def notify_production_problem(
    ctx: Context, order_id: str, problem_type: str, description: str, severity: str = "Medium"
) -> dict:
    """
    Log a problem against a production order.

    Args:
        order_id: Production order ID
        problem_type: Type of problem (e.g. Quality Issue, Machine Failure)
        description: Detailed description
        severity: Low, Medium, or High
    """
    client = _get_client(ctx)
    return await production_orders.notify_problem(
        client, order_id, problem_type, description, severity
    )


# ------------------------------------------------------------------
# Product Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_products(ctx: Context, page: int = 1, page_size: int = 25) -> dict:
    """List all products/parts in Fusion Operations."""
    client = _get_client(ctx)
    return await products.list_products(client, page, page_size)


@mcp.tool()
async def get_product(ctx: Context, product_id: str) -> dict:
    """
    Get product details including BOM.

    Args:
        product_id: Product ID
    """
    client = _get_client(ctx)
    return await products.get_product(client, product_id)


@mcp.tool()
async def create_product(ctx: Context, code: str, name: str, observations: str = "") -> dict:
    """
    Create a new product record.

    Args:
        code: Unique product code (e.g. WIDGET-A or 9400-000)
        name: Product name/title
        observations: Optional free-text notes
    """
    client = _get_client(ctx)
    return await products.create_product(client, code, name, observations)


@mcp.tool()
async def update_product_bom(ctx: Context, product_id: str, bom_items: list[dict]) -> dict:
    """
    Update the Bill of Materials for a product.

    Args:
        product_id: Product ID
        bom_items: List of BOM items, each with:
                   {component_id, component_code, quantity, unit}

    Example bom_items:
        [{"component_id": "COMP-001", "quantity": 4, "unit": "pcs"}]
    """
    client = _get_client(ctx)
    return await products.update_bom(client, product_id, bom_items)


# ------------------------------------------------------------------
# Sales Order Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_sales_orders(
    ctx: Context, page: int = 1, page_size: int = 25, code: str | None = None
) -> dict:
    """List sales orders with optional code filter."""
    client = _get_client(ctx)
    return await sales_purchase_orders.list_sales_orders(client, page, page_size, code)


@mcp.tool()
async def get_sales_order(ctx: Context, order_id: str) -> dict:
    """Get a specific sales order by ID."""
    client = _get_client(ctx)
    return await sales_purchase_orders.get_sales_order(client, order_id)


@mcp.tool()
async def create_sales_order(
    ctx: Context, code: str, client_id: str, items: list[dict], due_date: str, shipping_address: str = ""
) -> dict:
    """
    Create a new sales order.

    Args:
        code: Unique order code
        client_id: Client ID
        items: List of {product_id, quantity} objects
        due_date: ISO 8601 due date
        shipping_address: Delivery address
    """
    client = _get_client(ctx)
    return await sales_purchase_orders.create_sales_order(
        client, code, client_id, items, due_date, shipping_address
    )


# ------------------------------------------------------------------
# Purchase Order Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_purchase_orders(ctx: Context, page: int = 1, page_size: int = 25) -> dict:
    """List purchase orders."""
    client = _get_client(ctx)
    return await sales_purchase_orders.list_purchase_orders(client, page, page_size)


@mcp.tool()
async def get_purchase_order(ctx: Context, order_id: str) -> dict:
    """Get a specific purchase order by ID."""
    client = _get_client(ctx)
    return await sales_purchase_orders.get_purchase_order(client, order_id)


@mcp.tool()
async def create_purchase_order(
    ctx: Context, code: str, supplier_id: str, items: list[dict], expected_date: str
) -> dict:
    """
    Create a new purchase order.

    Args:
        code: Unique order code
        supplier_id: Supplier ID
        items: List of {product_id, quantity} objects
        expected_date: ISO 8601 expected delivery date
    """
    client = _get_client(ctx)
    return await sales_purchase_orders.create_purchase_order(
        client, code, supplier_id, items, expected_date
    )


# ------------------------------------------------------------------
# Inventory Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_inventory_movements(ctx: Context, page: int = 1, page_size: int = 25) -> dict:
    """List inventory movements."""
    client = _get_client(ctx)
    return await inventory.list_movements(client, page, page_size)


@mcp.tool()
async def create_inventory_movement(
    ctx: Context,
    product_id: str,
    quantity: float,
    from_location: str,
    to_location: str,
    movement_date: str,
    notes: str = "",
) -> dict:
    """
    Record a stock/inventory movement between locations.

    Args:
        product_id: Product ID being moved
        quantity: Quantity to move
        from_location: Source location
        to_location: Destination location
        movement_date: ISO 8601 movement date
        notes: Optional notes
    """
    client = _get_client(ctx)
    return await inventory.create_movement(
        client, product_id, quantity, from_location, to_location, movement_date, notes
    )


# ------------------------------------------------------------------
# Client & Supplier Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_clients(ctx: Context, page: int = 1, page_size: int = 25) -> dict:
    """List all clients/customers."""
    client = _get_client(ctx)
    return await clients_suppliers.list_clients(client, page, page_size)


@mcp.tool()
async def get_client(ctx: Context, client_id: str) -> dict:
    """Get a specific client by ID."""
    client = _get_client(ctx)
    return await clients_suppliers.get_client(client, client_id)


@mcp.tool()
async def list_suppliers(ctx: Context, page: int = 1, page_size: int = 25) -> dict:
    """List all suppliers."""
    client = _get_client(ctx)
    return await clients_suppliers.list_suppliers(client, page, page_size)


@mcp.tool()
async def get_supplier(ctx: Context, supplier_id: str) -> dict:
    """Get a specific supplier by ID."""
    client = _get_client(ctx)
    return await clients_suppliers.get_supplier(client, supplier_id)


# ------------------------------------------------------------------
# Cross-System Tools (PLM ↔ MES Orchestration)
# ------------------------------------------------------------------


@mcp.tool()
async def sync_product_from_plm(
    ctx: Context,
    plm_dms_id: int,
    plm_description: str,
    observations: str = "",
    bom_items: list[dict] | None = None,
) -> dict:
    """
    Create or update a single product in Fusion Operations from a PLM item.

    Product code = PLM DMS ID (stable unique key shared across PLM and MES).
    Product name = full PLM description (e.g. '9400-000 - Chiller-2-2000-400').

    For a full BOM sync (parent + all components in one call), use sync_plm_bom.

    Args:
        plm_dms_id: PLM item DMS ID — becomes the Fusion Operations product code
        plm_description: Full PLM item description
        observations: Optional traceability notes
        bom_items: BOM components from get_bom_for_item (surfaces pending syncs)
    """
    client = _get_client(ctx)
    return await cross_system.sync_product_from_plm(
        client, str(plm_dms_id), plm_description, observations, bom_items
    )


@mcp.tool()
async def sync_plm_bom(
    ctx: Context,
    parent_dms_id: int,
    parent_description: str,
    bom_components: list[dict],
    plm_ws_id: int | None = None,
) -> dict:
    """
    Full BOM sync from PLM to Fusion Operations in one call.

    Product code strategy: PLM DMS ID → Fusion Operations product code.
    Ensures stable 1:1 alignment regardless of PLM part number changes.

    Flow (all automated):
      1. Create/update each BOM component product (code = PLM DMS ID)
      2. Create/update parent product with an 'assembly' operation
      3. POST /api/v1/bom to link all components to the parent

    Typical usage:
      1. Call get_bom_for_item(ws_id, item_id) in fusion-manage-mcp
      2. Pass bom_components from that result directly here

    Args:
        parent_dms_id: PLM DMS ID of the assembly (e.g. 15466 for the Chiller)
        parent_description: Full PLM description (e.g. '9400-000 - Chiller-2-2000-400')
        bom_components: bom_components list from get_bom_for_item
                        [{id, description, lifecycle_status, release, workspace_id}]
        plm_ws_id: PLM workspace ID for traceability notes (optional)
    """
    client = _get_client(ctx)
    return await cross_system.sync_plm_bom(
        client, parent_dms_id, parent_description, bom_components, plm_ws_id
    )


@mcp.tool()
async def create_production_order_from_plm_item(
    ctx: Context,
    plm_item_number: str,
    order_code: str,
    quantity: float,
    due_date: str,
    notes: str = "",
) -> dict:
    """
    Create a MES production order for a PLM part number.
    The part must already exist in Fusion Operations — use sync_product_from_plm first.

    Args:
        plm_item_number: PLM part number (must match an existing MES product code)
        order_code: New production order code (e.g. PO-2024-001)
        quantity: Quantity to produce
        due_date: ISO 8601 due date
        notes: Optional notes (include ECO reference for traceability)
    """
    client = _get_client(ctx)
    return await cross_system.create_production_order_from_plm_item(
        client, plm_item_number, order_code, quantity, due_date, notes
    )


@mcp.tool()
async def find_orders_by_product_code(
    ctx: Context,
    product_code: str,
    active_only: bool = True,
) -> list:
    """
    Find production orders for a specific product/part code.
    Core tool for Change Impact Analysis — given a PLM part number,
    surface all affected WOs in MES.

    Args:
        product_code: PLM part number or MES product code
        active_only: If true, only return non-completed orders (default: true)
    """
    client = _get_client(ctx)
    return await cross_system.find_orders_by_product_code(
        client, product_code, active_only
    )


@mcp.tool()
async def get_production_summary(
    ctx: Context,
    product_code: str | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
) -> dict:
    """
    Get aggregated production statistics for Root Cause Analysis
    and Work Instruction Generation.

    Returns: order count, quantities, completion rate, status breakdown.
    Cross-reference the results with get_items_changed_since in
    fusion-manage-mcp to correlate defect spikes with engineering changes.

    Args:
        product_code: Filter to a specific product (optional)
        since_date: ISO 8601 start date (e.g. '2024-11-11T00:00:00Z')
        until_date: ISO 8601 end date
    """
    client = _get_client(ctx)
    return await cross_system.get_production_summary(
        client, product_code, since_date, until_date
    )


@mcp.tool()
async def preview_cia_order_date_changes(
    ctx: Context,
    at_risk_orders: list[dict],
    new_start_date: str | None = None,
    new_due_date: str | None = None,
) -> dict:
    """
    Preview date changes for production orders identified in a Change Impact Analysis.

    Returns a summary of every order that would be updated (order ID, code, risk level,
    current due date, proposed new dates) plus the list of order_ids to pass to
    apply_cia_order_date_changes.

    IMPORTANT: Always present this preview to the user and obtain explicit confirmation
    before calling apply_cia_order_date_changes.

    Args:
        at_risk_orders: Output of get_active_orders_at_risk
        new_start_date: New start date in ISO 8601 format (optional)
        new_due_date:   New due date in ISO 8601 format (optional)
    """
    return cross_system.preview_cia_date_changes(at_risk_orders, new_start_date, new_due_date)


@mcp.tool()
async def apply_cia_order_date_changes(
    ctx: Context,
    order_ids: list[str],
    new_start_date: str | None = None,
    new_due_date: str | None = None,
) -> dict:
    """
    Apply start/due date changes to a list of production orders.

    PREREQUISITE: Call preview_cia_order_date_changes first and present the results
    to the user. Only call this tool after the user has explicitly confirmed the changes.

    Args:
        order_ids:      List of production order IDs to update
                        (use the order_ids field from preview_cia_order_date_changes)
        new_start_date: New start date in ISO 8601 format (optional)
        new_due_date:   New due date in ISO 8601 format (optional)
    """
    client = _get_client(ctx)
    return await cross_system.apply_cia_date_changes(client, order_ids, new_start_date, new_due_date)


@mcp.tool()
async def get_active_orders_at_risk(
    ctx: Context,
    product_codes: list[str],
) -> list[dict]:
    """
    Given a list of PLM part numbers, find all active MES production orders
    and classify each by risk level (HIGH/MEDIUM/LOW based on completion %).

    Used in Change Impact Analysis — after identifying affected parts from
    an ECO in PLM, call this to surface the WO impact and prioritize response.

    HIGH risk: >25% complete (rework already in progress)
    MEDIUM risk: started but <25% complete
    LOW risk: not yet started

    Args:
        product_codes: List of PLM part numbers / MES product codes
    """
    client = _get_client(ctx)
    return await cross_system.get_active_orders_at_risk(client, product_codes)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fusion Operations MCP Server")
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
            "Starting fusion-operations-mcp on %s:%d (auth_disabled=%s)",
            os.getenv("HOST", "0.0.0.0"),
            int(os.getenv("PORT", "8001")),
            args.disable_auth,
        )
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
