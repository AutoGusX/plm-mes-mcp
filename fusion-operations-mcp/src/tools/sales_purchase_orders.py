from typing import Optional
from ..client import FusionOperationsClient


# -- Sales Orders --

async def list_sales_orders(
    client: FusionOperationsClient, page: int, page_size: int, code: Optional[str]
) -> dict:
    return await client.list_sales_orders(page=page, page_size=page_size, code=code)


async def get_sales_order(client: FusionOperationsClient, order_id: str) -> dict:
    return await client.get_sales_order(order_id)


async def create_sales_order(
    client: FusionOperationsClient,
    code: str,
    client_id: str,
    items: list[dict],
    due_date: str,
    shipping_address: str,
) -> dict:
    return await client.create_sales_order(
        {
            "code": code,
            "client": {"id": client_id},
            "items": [
                {"product": {"id": i["product_id"]}, "quantity": i["quantity"]}
                for i in items
            ],
            "due_date": due_date,
            "shipping_address": shipping_address,
        }
    )


# -- Purchase Orders --

async def list_purchase_orders(
    client: FusionOperationsClient, page: int, page_size: int
) -> dict:
    return await client.list_purchase_orders(page=page, page_size=page_size)


async def get_purchase_order(client: FusionOperationsClient, order_id: str) -> dict:
    return await client.get_purchase_order(order_id)


async def create_purchase_order(
    client: FusionOperationsClient,
    code: str,
    supplier_id: str,
    items: list[dict],
    expected_date: str,
) -> dict:
    return await client.create_purchase_order(
        {
            "code": code,
            "supplier": {"id": supplier_id},
            "items": [
                {"product": {"id": i["product_id"]}, "quantity": i["quantity"]}
                for i in items
            ],
            "expected_date": expected_date,
        }
    )
