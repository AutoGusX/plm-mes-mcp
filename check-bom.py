"""
Final BOM endpoint attempts:
1. PATCH /products/{code}
2. POST /products/{code}/components (various bodies)
3. Check what the web UI sends by inspecting an existing product with BOM
"""
import asyncio, base64, json, os, httpx
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
OPS_ENV = dotenv_values(os.path.join(HERE, "fusion-operations-mcp", ".env"))
OPS_BASE = "https://fusionoperations.autodesk.com/api/v1"

async def get_token():
    creds = base64.b64encode(f"{OPS_ENV['FUSION_OPS_API_KEY']}:{OPS_ENV['FUSION_OPS_API_SECRET']}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{OPS_BASE}/authorization", json={"scopes": ["productions_write"]},
                         headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()["token"]

async def main():
    t = await get_token()

    async with httpx.AsyncClient(timeout=30) as c:

        # PATCH with components
        print("PATCH /products/9400-000 with components:")
        r = await c.patch(f"{OPS_BASE}/products/9400-000",
                          params={"access_token": t},
                          json={"components": [{"product": {"code": "9400-001"}, "quantity": 1}]},
                          headers={"Content-Type": "application/json"})
        print(f"  status: {r.status_code}")
        if r.is_success:
            print(f"  components: {r.json().get('components')}")
        else:
            print(f"  {r.text[:100]}")

        # GET after PATCH
        r = await c.get(f"{OPS_BASE}/products/9400-000", params={"access_token": t})
        print(f"  GET components: {r.json().get('components')}\n")

        # Look at the FULL raw response for product with operations (0000001)
        # to see if there's a "materials" or component-like field with real data
        print("Full 0000001 product structure (all non-empty fields):")
        r = await c.get(f"{OPS_BASE}/products/0000001", params={"access_token": t})
        p = r.json()
        for k, v in p.items():
            if v not in (None, [], {}, False, 0, 0.0, ""):
                print(f"  {k}: {json.dumps(v)[:150]}")

        # If operations exist, dump first operation fully
        ops = p.get("operations", [])
        if ops:
            print(f"\nFirst operation full structure:")
            print(json.dumps(ops[0], indent=2)[:2000])

asyncio.run(main())
