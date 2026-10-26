"""
Workspace tools.

Actual v1 API response shape for list_workspaces:
{
  "list": {
    "data": [
      { "data": {"id": 57, "category": "...", "label": "Items"}, "uri": "..." },
      ...
    ]
  }
}
"""

from ..client import FusionManageClient


def _normalize_workspaces(raw: dict) -> list[dict]:
    """Flatten the nested list.data[].data structure into a plain list."""
    entries = raw.get("list", {}).get("data", [])
    return [entry["data"] for entry in entries if "data" in entry]


# Key workspace IDs for this tenant (the reference tenant) — verified live
WORKSPACE_IDS = {
    "items": 57,           # Parts & Assemblies (Revision Controlled)
    "change_orders": 84,   # Change Orders / ECOs (Revisioning)
    "change_requests": 83, # Change Requests
    "non_conformances": 98,
    "capas": 100,          # Corrective / Preventative Actions
    "suppliers": 14,
    "products": 95,
    "documents": 71,
    "manufacturer_pn": 63,
}


async def list_workspaces(client: FusionManageClient) -> list:
    raw = await client.list_workspaces()
    return _normalize_workspaces(raw)


async def get_workspace_sections(client: FusionManageClient, ws_id: int) -> dict:
    return await client.get_workspace_sections(ws_id)
