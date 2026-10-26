"""
Cross-system tools for PLM ↔ MES orchestration.

These tools support the 5 use cases in use-cases.md by providing
targeted MES queries that AI agents combine with PLM data from
the fusion-manage-mcp server.

Fusion Operations API facts (verified against live API):
- All list endpoints return plain JSON arrays (no pagination wrapper)
- Field names are kebab-case: due-date, start-date, is-active, running-status
- Products are identified by `code` (not an `id` field)
- Production orders reference products via products[].product = product_code
- POST /authorization needs body {"scopes": ["productions_write"]}, returns {"token": "..."}

Product code strategy (PLM ↔ MES alignment):
- Fusion Operations product `code` = PLM DMS ID (string, e.g. "15466")
- Fusion Operations product `name` = full PLM description (e.g. "9400-000 - Chiller-2-2000-400")
- This ensures stable 1:1 mapping regardless of PLM part number changes or revisions

BOM sync flow (verified):
1. Create each BOM component as a product (code = PLM DMS ID)
2. Create parent product with an "assembly" operation (PUT /products/{code})
3. POST /api/v1/bom with parent code + [{product-code, quantity, operation-code}]
"""

from typing import Optional
from ..client import FusionOperationsClient


async def find_orders_by_product_code(
    client: FusionOperationsClient,
    product_code: str,
    active_only: bool = True,
) -> list:
    """
    Find production orders that include a specific product code.
    Core tool for Change Impact Analysis — given a PLM part number,
    surface all affected WOs in MES.

    A production order can contain multiple products (products[] array).
    Matches if any product in the order has code == product_code.
    """
    all_orders = await client.list_production_orders()

    matched = [
        o for o in all_orders
        if any(
            p.get("product") == product_code
            for p in o.get("products", [])
        )
    ]

    if active_only:
        # is-active=True means currently running; also include non-closed orders
        matched = [
            o for o in matched
            if o.get("is-active") or o.get("running-status") not in ("closed",)
        ]

    return matched


async def get_production_summary(
    client: FusionOperationsClient,
    product_code: Optional[str] = None,
    since_date: Optional[str] = None,
    until_date: Optional[str] = None,
) -> dict:
    """
    Get a production summary for Root Cause Analysis and Work Instruction Generation.

    Returns aggregated stats: total orders, quantities, completion rates,
    and status breakdown for the requested period/product.
    """
    all_orders = await client.list_production_orders()

    # Filter by product code
    if product_code:
        all_orders = [
            o for o in all_orders
            if any(p.get("product") == product_code for p in o.get("products", []))
        ]

    # Date filtering (compare against due-date as ISO string prefix)
    if since_date:
        all_orders = [o for o in all_orders if o.get("due-date", "") >= since_date]
    if until_date:
        all_orders = [o for o in all_orders if o.get("due-date", "") <= until_date]

    total_ordered = sum(
        p.get("quantity-ordered", 0)
        for o in all_orders
        for p in o.get("products", [])
    )
    total_produced = sum(
        p.get("quantity-produced", 0)
        for o in all_orders
        for p in o.get("products", [])
    )
    completion_rate = (total_produced / total_ordered * 100) if total_ordered > 0 else 0

    status_counts: dict[str, int] = {}
    for o in all_orders:
        status = o.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "period": {"since": since_date, "until": until_date},
        "product_code": product_code,
        "order_count": len(all_orders),
        "total_ordered_quantity": total_ordered,
        "total_produced_quantity": total_produced,
        "completion_rate_pct": round(completion_rate, 1),
        "status_breakdown": status_counts,
        "orders": all_orders,
    }


_ASSEMBLY_OPERATION_CODE = "assembly"


async def _upsert_product(
    client: FusionOperationsClient,
    existing_products: list,
    code: str,
    name: str,
    observations: str,
) -> tuple[str, dict]:
    """Create or update a single product. Returns (action, product_dict)."""
    existing = next((p for p in existing_products if p.get("code") == code), None)
    body = {"code": code, "name": name, "observations": observations}
    if existing:
        product = await client.update_product(code, body)
        return "updated", product
    else:
        product = await client.create_product(body)
        return "created", product



