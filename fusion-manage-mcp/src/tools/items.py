"""
Item tools — field names verified against live Fusion Manage v1 API (the reference tenant).

Actual list response shape:
  {"list": {"item": [{uri, id, description, details: {...}}, ...]}}

Actual detail response shape:
  {"item": {uri, id, description, details: {descriptor, workspaceID, deleted, version,
   release, timeStamp, createdByUser, owner, lifecycleState, lifecycleStatus,
   latest, working, status, dmsID}, relations: {entry: [{key, value}]}, metaFields}}

BOM is in: relations.entry where key == "REL_BOM", value.item[] = child parts.
lifecycleStatus values observed: "Production", "Released", etc.
"""

from typing import Optional
from ..client import FusionManageClient


def _normalize_item_list(raw: dict) -> list[dict]:
    return raw.get("list", {}).get("item", [])


def _normalize_item(raw: dict) -> dict:
    return raw.get("item", raw)


def _extract_bom(item: dict) -> list[dict]:
    """Extract BOM components from item relations."""
    bom = []
    for entry in item.get("relations", {}).get("entry", []):
        if entry.get("key") == "REL_BOM":
            for child in entry.get("value", {}).get("item", []):
                bom.append({
                    "id": child.get("id"),
                    "description": child.get("description"),
                    "lifecycle_status": child.get("details", {}).get("lifecycleStatus"),
                    "release": child.get("details", {}).get("release"),
                    "workspace_id": child.get("details", {}).get("workspaceID"),
                })
    return bom


async def list_items(
    client: FusionManageClient, ws_id: int, page: int, page_size: int
) -> dict:
    raw = await client.list_workspace_items(ws_id, page=page, size=page_size)
    items = _normalize_item_list(raw)
    return {
        "workspace_id": ws_id,
        "count": len(items),
        "items": [
            {
                "id": it["id"],
                "description": it["description"],
                "lifecycle_status": it.get("details", {}).get("lifecycleStatus"),
                "release": it.get("details", {}).get("release"),
                "timestamp": it.get("details", {}).get("timeStamp"),
            }
            for it in items
        ],
    }


async def get_item(client: FusionManageClient, ws_id: int, item_id: int) -> dict:
    raw = await client.get_workspace_item(ws_id, item_id)
    item = _normalize_item(raw)
    bom = _extract_bom(item)
    return {
        "id": item.get("id"),
        "description": item.get("description"),
        "details": item.get("details", {}),
        "bom": bom,
        "bom_count": len(bom),
        "meta_fields": item.get("metaFields", {}),
    }


async def search_items(
    client: FusionManageClient,
    ws_id: int,
    search_text: str,
    field_filters: list,
    page: int,
    page_size: int,
    sort_field: str,
    sort_order: str,
) -> dict:
    filtering_criteria = []
    if search_text:
        filtering_criteria.append(
            {"filterType": {"filterID": "CONTAINS"}, "filterValue": search_text}
        )

    search_def = {
        "pageNo": page,
        "pageSize": page_size,
        "logicClause": "AND",
        "fields": [{"fieldID": f.get("fieldID", "TITLE")} for f in field_filters] or [{"fieldID": "TITLE"}],
        "sorting": [{"fieldID": sort_field, "sortOrder": sort_order}],
        "filteringCriteria": filtering_criteria,
    }
    return await client.search_workspace_items(ws_id, search_def)


async def create_item(
    client: FusionManageClient, ws_id: int, fields: list[dict]
) -> dict:
    # v1 create format — fields as a flat dict
    body = {f["fieldId"]: f["value"] for f in fields}
    return await client.create_workspace_item(ws_id, body)


async def update_item(
    client: FusionManageClient, ws_id: int, item_id: int, fields: list[dict]
) -> dict:
    body = {f["fieldId"]: f["value"] for f in fields}
    return await client.update_workspace_item(ws_id, item_id, body)


async def list_attachments(
    client: FusionManageClient, ws_id: int, dms_id: int
) -> list:
    return await client.list_item_attachments(ws_id, dms_id)
