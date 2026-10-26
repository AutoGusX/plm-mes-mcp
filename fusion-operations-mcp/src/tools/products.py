"""
Product tools — field names verified against live Fusion Operations API.

Actual product fields: code, name, observations, section, unit-cost,
unit-price, families, operations (with waste, task-durations, etc.)

Products are identified by `code` (not a separate `id` field).
"""

from ..client import FusionOperationsClient


async def list_products(client: FusionOperationsClient, page: int, page_size: int) -> list:
    return await client.list_products(page=page, page_size=page_size)


async def get_product(client: FusionOperationsClient, product_code: str) -> dict:
    return await client.get_product(product_code)


async def create_product(
    client: FusionOperationsClient, code: str, name: str, observations: str = ""
) -> dict:
    return await client.create_product({
        "code": code,
        "name": name,
        "observations": observations,
    })


async def update_bom(
    client: FusionOperationsClient, product_code: str, bom_items: list[dict]
) -> dict:
    """
    Update BOM for a product. In Fusion Operations, BOM is represented
    as component products. Each bom_item should have:
      {component_code, quantity, observations}
    """
    normalized = [
        {
            "component": item.get("component_code", ""),
            "quantity": item["quantity"],
            "observations": item.get("observations", ""),
        }
        for item in bom_items
    ]
    return await client.update_product_bom(product_code, normalized)