async def sync_product_from_plm(
    client: FusionOperationsClient,
    plm_dms_id: str,
    plm_description: str,
    observations: str = "",
    bom_items: Optional[list] = None,
) -> dict:
    """
    Create or update a single product in Fusion Operations from a PLM item.

    Product code = PLM DMS ID (stable unique identifier).
    Product name = full PLM description (e.g. '9400-000 - Chiller-2-2000-400').

    For a full BOM sync (parent + all components in one call), use sync_plm_bom.

    Args:
        plm_dms_id: PLM DMS ID → used as the Fusion Operations product code
        plm_description: Full PLM item description (part number + name)
        observations: Optional traceability notes
        bom_items: If provided, surfaces BOM components that still need syncing
    """
    existing_products = await client.list_products()
    action, product = await _upsert_product(
        client, existing_products, str(plm_dms_id), plm_description, observations
    )

    result: dict = {
        "action": action,
        "product_code": str(plm_dms_id),
        "product": product,
    }

    if bom_items:
        result["bom_components_pending"] = [
            {
                "ops_product_code": str(item.get("id")),
                "plm_description": item.get("description"),
                "plm_dms_id": item.get("id"),
            }
            for item in bom_items
        ]
        result["bom_sync_note"] = (
            f"{len(bom_items)} BOM components need to be synced. "
            "Use sync_plm_bom to create all components and assemble the BOM in one call."
        )

    return result


async def sync_plm_bom(
    client: FusionOperationsClient,
    parent_dms_id: int,
    parent_description: str,
    bom_components: list,
    plm_ws_id: Optional[int] = None,
) -> dict:
    """
    Full BOM sync from PLM to Fusion Operations.

    Product code strategy: PLM DMS ID → Fusion Operations product code.
    This ensures stable 1:1 alignment regardless of PLM part number changes.

    Flow:
      1. Create/update each BOM component product (code = PLM DMS ID)
      2. Create/update parent product with an 'assembly' operation
      3. POST /api/v1/bom to link all components to the parent

    Args:
        parent_dms_id: PLM DMS ID of the assembly (e.g. 15466)
        parent_description: Full PLM description (e.g. '9400-000 - Chiller-2-2000-400')
        bom_components: List from get_bom_for_item —
                        [{id, description, lifecycle_status, release, workspace_id}]
        plm_ws_id: PLM workspace ID (for traceability notes)
    """
    existing_products = await client.list_products()

    # ── Step 1: Create all BOM component products (code = DMS ID) ─────────
    component_results = []
    errors = []

    for comp in bom_components:
        dms_id = str(comp.get("id", ""))
        desc = str(comp.get("description", ""))
        obs = (
            f"PLM DMS ID: {dms_id} | WS: {comp.get('workspace_id')} | "
            f"Lifecycle: {comp.get('lifecycle_status')} | "
            f"BOM component of DMS ID {parent_dms_id}"
        )
        try:
            action, product = await _upsert_product(
                client, existing_products, dms_id, desc, obs
            )
            if action == "created":
                existing_products.append(product)
            component_results.append({
                "action": action,
                "ops_product_code": dms_id,
                "plm_description": desc,
                "plm_dms_id": comp.get("id"),
                "ops_internal_id": product.get("id"),
            })
        except Exception as e:
            errors.append({"dms_id": dms_id, "description": desc, "error": str(e)})

    # ── Step 2: Create/update parent product with assembly operation ───────
    parent_code = str(parent_dms_id)
    parent_obs = (
        f"PLM DMS ID: {parent_dms_id} | WS: {plm_ws_id} | "
        f"Assembly with {len(bom_components)} BOM components"
    )

    # Parent product: include the assembly operation in the same PUT so that
    # re-runs don't lose the operation (PUT without existing ops → 400).
    parent_body = {
        "code": parent_code,
        "name": parent_description,
        "observations": parent_obs,
        "operations": [{"code": _ASSEMBLY_OPERATION_CODE, "name": "Assembly"}],
    }
    existing_parent = next(
        (p for p in existing_products if p.get("code") == parent_code), None
    )
    if existing_parent:
        parent_product = await client.update_product(parent_code, parent_body)
        parent_action = "updated"
    else:
        try:
            parent_product = await client.create_product(parent_body)
            parent_action = "created"
        except Exception:
            # Already exists — recover with PUT
            parent_product = await client.update_product(parent_code, parent_body)
            parent_action = "updated(recovered)"

    # ── Step 3: POST /api/v1/bom to assemble the BOM ──────────────────────
    bom_payload = [
        {
            "product-code": str(comp.get("id")),
            "quantity": 1,
            "operation-code": _ASSEMBLY_OPERATION_CODE,
        }
        for comp in bom_components
        if comp.get("id")
    ]

    bom_result = None
    bom_error = None
    if bom_payload and not errors:
        try:
            bom_result = await client.post_bom(parent_code, bom_payload)
        except Exception as e:
            bom_error = str(e)

    created_count = sum(1 for r in component_results if r["action"] == "created")
    updated_count = sum(1 for r in component_results if r["action"] == "updated")

    return {
        "parent": {
            "action": parent_action,
            "ops_product_code": parent_code,
            "plm_description": parent_description,
            "ops_internal_id": parent_product.get("id"),
        },
        "components_synced": len(component_results),
        "components_created": created_count,
        "components_updated": updated_count,
        "component_errors": len(errors),
        "components": component_results,
        "errors": errors,
        "bom_assembled": bom_result is not None and bom_error is None,
        "bom_result": bom_result,
        "bom_error": bom_error,
    }


