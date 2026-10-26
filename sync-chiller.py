"""
BOM Sync: 9400-000 - Chiller-2-2000-400  (PLM DMS ID: 15466)

Flow:
  1. Fetch item + BOM from Fusion Manage PLM (WS57/ID15466)
  2. Create each BOM component as a product in Fusion Operations
     code = PLM DMS ID  (e.g. "15468" for 9400-001 Framework)
     name = full PLM description
  3. Create parent product (code="15466") with an 'assembly' operation
  4. POST /api/v1/bom to link all components to the parent

Run: uv run --project fusion-manage-mcp python sync-chiller.py
"""

import asyncio
import base64
import json
import os

import httpx
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
PLM_ENV = dotenv_values(os.path.join(HERE, "fusion-manage-mcp", ".env"))
OPS_ENV = dotenv_values(os.path.join(HERE, "fusion-operations-mcp", ".env"))

PLM_TENANT = PLM_ENV["FUSION_MANAGE_TENANT"]
PLM_TOKEN = PLM_ENV.get("FUSION_MANAGE_TOKEN", "")
OPS_API_KEY = OPS_ENV["FUSION_OPS_API_KEY"]
OPS_API_SECRET = OPS_ENV["FUSION_OPS_API_SECRET"]

PLM_V1_BASE = f"https://{PLM_TENANT}.autodeskplm360.net/api/rest/v1"
OPS_BASE = "https://fusionoperations.autodesk.com/api/v1"

PLM_WS_ID = 57
PLM_ITEM_ID = int(os.environ.get("PLM_ITEM_ID", "15466"))
ASSEMBLY_OP_CODE = "assembly"


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _extract_bom(item: dict) -> list[dict]:
    bom = []
    for entry in item.get("relations", {}).get("entry", []):
        if entry.get("key") == "REL_BOM":
            for child in entry.get("value", {}).get("item", []):
                bom.append({
                    "id": child.get("id"),
                    "description": child.get("description"),
                    "lifecycle_status": child.get("details", {}).get("lifecycleStatus"),
                })
    return bom


