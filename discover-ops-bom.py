"""
Discovery script: find the correct Fusion Operations BOM endpoint/format.

1. Lists all products
2. Gets full detail of any product that appears to have a BOM
3. Tests the BOM POST with correct {component: {code}} format

Run: uv run --project fusion-manage-mcp python discover-ops-bom.py
"""

import asyncio
import base64
import json
import os
import httpx
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
OPS_ENV = dotenv_values(os.path.join(HERE, "fusion-operations-mcp", ".env"))
OPS_API_KEY = OPS_ENV["FUSION_OPS_API_KEY"]
OPS_API_SECRET = OPS_ENV["FUSION_OPS_API_SECRET"]
OPS_BASE = "https://fusionoperations.autodesk.com/api/v1"


async def get_token() -> str:
    creds = base64.b64encode(f"{OPS_API_KEY}:{OPS_API_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{OPS_BASE}/authorization",
            json={"scopes": ["productions_write"]},
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["token"]


async def get(token: str, path: str, **params) -> any:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{OPS_BASE}{path}", params={"access_token": token, **params})
        r.raise_for_status()
        return r.json()


async def put(token: str, path: str, body: dict) -> any:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(
            f"{OPS_BASE}{path}",
            params={"access_token": token},
            json=body,
            headers={"Content-Type": "application/json"},
        )
        print(f"  PUT {path} -> {r.status_code}")
        if r.is_success:
            return r.json()
        else:
            return {"error": r.status_code, "body": r.text[:300]}


async def post(token: str, path: str, body: dict) -> any:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{OPS_BASE}{path}",
            params={"access_token": token},
            json=body,
            headers={"Content-Type": "application/json"},
        )
        print(f"  POST {path} -> {r.status_code}")
        if r.is_success:
            return r.json()
        else:
            return {"error": r.status_code, "body": r.text[:500]}


async def main():
    token = await get_token()
    print(f"Token: {token[:20]}...\n")

    # ── 1. List all products ────────────────────────────────────────────────
    print("=" * 60)
    print("All products (page-size=100):")
    print("=" * 60)
    products = await get(token, "/products/", **{"page-size": 100})
    print(f"Type: {type(products).__name__}")

    # Handle both list and dict responses
    product_list = products if isinstance(products, list) else products.get("results", [])
    print(f"Count: {len(product_list)}")
    for p in product_list:
        print(f"  code={p.get('code')!r:25}  name={p.get('name') or p.get('description') or ''!r:30}  keys={sorted(p.keys())}")

    # ── 2. Get full detail of first product ────────────────────────────────
    if product_list:
        first = product_list[0]
        code = first.get("code")
        print(f"\n{'='*60}")
        print(f"Full detail for product: {code!r}")
        print(f"{'='*60}")
        try:
            detail = await get(token, f"/products/{code}")
            print(json.dumps(detail, indent=2))
        except Exception as e:
            print(f"  GET /products/{code} failed: {e}")

        # Try GET with trailing slash
        try:
            detail2 = await get(token, f"/products/{code}/")
            print("\nWith trailing slash:")
            print(json.dumps(detail2, indent=2))
        except Exception as e:
            print(f"  GET /products/{code}/ failed: {e}")

    # ── 3. Test BOM endpoint format on 9400-000 ────────────────────────────
    print(f"\n{'='*60}")
    print("Testing BOM endpoint on 9400-000")
    print(f"{'='*60}")

    # Try format from api-reference: component as {code: str}
    print("\nAttempt 1: component as {code: '9400-001'}")
    r1 = await post(token, "/products/9400-000/bom", {
        "bom_items": [{"component": {"code": "9400-001"}, "quantity": 1}]
    })
    print(f"  Result: {json.dumps(r1, indent=2)}")

    # Try with trailing slash
    print("\nAttempt 2: /products/9400-000/bom/ (trailing slash)")
    r2 = await post(token, "/products/9400-000/bom/", {
        "bom_items": [{"component": {"code": "9400-001"}, "quantity": 1}]
    })
    print(f"  Result: {json.dumps(r2, indent=2)}")

    # Try component as string
    print("\nAttempt 3: component as plain string")
    r3 = await post(token, "/products/9400-000/bom", {
        "bom_items": [{"component": "9400-001", "quantity": 1}]
    })
    print(f"  Result: {json.dumps(r3, indent=2)}")

    # Try PUT on product with components field embedded
    print("\nAttempt 4: PUT /products/9400-000 with components: [{product: code, quantity}]")
    r4 = await put(token, "/products/9400-000", {
        "code": "9400-000",
        "name": "Chiller-2-2000-400",
        "components": [{"product": "9400-001", "quantity": 1}],
    })
    print(f"  Result: {json.dumps(r4, indent=2)}")

    # Try PUT with components as [{code, quantity}]
    print("\nAttempt 5: PUT /products/9400-000 with components: [{code, quantity}]")
    r5 = await put(token, "/products/9400-000", {
        "code": "9400-000",
        "name": "Chiller-2-2000-400",
        "components": [{"code": "9400-001", "quantity": 1}],
    })
    print(f"  Result: {json.dumps(r5, indent=2)}")

    # Check if 9400-001 product exists yet (created as component earlier)
    print("\nChecking existing product components on 0000001:")
    try:
        existing = await get(token, "/products/0000001")
        comps = existing.get("components", [])
        print(f"  components field: {json.dumps(comps, indent=2)}")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