async def create_production_order_from_plm_item(
    client: FusionOperationsClient,
    plm_item_number: str,
    order_code: str,
    quantity: float,
    due_date: str,
    notes: str = "",
) -> dict:
    """
    Create a production order in MES linked to a PLM part number.

    The PLM item number must already exist as a product in Fusion Operations
    (use sync_product_from_plm first if needed).

    Fusion Operations production order body uses kebab-case fields and
    references products by code string (not ID).

    Args:
        plm_item_number: PLM part number (must match an existing Fusion Operations product code)
        order_code: New production order code
        quantity: Quantity to produce
        due_date: ISO 8601 due date (e.g. 2024-12-31T00:00:00Z)
        notes: Optional notes (include ECO number for traceability)
    """
    # Verify product exists
    existing_products = await client.list_products()
    product = next(
        (p for p in existing_products if p.get("code") == plm_item_number),
        None,
    )

    if not product:
        return {
            "success": False,
            "error": (
                f"Product '{plm_item_number}' not found in Fusion Operations. "
                f"Run sync_product_from_plm first to create it from the PLM part."
            ),
        }

    order = await client.create_production_order({
        "code": order_code,
        "products": [
            {
                "product": plm_item_number,
                "quantity-ordered": quantity,
                "observations": notes,
            }
        ],
        "due-date": due_date,
        "notes": notes,
    })

    return {
        "success": True,
        "order": order,
        "plm_item_number": plm_item_number,
    }


def _classify_risk(order: dict) -> str:
    if order.get("is-active"):
        return "HIGH"
    if order.get("running-status", "") != "closed":
        return "MEDIUM"
    return "LOW"


def _order_entry(code: str, order: dict, match_type: str, parent_code: str | None = None) -> dict:
    prod_entry = next(
        (p for p in order.get("products", []) if p.get("product") == (parent_code or code)),
        {},
    )
    ordered = prod_entry.get("quantity-ordered", 0) or 0
    produced = prod_entry.get("quantity-produced", 0) or 0
    pct = (produced / ordered * 100) if ordered > 0 else 0
    running_status = order.get("running-status", "")

    entry = {
        "affected_product_code": code,
        "match_type": match_type,           # "direct" | "bom_component"
        "order_id": order.get("id"),
        "order_code": order.get("code"),
        "status": order.get("status"),
        "running_status": running_status,
        "is_active": order.get("is-active", False),
        "quantity_ordered": ordered,
        "quantity_produced": produced,
        "pct_complete": round(pct, 1),
        "due_date": order.get("due-date"),
        "risk_level": _classify_risk(order),
    }
    if parent_code:
        entry["parent_product_code"] = parent_code
    return entry


