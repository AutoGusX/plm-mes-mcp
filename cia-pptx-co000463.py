"""
Generate Change Impact Analysis PPTX for CO-000463 - Update ID.
Runs the full CIA (PLM + Fusion Operations) then calls the reporting module.
"""
import asyncio, base64, os, sys, httpx
from datetime import datetime, timezone
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
PLM_ENV = dotenv_values(os.path.join(HERE, "fusion-manage-mcp", ".env"))
OPS_ENV = dotenv_values(os.path.join(HERE, "fusion-operations-mcp", ".env"))

PLM_TENANT = PLM_ENV["FUSION_MANAGE_TENANT"]
PLM_TOKEN  = PLM_ENV.get("FUSION_MANAGE_TOKEN", "")
V1  = f"https://{PLM_TENANT}.autodeskplm360.net/api/rest/v1"
V3  = f"https://{PLM_TENANT}.autodeskplm360.net/api/v3"
PLM_HDR = {"Authorization": f"Bearer {PLM_TOKEN}", "Accept": "application/json"}

OPS_BASE = "https://fusionoperations.autodesk.com/api/v1"
OPS_KEY  = OPS_ENV["FUSION_OPS_API_KEY"]
OPS_SEC  = OPS_ENV["FUSION_OPS_API_SECRET"]

CO_WS = 84
CO_ID = 19360
TODAY = datetime.now(timezone.utc)


def days_until(date_str):
    if not date_str:
        return None
    try:
        due = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (due - TODAY).days
    except Exception:
        return None


def classify_risk(order):
    if order.get("is-active"):
        return "HIGH"
    if order.get("running-status", "") != "closed":
        return "MEDIUM"
    return "LOW"


