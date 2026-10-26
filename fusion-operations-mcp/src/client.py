"""
Fusion Operations API client.

All requests append ?access_token={token} as a query parameter.
Token lifecycle is managed by FusionOpsTokenManager in auth.py.
"""

import logging
from typing import Any, Optional

import httpx

from .auth import FusionOpsTokenManager

logger = logging.getLogger(__name__)

FUSION_OPS_BASE = "https://fusionoperations.autodesk.com/api/v1"


class FusionOperationsClient:
    def __init__(self, token_manager: FusionOpsTokenManager, timeout: float = 30.0):
        self._tokens = token_manager
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _params(self, extra: Optional[dict] = None) -> dict:
        token = await self._tokens.get_token()
        params = {"access_token": token}
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        return params

    async def _get(self, path: str, query: Optional[dict] = None) -> Any:
        async with httpx.AsyncClient(
            base_url=FUSION_OPS_BASE, timeout=self._timeout
        ) as client:
            response = await client.get(path, params=await self._params(query))
            self._raise_for_status(response)
            return response.json()

    async def _post(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient(
            base_url=FUSION_OPS_BASE, timeout=self._timeout
        ) as client:
            response = await client.post(
                path,
                params=await self._params(),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            self._raise_for_status(response)
            return response.json()

    async def _put(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient(
            base_url=FUSION_OPS_BASE, timeout=self._timeout
        ) as client:
            response = await client.put(
                path,
                params=await self._params(),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            self._raise_for_status(response)
            return response.json()

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient(
            base_url=FUSION_OPS_BASE, timeout=self._timeout
        ) as client:
            response = await client.delete(path, params=await self._params())
            self._raise_for_status(response)
            return {"success": True}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logger.error("Fusion Operations API error %d: %s", response.status_code, detail)
        response.raise_for_status()

    # ------------------------------------------------------------------
    # Production Orders
    # ------------------------------------------------------------------

    async def list_production_orders(
        self,
        page: int = 1,
        page_size: int = 25,
        code: Optional[str] = None,
        due_date_before: Optional[str] = None,
        due_date_after: Optional[str] = None,
    ) -> dict:
        return await self._get(
            "/production-orders/",
            query={
                "page": page,
                "page-size": page_size,
                "code": code,
                "due-date-before": due_date_before,
                "due-date-after": due_date_after,
            },
        )

    async def get_production_order(self, order_id: str) -> dict:
        return await self._get(f"/production-orders/{order_id}")

    async def create_production_order(self, data: dict) -> dict:
        return await self._post("/production-orders/", body=data)

    async def update_production_order(self, order_id: str, data: dict) -> dict:
        return await self._put(f"/production-orders/{order_id}", body=data)

    async def delete_production_order(self, order_id: str) -> dict:
        return await self._delete(f"/production-orders/{order_id}")

    async def activate_production_order(self, order_id: str) -> dict:
        return await self._post(f"/production-orders/{order_id}/activate", body={})

    async def notify_production_problem(self, order_id: str, data: dict) -> dict:
        return await self._post(f"/production-orders/{order_id}/notify", body=data)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def list_products(self, page: int = 1, page_size: int = 25) -> list:
        return await self._get("/products/", query={"page": page, "page-size": page_size})

    async def get_product(self, product_id: str) -> dict:
        return await self._get(f"/products/{product_id}")

    async def create_product(self, data: dict) -> dict:
        return await self._post("/products/", body=data)

    async def update_product(self, product_id: str, data: dict) -> dict:
        return await self._put(f"/products/{product_id}", body=data)

    async def post_bom(self, product_code: str, bom_items: list) -> dict:
        """
        POST /api/v1/bom — set the Bill of Materials for a product.

        Each bom_item: {"product-code": str, "quantity": float, "operation-code": str}
        The operation-code must reference an operation that exists on the parent product.

        Verified endpoint: POST /api/v1/bom?access_token=
        """
        return await self._post(
            "/bom",
            body={
                "product-code": product_code,
                "bom": bom_items,
            },
        )

    async def get_bom(self, product_code: str) -> list:
        """
        Retrieve the BOM components for a product via GET /products/{code}.

        The Fusion Operations API embeds the BOM in the product detail response
        as a `components` array. There is no standalone GET /bom endpoint.

        Each component entry: {"code": str, "name": str, "quantity": float, "operation": str}
        Returns an empty list if the product has no BOM or is not found.
        """
        try:
            product = await self._get(f"/products/{product_code}")
            return product.get("components", []) or []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Sales Orders
    # ------------------------------------------------------------------

    async def list_sales_orders(
        self,
        page: int = 1,
        page_size: int = 25,
        code: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> dict:
        return await self._get(
            "/sales-orders/",
            query={"page": page, "page-size": page_size, "code": code, "client-id": client_id},
        )

    async def get_sales_order(self, order_id: str) -> dict:
        return await self._get(f"/sales-orders/{order_id}")

    async def create_sales_order(self, data: dict) -> dict:
        return await self._post("/sales-orders/", body=data)

    async def update_sales_order(self, order_id: str, data: dict) -> dict:
        return await self._put(f"/sales-orders/{order_id}", body=data)

    async def delete_sales_order(self, order_id: str) -> dict:
        return await self._delete(f"/sales-orders/{order_id}")

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------

    async def list_purchase_orders(self, page: int = 1, page_size: int = 25) -> dict:
        return await self._get(
            "/purchase-orders/", query={"page": page, "page-size": page_size}
        )

    async def get_purchase_order(self, order_id: str) -> dict:
        return await self._get(f"/purchase-orders/{order_id}")

    async def create_purchase_order(self, data: dict) -> dict:
        return await self._post("/purchase-orders/", body=data)

    async def update_purchase_order(self, order_id: str, data: dict) -> dict:
        return await self._put(f"/purchase-orders/{order_id}", body=data)

    # ------------------------------------------------------------------
    # Inventory Movements
    # ------------------------------------------------------------------

    async def list_inventory_movements(self, page: int = 1, page_size: int = 25) -> dict:
        return await self._get(
            "/inventory-movements/", query={"page": page, "page-size": page_size}
        )

    async def create_inventory_movement(self, data: dict) -> dict:
        return await self._post("/inventory-movements/", body=data)

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    async def list_clients(self, page: int = 1, page_size: int = 25) -> dict:
        return await self._get("/clients/", query={"page": page, "page-size": page_size})

    async def get_client(self, client_id: str) -> dict:
        return await self._get(f"/clients/{client_id}")

    async def create_client(self, data: dict) -> dict:
        return await self._post("/clients/", body=data)

    async def update_client(self, client_id: str, data: dict) -> dict:
        return await self._put(f"/clients/{client_id}", body=data)

    # ------------------------------------------------------------------
    # Suppliers
    # ------------------------------------------------------------------

    async def list_suppliers(self, page: int = 1, page_size: int = 25) -> dict:
        return await self._get("/suppliers/", query={"page": page, "page-size": page_size})

    async def get_supplier(self, supplier_id: str) -> dict:
        return await self._get(f"/suppliers/{supplier_id}")

    async def create_supplier(self, data: dict) -> dict:
        return await self._post("/suppliers/", body=data)

    async def update_supplier(self, supplier_id: str, data: dict) -> dict:
        return await self._put(f"/suppliers/{supplier_id}", body=data)
