"""
Change Impact Analysis: CO-000463 - Update ID
Thorough analysis including supplier quotes, real lead time, and timeline risk.
"""
import asyncio, base64, os, httpx
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


def classify_risk(order):
    if order.get("is-active"):
        return "HIGH"
    if order.get("running-status", "") != "closed":
        return "MEDIUM"
    return "LOW"


def days_until(date_str):
    if not date_str:
        return None
    try:
        due = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (due - TODAY).days
    except Exception:
        return None


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


async def fetch_sourcing(ws_id: int, item_id: int) -> dict:
    """Fetch AML suppliers + all quotes; return structured sourcing data."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{V3}/workspaces/{ws_id}/items/{item_id}/views/8/suppliers",
            headers=PLM_HDR,
        )
    if not r.is_success:
        return {"suppliers": [], "min_lead_time_days": None, "default_lead_time_days": None,
                "has_quotes": False}

    raw = r.json()
    suppliers_out = []
    all_lead_times = []
    default_lead_time = None

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
            lt       = q.get("leadTime") or 0
            lt_mult  = q.get("leadTimeMultiplier") or 1
            lt_days  = lt * lt_mult
            is_def   = q.get("defaultQuote", False)
            bom_assemblies = [
                {"dms_id": int(a["link"].split("/")[-1]), "title": a.get("title")}
                for a in q.get("bomAssemblies", [])
                if a.get("link")
            ]
            quotes_out.append({
                "lead_time_days": lt_days,
                "unit_price":     q.get("unitPrice"),
                "min_qty":        q.get("minAmount"),
                "max_qty":        q.get("maxAmount"),
                "is_default":     is_def,
                "bom_assemblies": bom_assemblies,
            })
            if lt_days > 0:
                all_lead_times.append(lt_days)
            if is_def and lt_days > 0:
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
        "suppliers":              suppliers_out,
        "min_lead_time_days":     min(all_lead_times) if all_lead_times else None,
        "default_lead_time_days": default_lead_time,
        "has_quotes":             raw.get("hasQuotes", False),
    }


async def main():
    print("=" * 65)
    print("CHANGE IMPACT ANALYSIS  --  CO-000463 - Update ID")
    print("=" * 65)

    # ── 1. CO details + affected items ────────────────────────────────────
    print("\n[1] Change Order")
    async with httpx.AsyncClient(timeout=30) as c:
        r_co = await c.get(f"{V3}/workspaces/{CO_WS}/items/{CO_ID}", headers=PLM_HDR)
        r_mi = await c.get(f"{V3}/workspaces/{CO_WS}/items/{CO_ID}/views/11", headers=PLM_HDR)
    r_co.raise_for_status(); r_mi.raise_for_status()

    co = r_co.json()
    print(f"  Title:          {co.get('title')}")
    print(f"  Workflow state: {co.get('currentState', {}).get('title')}")

    affected = []
    for ai in r_mi.json().get("affectedItems", []):
        link  = ai.get("item", {}).get("link", "")
        parts = link.split("/")
        try:
            wi     = parts.index("workspaces")
            dms_id = int(parts[parts.index("items", wi) + 1])
            ws_id  = int(parts[wi + 1])
        except (ValueError, IndexError):
            dms_id = ws_id = None
        affected.append({
            "dms_id":      dms_id, "ws_id": ws_id,
            "title":       ai.get("item", {}).get("title"),
            "transition":  ai.get("targetTransition", {}).get("title"),
            "from_rel":    ai.get("fromRelease", ""),
            "to_rel":      ai.get("toRelease", ""),
            "effectivity": ai.get("effectivityDate"),
            "ops_code":    str(dms_id) if dms_id else None,
        })

    print(f"  Affected items: {len(affected)}")
    for ai in affected:
        print(f"    [{ai['dms_id']}]  {ai['title']}")
        print(f"      Transition: {ai['transition']}  |  "
              f"Release: '{ai['from_rel']}' -> '{ai['to_rel']}'")
        print(f"      Effectivity: {ai['effectivity']}")

    # ── 2. Item detail + sourcing (suppliers & quotes with lead times) ─────
    print("\n[2] Affected Item Detail & Sourcing")
    for ai in affected:
        dms_id = ai["dms_id"]
        ws_id  = ai["ws_id"]

        async with httpx.AsyncClient(timeout=30) as c:
            r_item = await c.get(f"{V1}/workspaces/{ws_id}/items/{dms_id}", headers=PLM_HDR)
        item    = r_item.json().get("item", r_item.json())
        details = item.get("details", {})
        meta    = {e["key"]: e.get("fieldData", {}).get("value", "")
                   for e in item.get("metaFields", {}).get("entry", [])}

        # Where-used from PLM inverse BOM relation
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

        # Supplier quotes (real lead time source)
        sourcing = await fetch_sourcing(ws_id, dms_id)

        ai["procurement"]  = meta.get("PDM_CATEGORY", "Unknown")
        ai["material"]     = meta.get("MATERIAL", "")
        ai["dimensions"]   = meta.get("PDM_SIZE") or meta.get("DIMENSIONS", "")
        ai["mass_kg"]      = meta.get("PDM_MASS", "")
        ai["pdm_status"]   = meta.get("PDM_STATUS_NAME", "")
        ai["pdm_revision"] = meta.get("PDM_REVISION", "")
        ai["where_used"]   = where_used
        ai["sourcing"]     = sourcing

        print(f"\n  [{dms_id}]  {ai['title']}")
        print(f"    Lifecycle (PLM):   {details.get('lifecycleStatus')}  |  "
              f"PDM status: {ai['pdm_status']} Rev {ai['pdm_revision']}")
        print(f"    Procurement type:  {ai['procurement']}")
        print(f"    Material:          {ai['material']}")
        print(f"    Dimensions:        {ai['dimensions']}  |  Mass: {ai['mass_kg']} kg")
        print(f"    Where-used ({len(where_used)} assembly(s)):")
        for wu in where_used:
            rel_str = f"  Rev {wu['release']}" if wu.get("release") else ""
            print(f"      [{wu['dms_id']}]  {wu['title']}  ({wu['lifecycle']}{rel_str})")

        print(f"\n    Suppliers & Quotes  ({len(sourcing['suppliers'])} supplier(s)):")
        if not sourcing["suppliers"]:
            print("      No suppliers on AML  <-- data gap")
        for sup in sourcing["suppliers"]:
            print(f"      Supplier: {sup['supplier_name']}"
                  f"  (part# {sup['supplier_part_number']}"
                  f"  mfr: {sup['manufacturer']} {sup['manufacturer_part_number']})")
            if not sup["quotes"]:
                print("        No quotes on file")
            for q in sup["quotes"]:
                def_marker = " [DEFAULT]" if q["is_default"] else ""
                bom_titles = ", ".join(a["title"] for a in q["bom_assemblies"])
                print(f"        Quote{def_marker}: lead time = {q['lead_time_days']} days  |  "
                      f"unit price = ${q['unit_price']}  |  "
                      f"qty range = {q['min_qty']}-{q['max_qty']}")
                if bom_titles:
                    print(f"          Applies to: {bom_titles}")

        if sourcing["default_lead_time_days"] is not None:
            print(f"\n    Lead time (default quote): {sourcing['default_lead_time_days']} days")
        elif sourcing["min_lead_time_days"] is not None:
            print(f"\n    Lead time (best available): {sourcing['min_lead_time_days']} days")
        else:
            print(f"\n    Lead time: NOT AVAILABLE from quotes  <-- data gap")

    # ── 3. Production impact: direct + BOM ancestry ────────────────────────
    print("\n[3] Production Order Impact")
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

    affected_codes = {ai["ops_code"] for ai in affected if ai["ops_code"]}
    where_used_codes = {
        wu["ops_code"]
        for ai in affected
        for wu in ai.get("where_used", [])
    }

    # Fetch BOMs for products on orders that aren't already in our check sets
    order_product_codes = {
        p.get("product")
        for o in all_orders
        for p in o.get("products", [])
        if p.get("product")
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
            "match_type":     match_type,
            "part":           code,
            "parent":         parent,
            "order_code":     order.get("code"),
            "order_id":       order.get("id"),
            "status":         order.get("running-status"),
            "active":         order.get("is-active"),
            "qty_ordered":    ordered,
            "qty_produced":   produced,
            "pct":            round(produced / ordered * 100, 1) if ordered else 0,
            "due":            due_str,
            "days_until_due": days_until(due_str),
            "risk":           classify_risk(order),
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

    print(f"  Total orders in MES:  {len(all_orders)}")
    print(f"  At-risk orders found: {len(at_risk)}")
    for r in at_risk:
        tag    = "DIRECT" if r["match_type"] == "direct" else "BOM   "
        parent = f"  via assembly {r['parent']}" if r["parent"] else ""
        days   = f"  [{r['days_until_due']}d until due]" if r["days_until_due"] is not None else ""
        print(f"\n    [{r['risk']:6}] [{tag}] Order {r['order_code']}{parent}")
        print(f"             status={r['status']}  active={r['active']}"
              f"  {r['pct']}% done  due={r['due']}{days}")
        print(f"             qty ordered={r['qty_ordered']}  produced={r['qty_produced']}")

    # ── 4. Lead time vs. order timeline ───────────────────────────────────
    print("\n[4] Lead Time vs. Order Timeline")
    for ai in affected:
        sourcing   = ai["sourcing"]
        lt_days    = sourcing.get("default_lead_time_days") or sourcing.get("min_lead_time_days")
        lt_source  = ("default quote" if sourcing.get("default_lead_time_days")
                      else "best available quote" if sourcing.get("min_lead_time_days")
                      else "none on file")

        my_orders = [r for r in at_risk if r["part"] == ai["ops_code"]]
        print(f"\n  Part [{ai['dms_id']}]  {ai['title']}")
        print(f"    Lead time: "
              + (f"{lt_days} days  (from {lt_source})" if lt_days else f"NOT AVAILABLE  ({lt_source})"))

        if not my_orders:
            print("    No production orders currently at risk for this part.")
            continue

        for r in my_orders:
            days_left = r["days_until_due"]
            print(f"\n    Order {r['order_code']}  --  due in {days_left} day(s)"
                  + (f"  via assembly {r['parent']}" if r["parent"] else ""))
            if lt_days is None:
                print(f"      UNKNOWN RISK: no lead time data to compare against {days_left}d window")
                print(f"      Action: obtain supplier quote immediately and enter in PLM")
            elif days_left <= lt_days:
                shortfall = lt_days - days_left
                print(f"      CANNOT implement change in time:")
                print(f"      {days_left}d remaining  <  {lt_days}d lead time  "
                      f"(shortfall: {shortfall}d)")
                print(f"      Options:")
                print(f"        1. Use existing pre-change stock for this order;")
                print(f"           set ECO effectivity to next order")
                print(f"        2. Request expedite from supplier"
                      + (f" ({', '.join(s['supplier_name'] for s in sourcing['suppliers'])})"
                         if sourcing["suppliers"] else ""))
                print(f"        3. Hold order until new stock arrives (impacts delivery)")
            else:
                slack = days_left - lt_days
                print(f"      Change IS achievable: {days_left}d remaining > {lt_days}d lead time")
                print(f"      Slack: {slack}d -- place order with supplier now to preserve buffer")

    # ── 5. Where-used scope ───────────────────────────────────────────────
    print("\n[5] Full Where-Used Scope (All Assemblies in PLM)")
    for ai in affected:
        print(f"\n  Part [{ai['dms_id']}]  {ai['title']} is a BOM component of:")
        for wu in ai.get("where_used", []):
            on_order = any(r["parent"] == wu["ops_code"] for r in at_risk)
            flag     = "  <-- HAS OPEN ORDERS" if on_order else ""
            rel_str  = f"  Rev {wu['release']}" if wu.get("release") else ""
            print(f"    [{wu['dms_id']}]  {wu['title']}  ({wu['lifecycle']}{rel_str}){flag}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    high  = sum(1 for r in at_risk if r["risk"] == "HIGH")
    med   = sum(1 for r in at_risk if r["risk"] == "MEDIUM")
    direct_ct = sum(1 for r in at_risk if r["match_type"] == "direct")
    bom_ct    = sum(1 for r in at_risk if r["match_type"] == "bom_component")
    print(f"\n  At-risk orders:  {len(at_risk)}  (HIGH: {high}, MEDIUM: {med})")
    print(f"  Direct matches:  {direct_ct}  |  BOM-component matches: {bom_ct}")

    for ai in affected:
        sourcing  = ai["sourcing"]
        lt_days   = sourcing.get("default_lead_time_days") or sourcing.get("min_lead_time_days")
        my_orders = [r for r in at_risk if r["part"] == ai["ops_code"]]
        if not my_orders:
            print(f"\n  Part {ai['dms_id']}: no active production impact.")
            continue

        min_days = min(
            r["days_until_due"] for r in my_orders if r["days_until_due"] is not None
        )
        if lt_days and min_days <= lt_days:
            urgency = "CRITICAL"
        elif lt_days and min_days <= lt_days * 1.5:
            urgency = "HIGH"
        elif lt_days:
            urgency = "MEDIUM"
        else:
            urgency = "UNKNOWN -- obtain lead time immediately"

        supplier_names = ", ".join(
            s["supplier_name"] for s in sourcing["suppliers"] if s["supplier_name"]
        ) or "none on AML"
        print(f"\n  Part {ai['dms_id']} ({ai['title']}):")
        print(f"    Procurement:       {ai['procurement']}")
        print(f"    Suppliers (AML):   {supplier_names}")
        print(f"    Lead time:         "
              + (f"{lt_days} days" if lt_days else "NOT SPECIFIED"))
        print(f"    Nearest due date:  {min_days} day(s)  -->  URGENCY: {urgency}")
        print(f"    Recommendation:")
        if lt_days and min_days <= lt_days:
            print(f"      ECO cannot be applied to order {my_orders[0]['order_code']}.")
            print(f"      Contact {supplier_names} to check expedite availability.")
            print(f"      If not feasible: apply ECO effective next order; ship existing stock.")
        elif lt_days:
            print(f"      Place order with supplier now to maintain schedule.")
        else:
            print(f"      Lead time unknown -- obtain supplier quote before advancing CO workflow.")

    print("\n" + "=" * 65)


asyncio.run(main())
