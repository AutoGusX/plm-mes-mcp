"""
Cross-system tools for PLM ↔ MES orchestration.

These tools support the 5 use cases in use-cases.md by providing
targeted PLM queries that AI agents combine with MES data from
the fusion-operations-mcp server.
"""

from typing import Optional
from ..client import FusionManageClient
from .items import _normalize_item_list, _normalize_item, _extract_bom


async def get_released_parts(
    client: FusionManageClient,
    ws_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    Get items in approved-for-production lifecycle states from a workspace.

    In this tenant (the reference tenant), observed lifecycleStatus values include
    "Production" (effectivity=true items). Filters the item list client-side
    since the search endpoint uses fieldIDs not lifecycleStatus directly.
    """
    raw = await client.list_workspace_items(ws_id, page=page, size=page_size)
    all_items = _normalize_item_list(raw)
    released_statuses = {"Released", "Production", "Approved"}
    released = [
        {
            "id": it["id"],
            "description": it["description"],
            "lifecycle_status": it.get("details", {}).get("lifecycleStatus"),
            "release": it.get("details", {}).get("release"),
        }
        for it in all_items
        if it.get("details", {}).get("lifecycleStatus") in released_statuses
    ]
    return {"workspace_id": ws_id, "count": len(released), "items": released}


async def get_items_changed_since(
    client: FusionManageClient,
    ws_id: int,
    since_date: str,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    Find items modified on or after a given date.
    Used for correlating engineering changes with production defects.

    Args:
        since_date: ISO 8601 date string (e.g. '2024-11-11T00:00:00Z')
    """
    search_def = {
        "pageNo": page,
        "pageSize": page_size,
        "logicClause": "AND",
        "fields": [{"fieldID": "MODIFIED_DATE"}],
        "sorting": [{"fieldID": "MODIFIED_DATE", "sortOrder": "DESC"}],
        "filteringCriteria": [
            {
                "filterType": {"filterID": "GREATER_THAN_OR_EQUAL"},
                "filterValue": since_date,
            }
        ],
    }
    return await client.search_workspace_items(ws_id, search_def)


async def get_item_by_number(
    client: FusionManageClient,
    ws_id: int,
    item_number: str,
) -> dict:
    """
    Find a specific item by its item/part number field.
    Used as the entry point for Change Impact Analysis (given an ECO or part number).
    """
    search_def = {
        "pageNo": 1,
        "pageSize": 5,
        "logicClause": "AND",
        "fields": [{"fieldID": "ITEM_NUMBER"}],
        "sorting": [{"fieldID": "TITLE", "sortOrder": "ASC"}],
        "filteringCriteria": [
            {"filterType": {"filterID": "EQUALS"}, "filterValue": item_number}
        ],
    }
    return await client.search_workspace_items(ws_id, search_def)


async def get_eco_details(
    client: FusionManageClient,
    eco_ws_id: int,
    eco_id: int,
) -> dict:
    """
    Get full details of an Engineering Change Order including affected items,
    workflow history, and attachments. Entry point for Change Impact Analysis.

    Returns structured 'affected_items' list — each item has:
      dms_id, workspace_id, title, target_transition, from_release, to_release,
      effectivity_date, ops_product_code (= dms_id, ready for Fusion Operations lookup)

    Verified endpoints (the reference tenant):
      v3 item detail:      GET /api/v3/workspaces/{ws}/items/{id}
      v3 managed items:    GET /api/v3/workspaces/{ws}/items/{id}/views/11
        → affectedItems[].item.link contains /workspaces/{ws}/items/{dms_id}
    """
    # v3 gives us title + currentState; v1 gives workflow history
    v3_item = await client.get_workspace_item_v3(eco_ws_id, eco_id)
    managed = await client.get_co_affected_items(eco_ws_id, eco_id)  # views/11
    history = await client.get_workflow_history(eco_ws_id, eco_id)
    attachments = await client.list_item_attachments(eco_ws_id, eco_id)

    # Parse affected items from the CO Affected Items view (views/11)
    affected_items = []
    for ai in managed.get("affectedItems", []):
        item_link = ai.get("item", {}).get("link", "")
        # Extract DMS ID and workspace from: /api/v3/workspaces/57/items/15478
        parts = item_link.split("/")
        try:
            ws_idx = parts.index("workspaces")
            item_ws_id = int(parts[ws_idx + 1])
            item_dms_id = int(parts[parts.index("items", ws_idx) + 1])
        except (ValueError, IndexError):
            item_ws_id = None
            item_dms_id = None

        affected_items.append({
            "dms_id": item_dms_id,
            "workspace_id": item_ws_id,
            "title": ai.get("item", {}).get("title"),
            "target_transition": ai.get("targetTransition", {}).get("title"),
            "from_release": ai.get("fromRelease", ""),
            "to_release": ai.get("toRelease", ""),
            "effectivity_date": ai.get("effectivityDate"),
            # ready for find_orders_by_product_code in fusion-operations-mcp
            "ops_product_code": str(item_dms_id) if item_dms_id else None,
        })

    return {
        "co_id": eco_id,
        "co_ws_id": eco_ws_id,
        "title": v3_item.get("title") or v3_item.get("description"),
        "current_state": v3_item.get("currentState", {}).get("title"),
        "affected_items": affected_items,
        "affected_item_count": len(affected_items),
        "workflow_history": history,
        "attachments": attachments,
    }


async def get_bom_for_item(
    client: FusionManageClient,
    ws_id: int,
    item_id: int,
) -> dict:
    """
    Get an item with its full BOM extracted from REL_BOM relationships.

    BOM is embedded in the item detail response under:
      relations.entry[key="REL_BOM"].value.item[]

    Returns normalized item info plus a flat bom_components list ready
    for use with sync_product_from_plm in fusion-operations-mcp.
    """
    raw = await client.get_workspace_item(ws_id, item_id)
    item = _normalize_item(raw)
    bom = _extract_bom(item)
    details = item.get("details", {})

    return {
        "id": item.get("id"),
        "description": item.get("description"),
        "lifecycle_status": details.get("lifecycleStatus"),
        "release": details.get("release"),
        "bom_components": bom,
        "bom_count": len(bom),
        "sync_ready": details.get("lifecycleStatus") in ("Released", "Production", "Approved"),
    }


async def find_items_by_part_numbers(
    client: FusionManageClient,
    ws_id: int,
    part_numbers: list[str],
) -> list[dict]:
    """
    Batch lookup multiple parts by item number.
    Used in Change Impact Analysis to resolve BOM components to PLM items.
    """
    results = []
    for pn in part_numbers:
        result = await get_item_by_number(client, ws_id, pn)
        results.append({"part_number": pn, "result": result})
    return results


async def get_item_sourcing(
    client: FusionManageClient,
    ws_id: int,
    item_id: int,
) -> dict:
    """
    Fetch the full Approved Manufacturer/Supplier List (AML) for an item,
    including all quotes with lead time data.

    Calls:
      GET /api/v3/workspaces/{ws}/items/{id}/views/8/suppliers
      GET /api/v3/workspaces/{ws}/items/{id}/views/8/suppliers/{sid}/quotes  (per supplier)

    Returns structured sourcing info:
      suppliers[]:
        supplier_id, supplier_name, supplier_part_number,
        manufacturer, manufacturer_part_number,
        quotes[]: { lead_time_days, unit_price, min_qty, max_qty,
                    is_default, bom_assemblies[] }
      min_lead_time_days:  shortest lead time across all quotes
      default_lead_time_days: lead time from the default quote (if any)
      has_quotes: bool
    """
    raw = await client.get_item_suppliers(ws_id, item_id)

    suppliers_out = []
    all_lead_times = []
    default_lead_time = None

    for s in raw.get("suppliers", []):
        # Extract supplier ID from __self__: .../suppliers/695
        self_link = s.get("__self__", "")
        try:
            supplier_id = int(self_link.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            continue

        quotes_raw = await client.get_item_supplier_quotes(ws_id, item_id, supplier_id)

        quotes_out = []
        for q in (quotes_raw if isinstance(quotes_raw, list) else []):
            lt       = q.get("leadTime") or 0
            lt_mult  = q.get("leadTimeMultiplier") or 1
            lt_days  = lt * lt_mult
            is_default = q.get("defaultQuote", False)

            bom_assemblies = [
                {
                    "dms_id": int(a.get("link", "").split("/")[-1]),
                    "title":  a.get("title"),
                }
                for a in q.get("bomAssemblies", [])
                if a.get("link")
            ]

            quote = {
                "lead_time_days":      lt_days,
                "unit_price":          q.get("unitPrice"),
                "min_qty":             q.get("minAmount"),
                "max_qty":             q.get("maxAmount"),
                "is_default":          is_default,
                "bom_assemblies":      bom_assemblies,
            }
            quotes_out.append(quote)

            if lt_days > 0:
                all_lead_times.append(lt_days)
            if is_default and lt_days > 0:
                default_lead_time = lt_days

        suppliers_out.append({
            "supplier_id":              supplier_id,
            "supplier_name":            s.get("supplier", {}).get("title"),
            "supplier_part_number":     s.get("supplierPartNumber"),
            "manufacturer":             s.get("manufacturer"),
            "manufacturer_part_number": s.get("manufacturerPartNumber"),
            "quotes":                   quotes_out,
        })

    return {
        "ws_id":                  ws_id,
        "item_id":                item_id,
        "has_quotes":             raw.get("hasQuotes", False),
        "has_default_quote":      raw.get("hasDefaultQuote", False),
        "suppliers":              suppliers_out,
        "supplier_count":         len(suppliers_out),
        "min_lead_time_days":     min(all_lead_times) if all_lead_times else None,
        "default_lead_time_days": default_lead_time,
    }


async def get_item_change_orders(
    client: FusionManageClient,
    ws_id: int,
    item_id: int,
) -> dict:
    """
    Get Change Orders that list a given item as an affected item (views/2).

    Used in quality Root Cause Analysis: given a part that produced waste,
    find which COs have been made against it.

    Args:
        ws_id:   Workspace ID of the part (e.g. 57 for Items)
        item_id: DMS ID of the part
    """
    raw = await client.get_item_managed_items(ws_id, item_id)

    change_orders = []
    for entry in (raw if isinstance(raw, list) else []):
        item_ref = entry.get("item", {})
        link = item_ref.get("link", "")
        parts = link.split("/")
        try:
            ws_idx = parts.index("workspaces")
            co_ws_id = int(parts[ws_idx + 1])
            co_id = int(parts[parts.index("items", ws_idx) + 1])
        except (ValueError, IndexError):
            co_ws_id = None
            co_id = None

        wf_state = entry.get("workflow-state", {})
        last_hist = entry.get("last-workflow-history", {})
        change_orders.append({
            "co_id": co_id,
            "co_ws_id": co_ws_id,
            "title": item_ref.get("title"),
            "current_state": wf_state.get("title") or item_ref.get("currentState"),
            "last_transition": last_hist.get("workflowTransition", {}).get("title"),
            "last_transition_date": last_hist.get("created"),
        })

    return {
        "item_id": item_id,
        "ws_id": ws_id,
        "change_order_count": len(change_orders),
        "change_orders": change_orders,
    }


async def get_approved_suppliers_for_item(
    client: FusionManageClient,
    ws_id: int,
    item_id: int,
) -> dict:
    """
    Get the approved supplier list for an item (from item relationships/fields).
    Used in Supplier Exception Handling to find approved alternates.
    """
    item = await client.get_workspace_item(ws_id, item_id)
    return {
        "item_id": item_id,
        "item": item,
        "usage_note": (
            "Approved suppliers are typically stored in a related workspace "
            "(e.g. 'Approved Supplier List') or as a multi-select field on the item. "
            "Check item.sections for fields named 'APPROVED_SUPPLIERS' or similar."
        ),
    }
