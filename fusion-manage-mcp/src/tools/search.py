"""
Global search tool using the Fusion Manage v3 search-results endpoint.

Endpoint: GET /api/v3/search-results?query={text}&revision={1|2|3}&limit={n}

revision param:
  1 = latest revision only (default — use for BOM sync, part lookup)
  2 = all revisions
  3 = working/unreleased revisions only

Response preprocessing:
  - Extracts workspaceId and dmsId from __self__ (/api/v3/workspaces/{wsId}/items/{dmsId})
  - Adds workspace_label from workspaceLongName
  - Returns clean list ready for LLM reasoning or downstream tool calls
"""

import re
from ..client import FusionManageClient
from .. import workspaces as WS


_SELF_RE = re.compile(r"/api/v3/workspaces/(\d+)/items/(\d+)")


def _parse_self(self_url: str) -> tuple[int | None, int | None]:
    """Extract (workspace_id, dms_id) from a __self__ URL."""
    m = _SELF_RE.search(self_url or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _preprocess_results(raw: dict) -> dict:
    """
    Flatten the search response into a clean list of matches.
    Each result includes workspace_id, dms_id, descriptor, workspace_label,
    version, category, creator, and the raw __self__ URL.
    """
    items = raw.get("items", [])
    results = []
    for item in items:
        ws_id, dms_id = _parse_self(item.get("__self__", ""))
        results.append({
            "descriptor": item.get("descriptor"),
            "workspace_id": ws_id,
            "workspace_label": item.get("workspaceLongName"),
            "dms_id": dms_id,
            "version": item.get("version"),
            "category": item.get("category"),
            "creator": item.get("creator"),
            "owner": item.get("owner"),
            "self_url": item.get("__self__"),
        })
    return {
        "total_count": raw.get("totalCount", len(results)),
        "returned": len(results),
        "results": results,
    }


async def search(
    client: FusionManageClient,
    query: str,
    revision: int = 1,
    limit: int = 50,
    workspace_filter: int | None = None,
) -> dict:
    """
    Full-text search across all Fusion Manage workspaces.

    Args:
        query: Free-text search string (part number, description, etc.)
        revision: 1=latest (default), 2=all, 3=working/unreleased
        limit: Max results to return (default 50)
        workspace_filter: Optionally narrow to a specific workspace ID

    Returns preprocessed results with workspace_id and dms_id parsed from __self__.
    Use dms_id + workspace_id to call get_item_bom, get_item, etc.
    """
    raw = await client.search(query=query, revision=revision, limit=limit)
    processed = _preprocess_results(raw)

    if workspace_filter is not None:
        processed["results"] = [
            r for r in processed["results"]
            if r.get("workspace_id") == workspace_filter
        ]
        processed["returned"] = len(processed["results"])
        processed["workspace_filter"] = workspace_filter

    return processed


async def search_items(
    client: FusionManageClient,
    query: str,
    revision: int = 1,
    limit: int = 50,
) -> dict:
    """
    Search restricted to the Items workspace (WS 57 — Parts & Assemblies).
    Use this for BOM sync, part lookup, and change impact analysis.
    """
    return await search(
        client, query=query, revision=revision, limit=limit,
        workspace_filter=WS.ITEMS,
    )


async def search_change_orders(
    client: FusionManageClient,
    query: str,
    limit: int = 50,
) -> dict:
    """Search restricted to Change Orders workspace (WS 84)."""
    return await search(
        client, query=query, revision=1, limit=limit,
        workspace_filter=WS.CHANGE_ORDERS,
    )


async def search_non_conformances(
    client: FusionManageClient,
    query: str,
    limit: int = 50,
) -> dict:
    """Search restricted to Non Conformances workspace (WS 98)."""
    return await search(
        client, query=query, revision=1, limit=limit,
        workspace_filter=WS.NON_CONFORMANCES,
    )