async def get_active_orders_at_risk(
    client: FusionOperationsClient,
    product_codes: list[str],
) -> list[dict]:
    """
    Given a list of PLM part numbers (as Fusion Operations product codes), find
    all MES production orders that are impacted — either directly or via BOM ancestry.

    Two match types are checked for each product code:

      direct        — the product itself appears on a production order
      bom_component — the product is a BOM child of an assembly that appears on
                      a production order (i.e. the order will consume this part)

    Risk levels:
      HIGH:   order is active (is-active=True) with production already underway
      MEDIUM: order is not closed but not yet active
      LOW:    order is closed/completed

    Results are deduplicated by (affected_product_code, order_id) and sorted
    HIGH → MEDIUM → LOW.
    """
    all_orders = await client.list_production_orders()
    seen: set[tuple] = set()
    at_risk = []

    def _add(entry: dict) -> None:
        key = (entry["affected_product_code"], entry["order_id"], entry["match_type"])
        if key not in seen:
            seen.add(key)
            at_risk.append(entry)

    # ── Pass 1: direct matches ─────────────────────────────────────────────
    code_set = set(product_codes)
    for order in all_orders:
        for prod in order.get("products", []):
            if prod.get("product") in code_set:
                _add(_order_entry(prod["product"], order, "direct"))

    # ── Pass 2: BOM-component matches ──────────────────────────────────────
    # Collect unique product codes that appear on any order
    order_product_codes: set[str] = {
        p.get("product")
        for o in all_orders
        for p in o.get("products", [])
        if p.get("product")
    }

    # For each product on an order, fetch its BOM and check for affected parts
    bom_cache: dict[str, list] = {}
    for parent_code in order_product_codes:
        if parent_code in code_set:
            # Already handled as direct match
            continue
        bom = await client.get_bom(parent_code)
        bom_cache[parent_code] = bom
        # Product detail embeds BOM as components[].code (not "product-code")
        component_codes = {item.get("code") for item in bom}
        for code in product_codes:
            if code in component_codes:
                # Find orders for this parent
                for order in all_orders:
                    if any(p.get("product") == parent_code for p in order.get("products", [])):
                        _add(_order_entry(code, order, "bom_component", parent_code))

    at_risk.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["risk_level"]])
    return at_risk


def preview_cia_date_changes(
    at_risk_orders: list[dict],
    new_start_date: Optional[str] = None,
    new_due_date: Optional[str] = None,
) -> dict:
    """
    Build a human-readable preview of date changes for at-risk production orders.
    No API calls — purely formats the pending changes so they can be confirmed
    by the user before apply_cia_date_changes is called.

    Deduplicates by order_id so the same order only appears once even if it was
    matched by both 'direct' and 'bom_component'.
    """
    if not new_start_date and not new_due_date:
        return {"error": "Provide at least one of new_start_date or new_due_date."}

    seen_ids: set = set()
    orders_to_update = []
    for o in at_risk_orders:
        oid = o.get("order_id")
        if not oid or oid in seen_ids:
            continue
        seen_ids.add(oid)
        change: dict = {
            "order_id": oid,
            "order_code": o.get("order_code"),
            "risk_level": o.get("risk_level"),
            "current_due_date": o.get("due_date"),
        }
        if new_start_date:
            change["new_start_date"] = new_start_date
        if new_due_date:
            change["current_due_date"] = o.get("due_date")
            change["new_due_date"] = new_due_date
        orders_to_update.append(change)

    order_ids = [o["order_id"] for o in orders_to_update]

    return {
        "update_count": len(orders_to_update),
        "new_start_date": new_start_date,
        "new_due_date": new_due_date,
        "orders_to_update": orders_to_update,
        "order_ids": order_ids,
        "confirmation_required": (
            "Present this preview to the user and ask them to confirm "
            "before calling apply_cia_order_date_changes."
        ),
    }


async def apply_cia_date_changes(
    client: FusionOperationsClient,
    order_ids: list[str],
    new_start_date: Optional[str] = None,
    new_due_date: Optional[str] = None,
) -> dict:
    """
    Apply start/due date changes to the given production orders.
    Should only be called after the user has confirmed the preview
    returned by preview_cia_order_date_changes.
    """
    if not new_start_date and not new_due_date:
        return {"success": False, "error": "Provide at least one of new_start_date or new_due_date."}

    body: dict = {}
    if new_start_date:
        body["start-date"] = new_start_date
    if new_due_date:
        body["due-date"] = new_due_date

    results = []
    errors = []
    for oid in order_ids:
        try:
            updated = await client.update_production_order(str(oid), body)
            results.append({
                "order_id": oid,
                "success": True,
                "updated": updated,
            })
        except Exception as exc:
            errors.append({"order_id": oid, "success": False, "error": str(exc)})

    return {
        "updated_count": len(results),
        "error_count": len(errors),
        "new_start_date": new_start_date,
        "new_due_date": new_due_date,
        "results": results,
        "errors": errors,
    }