async def get_ops_token() -> str:
    creds = _b64(f"{OPS_API_KEY}:{OPS_API_SECRET}")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{OPS_BASE}/authorization",
                         json={"scopes": ["productions_write"]},
                         headers={"Authorization": f"Basic {creds}",
                                  "Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()["token"]


async def upsert_product(c, token, existing, code, name, observations):
    found = next((p for p in existing if p.get("code") == code), None)
    body = {"code": code, "name": name, "observations": observations}
    if found:
        r = await c.put(f"{OPS_BASE}/products/{code}",
                        params={"access_token": token}, json=body,
                        headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return "updated", r.json()
    else:
        r = await c.post(f"{OPS_BASE}/products/",
                         params={"access_token": token}, json=body,
                         headers={"Content-Type": "application/json"})
        if r.status_code == 400:
            # Already exists — recover via GET + PUT
            r2 = await c.get(f"{OPS_BASE}/products/{code}", params={"access_token": token})
            if r2.is_success:
                r3 = await c.put(f"{OPS_BASE}/products/{code}",
                                 params={"access_token": token}, json=body,
                                 headers={"Content-Type": "application/json"})
                r3.raise_for_status()
                return "updated(recovered)", r3.json()
        r.raise_for_status()
        return "created", r.json()


async def main():
    # ── Step 1: Fetch BOM from Fusion Manage ──────────────────────────────
    print(f"\n{'='*60}")
    print(f"STEP 1: Fetch BOM from Fusion Manage (WS{PLM_WS_ID}/ID{PLM_ITEM_ID})")
    print(f"{'='*60}")

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{PLM_V1_BASE}/workspaces/{PLM_WS_ID}/items/{PLM_ITEM_ID}",
            headers={"Authorization": f"Bearer {PLM_TOKEN}", "Accept": "application/json"},
        )
        r.raise_for_status()

    item = r.json().get("item", r.json())
    details = item.get("details", {})
    parent_desc = item.get("description", "")
    bom = _extract_bom(item)

    print(f"  {parent_desc}  (lifecycle={details.get('lifecycleStatus')})")
    print(f"  BOM components: {len(bom)}")
    for comp in bom:
        print(f"    DMS {comp['id']:6}  {comp['description']}")

    # ── Step 2: Auth + existing products ──────────────────────────────────
    print(f"\n{'='*60}")
    print(f"STEP 2: Authenticate with Fusion Operations")
    print(f"{'='*60}")

    ops_token = await get_ops_token()

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{OPS_BASE}/products/",
                        params={"access_token": ops_token, "page-size": 200})
        r.raise_for_status()
        existing = r.json()

    print(f"  Token OK  |  Existing products: {len(existing)}")

    # ── Step 3: Sync all component products ───────────────────────────────
    print(f"\n{'='*60}")
    print(f"STEP 3: Sync {len(bom)} component products  (code = PLM DMS ID)")
    print(f"{'='*60}")

    component_codes = []
    async with httpx.AsyncClient(timeout=30) as c:
        for comp in bom:
            code = str(comp["id"])
            name = comp["description"]
            obs = (
                f"PLM DMS ID: {comp['id']} | WS: {PLM_WS_ID} | "
                f"Lifecycle: {comp['lifecycle_status']} | "
                f"BOM component of DMS ID {PLM_ITEM_ID}"
            )
            action, product = await upsert_product(c, ops_token, existing, code, name, obs)
            if action == "created":
                existing.append(product)
            component_codes.append(code)
            marker = "NEW" if action == "created" else " - "
            print(f"  [{marker}] code={code:6}  {name:40}  ops_id={product.get('id')}")

    # ── Step 4: Sync parent product with assembly operation ────────────────
    print(f"\n{'='*60}")
    print(f"STEP 4: Sync parent product (code={PLM_ITEM_ID})")
    print(f"{'='*60}")

    parent_code = str(PLM_ITEM_ID)
    parent_obs = (
        f"PLM DMS ID: {PLM_ITEM_ID} | WS: {PLM_WS_ID} | "
        f"Assembly with {len(bom)} BOM components | "
        f"Lifecycle: {details.get('lifecycleStatus')}"
    )

    # Parent product: always include the assembly operation in the same PUT
    # so idempotent re-runs don't lose it (PUT with missing ops → 400).
    parent_body = {
        "code": parent_code,
        "name": parent_desc,
        "observations": parent_obs,
        "operations": [{"code": ASSEMBLY_OP_CODE, "name": "Assembly"}],
    }

    async with httpx.AsyncClient(timeout=30) as c:
        found = next((p for p in existing if p.get("code") == parent_code), None)
        if found:
            r = await c.put(f"{OPS_BASE}/products/{parent_code}",
                            params={"access_token": ops_token}, json=parent_body,
                            headers={"Content-Type": "application/json"})
            r.raise_for_status()
            parent_action, parent_product = "updated", r.json()
        else:
            r = await c.post(f"{OPS_BASE}/products/",
                             params={"access_token": ops_token}, json=parent_body,
                             headers={"Content-Type": "application/json"})
            if r.status_code == 400:
                r2 = await c.put(f"{OPS_BASE}/products/{parent_code}",
                                 params={"access_token": ops_token}, json=parent_body,
                                 headers={"Content-Type": "application/json"})
                r2.raise_for_status()
                parent_action, parent_product = "updated(recovered)", r2.json()
            else:
                r.raise_for_status()
                parent_action, parent_product = "created", r.json()

        ops_in_response = parent_product.get("operations", [])
        print(f"  {parent_action.upper()}: code={parent_code}, ops_id={parent_product.get('id')}")
        print(f"  Operations: {[o.get('code') for o in ops_in_response]}")

    # ── Step 5: POST /api/v1/bom ───────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"STEP 5: POST /api/v1/bom  (link {len(bom)} components to parent)")
    print(f"{'='*60}")

    bom_payload = {
        "product-code": parent_code,
        "bom": [
            {
                "product-code": str(comp["id"]),
                "quantity": 1,
                "operation-code": ASSEMBLY_OP_CODE,
            }
            for comp in bom
        ],
    }

    print(f"  Payload: product-code={parent_code!r}, {len(bom_payload['bom'])} components")

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{OPS_BASE}/bom",
            params={"access_token": ops_token},
            json=bom_payload,
            headers={"Content-Type": "application/json"},
        )
        print(f"  Status: {r.status_code}")
        if r.is_success:
            result = r.json()
            print(f"  BOM response:")
            print(json.dumps(result, indent=4))
        else:
            print(f"  ERROR: {r.text[:500]}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    created = sum(1 for c in component_codes if not any(
        p.get("code") == c for p in existing[:len(existing) - len(component_codes)]
    ))
    print(f"DONE")
    print(f"  Parent product: code={parent_code} ({parent_desc})")
    print(f"  Components:     {len(bom)} synced as products in Fusion Operations")
    print(f"  BOM:            status={r.status_code}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