async def get_ops_token():
    creds = base64.b64encode(f"{OPS_KEY}:{OPS_SEC}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{OPS_BASE}/authorization",
            json={"scopes": ["productions_write"]},
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["token"]


async def fetch_sourcing(ws_id, item_id):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{V3}/workspaces/{ws_id}/items/{item_id}/views/8/suppliers",
            headers=PLM_HDR,
        )
    if not r.is_success:
        return {"suppliers": [], "min_lead_time_days": None,
                "default_lead_time_days": None, "has_quotes": False}

    raw = r.json()
    suppliers_out, all_lead_times, default_lead_time = [], [], None

    for s in raw.get("suppliers", []):
        self_link = s.get("__self__", "")
        try:
            supplier_id = int(self_link.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            continue
        async with httpx.AsyncClient(timeout=30) as c:
            rq = await c.get(
                f"{V3}/workspaces/{ws_id}/items/{item_id}/views/8/suppliers/{supplier_id}/quotes",
                headers=PLM_HDR,
            )
        quotes_raw = rq.json() if rq.is_success and rq.text.strip() else []
        if isinstance(quotes_raw, dict):
            quotes_raw = []

        quotes_out = []
        for q in quotes_raw:
            lt_days = (q.get("leadTime") or 0) * (q.get("leadTimeMultiplier") or 1)
            is_def  = q.get("defaultQuote", False)
            bom_assemblies = [
                {"dms_id": int(a["link"].split("/")[-1]), "title": a.get("title")}
                for a in q.get("bomAssemblies", []) if a.get("link")
            ]
            quotes_out.append({
                "lead_time_days": lt_days, "unit_price": q.get("unitPrice"),
                "min_qty": q.get("minAmount"), "max_qty": q.get("maxAmount"),
                "is_default": is_def, "bom_assemblies": bom_assemblies,
            })
            if lt_days > 0:
                all_lead_times.append(lt_days)
            if is_def and lt_days > 0:
                default_lead_time = lt_days

        suppliers_out.append({
            "supplier_id": supplier_id,
            "supplier_name": s.get("supplier", {}).get("title"),
            "supplier_part_number": s.get("supplierPartNumber"),
            "manufacturer": s.get("manufacturer"),
            "manufacturer_part_number": s.get("manufacturerPartNumber"),
            "quotes": quotes_out,
        })

    return {
        "suppliers": suppliers_out,
        "min_lead_time_days": min(all_lead_times) if all_lead_times else None,
        "default_lead_time_days": default_lead_time,
        "has_quotes": raw.get("hasQuotes", False),
        "has_default_quote": raw.get("hasDefaultQuote", False),
    }


async def main():
    print("Collecting data for CIA PPTX...")

    # CO details
    async with httpx.AsyncClient(timeout=30) as c:
        r_co = await c.get(f"{V3}/workspaces/{CO_WS}/items/{CO_ID}", headers=PLM_HDR)
        r_mi = await c.get(f"{V3}/workspaces/{CO_WS}/items/{CO_ID}/views/11", headers=PLM_HDR)
    r_co.raise_for_status(); r_mi.raise_for_status()

    co_raw = r_co.json()
    co = {
        "title":         co_raw.get("title"),
        "current_state": co_raw.get("currentState", {}).get("title"),
        "co_id":         CO_ID,
        "ws_id":         CO_WS,
    }

    # Affected items
    affected = []
    for ai in r_mi.json().get("affectedItems", []):
        link  = ai.get("item", {}).get("link", "")
        parts = link.split("/")
        try:
            wi     = parts.index("workspaces")
            dms_id = int(parts[parts.index("items", wi) + 1])
            ws_id  = int(parts[wi + 1])
        except (ValueError, IndexError):
            continue

        async with httpx.AsyncClient(timeout=30) as c:
            r_item = await c.get(f"{V1}/workspaces/{ws_id}/items/{dms_id}", headers=PLM_HDR)
        item    = r_item.json().get("item", r_item.json())
        details = item.get("details", {})
        meta    = {e["key"]: e.get("fieldData", {}).get("value", "")
                   for e in item.get("metaFields", {}).get("entry", [])}

        where_used = []
        for rel in item.get("relations", {}).get("entry", []):
            if rel.get("key") == "REL_INV_BOM" and rel.get("value"):
                for parent in rel["value"].get("item", []):
                    where_used.append({
                        "dms_id":    parent.get("id"),
                        "title":     parent.get("description"),
                        "lifecycle": parent.get("details", {}).get("lifecycleStatus"),
                        "release":   parent.get("details", {}).get("release"),
                        "ops_code":  str(parent.get("id")),
                    })

        sourcing = await fetch_sourcing(ws_id, dms_id)

        affected.append({
            "dms_id":        dms_id, "ws_id": ws_id,
            "title":         ai.get("item", {}).get("title"),
            "transition":    ai.get("targetTransition", {}).get("title"),
            "from_rel":      ai.get("fromRelease", ""),
            "to_rel":        ai.get("toRelease", ""),
            "effectivity":   ai.get("effectivityDate"),
            "ops_code":      str(dms_id),
            "plm_lifecycle": details.get("lifecycleStatus"),
            "pdm_status":    meta.get("PDM_STATUS_NAME", ""),
            "pdm_revision":  meta.get("PDM_REVISION", ""),
            "procurement":   meta.get("PDM_CATEGORY", "Unknown"),
            "material":      meta.get("MATERIAL", ""),
            "dimensions":    meta.get("PDM_SIZE") or meta.get("DIMENSIONS", ""),
            "mass_kg":       meta.get("PDM_MASS", ""),
            "where_used":    where_used,
            "sourcing":      sourcing,
        })

    # Production orders
    token = await get_ops_token()
    async with httpx.AsyncClient(timeout=30) as c:
        r_orders = await c.get(
            f"{OPS_BASE}/production-orders/",
            params={"access_token": token, "page-size": 200},
        )
        r_orders.raise_for_status()
    all_orders = r_orders.json()
    if isinstance(all_orders, dict):
        all_orders = all_orders.get("results", [])

    affected_codes   = {ai["ops_code"] for ai in affected}
    where_used_codes = {wu["ops_code"] for ai in affected for wu in ai.get("where_used", [])}
    order_product_codes = {
        p.get("product")
        for o in all_orders for p in o.get("products", []) if p.get("product")
    } - affected_codes - where_used_codes

    bom_map: dict = {}
    async with httpx.AsyncClient(timeout=30) as c:
        for pc in order_product_codes | where_used_codes:
            r_p = await c.get(f"{OPS_BASE}/products/{pc}", params={"access_token": token})
            if r_p.is_success:
                bom_map[pc] = [comp.get("code") for comp in (r_p.json().get("components") or [])]

    seen: set = set()
    at_risk = []

    def add_hit(match_type, code, parent, order):
        key = (code, order.get("id"), match_type)
        if key in seen:
            return
        seen.add(key)
        lc     = parent if parent else code
        prod_e = next((p for p in order.get("products", []) if p.get("product") == lc), {})
        ordered  = prod_e.get("quantity-ordered", 0) or 0
        produced = prod_e.get("quantity-produced", 0) or 0
        due_str  = order.get("due-date")
        at_risk.append({
            "match_type":    match_type, "part": code, "parent": parent,
            "order_code":    order.get("code"), "order_id": order.get("id"),
            "status":        order.get("running-status"),
            "active":        order.get("is-active"),
            "qty_ordered":   ordered, "qty_produced": produced,
            "pct":           round(produced / ordered * 100, 1) if ordered else 0,
            "due":           due_str, "days_until_due": days_until(due_str),
            "risk":          classify_risk(order),
        })

    for code in affected_codes:
        for o in all_orders:
            if any(p.get("product") == code for p in o.get("products", [])):
                add_hit("direct", code, None, o)
        for parent_code, comp_codes in bom_map.items():
            if code in comp_codes:
                for o in all_orders:
                    if any(p.get("product") == parent_code for p in o.get("products", [])):
                        add_hit("bom_component", code, parent_code, o)

    at_risk.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["risk"]])

    # Generate PPTX
    sys.path.insert(0, os.path.join(HERE, "fusion-manage-mcp"))
    from src.tools.reporting import build_cia_pptx

    out_path = os.path.join(HERE, "CIA_CO-000463_Update-ID_v2.pptx")
    result = build_cia_pptx(
        tenant=PLM_TENANT,
        co=co,
        affected_items=affected,
        at_risk=at_risk,
        output_path=out_path,
    )
    print(f"\nPPTX saved to: {result}")


asyncio.run(main())
