"""
Production order tools — field names verified against live Fusion Operations API.

Actual response fields (kebab-case):
  products, code, shipping, start-date, due-date, description,
  ended, machines, notes, is-active, running-status, status,
  material-staging-complete, id

products[] items: {product: code_str, quantity-ordered, observations, quantity-produced}
"""

from typing import Optional
from ..client import FusionOperationsClient


async def list_orders(
    client: FusionOperationsClient,
    page: int,
    page_size: int,
    code: Optional[str],
    due_date_before: Optional[str],
    due_date_after: Optional[str],
) -> list:
    orders = await client.list_production_orders(
        page=page,
        page_size=page_size,
        code=code,
        due_date_before=due_date_before,
        due_date_after=due_date_after,
    )
    return orders


async def get_order(client: FusionOperationsClient, order_id: str) -> dict:
    return await client.get_production_order(order_id)


async def create_order(
    client: FusionOperationsClient,
    code: str,
    product_code: str,
    quantity: float,
    due_date: str,
    notes: str,
) -> dict:
    return await client.create_production_order({
        "code": code,
        "products": [
            {
                "product": product_code,
                "quantity-ordered": quantity,
                "observations": notes,
            }
        ],
        "due-date": due_date,
        "notes": notes,
    })


async def update_order(
    client: FusionOperationsClient, order_id: str, data: dict
) -> dict:
    return await client.update_production_order(order_id, data)


async def delete_order(client: FusionOperationsClient, order_id: str) -> dict:
    return await client.delete_production_order(order_id)


async def activate_order(client: FusionOperationsClient, order_id: str) -> dict:
    return await client.activate_production_order(order_id)


async def notify_problem(
    client: FusionOperationsClient,
    order_id: str,
    problem_type: str,
    description: str,
    severity: str,
) -> dict:
    return await client.notify_production_problem(
        order_id,
        {"problem-type": problem_type, "description": description, "severity": severity},
    )
