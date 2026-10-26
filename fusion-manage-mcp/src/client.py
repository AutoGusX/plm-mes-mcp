"""
Fusion Manage API client.

Uses Fusion Manage v1 REST API:
  https://{tenant}.autodeskplm360.net/api/rest/v1/

Note: v3 (autodeskplm.com) is not available on all tenants.
All endpoints use v1 for compatibility.
"""

import logging
import os
from typing import Any, Optional

import httpx

from .auth import AuthContext

logger = logging.getLogger(__name__)


class FusionManageClient:
    def __init__(self, auth: AuthContext, timeout: float = 30.0):
        self._auth = auth
        self._timeout = timeout
        self._v1_base = f"https://{auth.tenant}.autodeskplm360.net/api/rest/v1"
        self._v3_base = f"https://{auth.tenant}.autodeskplm360.net/api/v3"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, url: str, params: Optional[dict] = None) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                url, headers=self._auth.bearer_headers, params=params
            )
            self._raise_for_status(response)
            result = response.json()
            return result if result is not None else {}

    async def _post(self, url: str, body: dict) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url, headers=self._auth.bearer_headers, json=body
            )
            self._raise_for_status(response)
            return response.json()

    async def _patch(self, url: str, body: dict) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.patch(
                url, headers=self._auth.bearer_headers, json=body
            )
            self._raise_for_status(response)
            return response.json()

    async def _put(self, url: str, body: dict) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(
                url, headers=self._auth.bearer_headers, json=body
            )
            self._raise_for_status(response)
            # 204 returns no body
            if response.status_code == 204:
                return {"success": True}
            return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logger.error("Fusion Manage API error %d: %s", response.status_code, detail)
        response.raise_for_status()

    # ------------------------------------------------------------------
    # Workspaces (v1)
    # ------------------------------------------------------------------

    async def list_workspaces(self) -> dict:
        return await self._get(f"{self._v1_base}/workspaces")

    async def search(
        self,
        query: str,
        revision: int = 1,
        limit: int = 50,
        offset: int = 0,
        page: int = 1,
    ) -> dict:
        """
        Global full-text search via v3 search-results endpoint.

        revision: 1 = latest only, 2 = all revisions, 3 = working/unreleased only
        Returns raw API response — caller extracts workspace ID and dmsId from __self__.
        """
        return await self._get(
            f"{self._v3_base}/search-results",
            params={
                "query": query,
                "revision": revision,
                "limit": limit,
                "offset": offset,
                "page": page,
            },
        )

    async def get_workspace_sections(self, ws_id: int) -> dict:
        return await self._get(f"{self._v3_base}/workspaces/{ws_id}/sections")

    # ------------------------------------------------------------------
    # Items (v1 list/search, v3 create/update/get)
    # ------------------------------------------------------------------

    async def list_workspace_items(
        self, ws_id: int, page: int = 1, size: int = 100
    ) -> dict:
        return await self._get(
            f"{self._v1_base}/workspaces/{ws_id}/items",
            params={"page": page, "size": size, "includeRelationships": "true"},
        )

    async def get_workspace_item(self, ws_id: int, item_id: int) -> dict:
        # v3 not available on this tenant — use v1 item detail endpoint
        return await self._get(f"{self._v1_base}/workspaces/{ws_id}/items/{item_id}")

    async def get_workspace_item_v3(self, ws_id: int, item_id: int) -> dict:
        """v3 item detail — returns title, currentState, createdDate, etc."""
        return await self._get(f"{self._v3_base}/workspaces/{ws_id}/items/{item_id}")

    async def get_item_managed_items(self, ws_id: int, item_id: int) -> dict:
        """
        views/2 — Change Orders linked to an item (item → COs direction).

        View ID is read from PLM_CO_VIEW_ID env var (default 2).
        Returns a plain list of CO references when called on a part/assembly item.
        """
        view_id = int(os.getenv("PLM_CO_VIEW_ID", "2"))
        try:
            return await self._get(
                f"{self._v3_base}/workspaces/{ws_id}/items/{item_id}/views/{view_id}"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.warning(
                    "views/%d returned 403 for ws=%d item=%d — "
                    "view may not exist in this workspace; set PLM_CO_VIEW_ID in .env",
                    view_id, ws_id, item_id,
                )
                return []
            raise

    async def get_co_affected_items(self, ws_id: int, co_id: int) -> dict:
        """
        views/11 — Affected items listed on a Change Order (CO → items direction).

        Returns a dict with affectedItems[]. Each entry has:
          item.link  (contains workspace ID and DMS ID)
          item.title
          targetTransition.title
          fromRelease / toRelease
          effectivityDate
        """
        try:
            return await self._get(
                f"{self._v3_base}/workspaces/{ws_id}/items/{co_id}/views/11"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.warning(
                    "views/11 returned 403 for ws=%d co=%d — "
                    "CO may not be in a workspace that supports this view",
                    ws_id, co_id,
                )
                return {"affectedItems": []}
            raise

    async def search_workspace_items(self, ws_id: int, search_def: dict) -> dict:
        return await self._post(
            f"{self._v1_base}/workspaces/{ws_id}/items/search",
            body={"searchDefinition": search_def},
        )

    async def create_workspace_item(self, ws_id: int, fields: dict) -> dict:
        # v1 create: POST /workspaces/{id}/items with field map
        return await self._post(
            f"{self._v1_base}/workspaces/{ws_id}/items",
            body=fields,
        )

    async def update_workspace_item(
        self, ws_id: int, item_id: int, fields: dict
    ) -> dict:
        return await self._put(
            f"{self._v1_base}/workspaces/{ws_id}/items/{item_id}",
            body=fields,
        )

    # ------------------------------------------------------------------
    # Suppliers & Quotes (v3 AML — view 8)
    # ------------------------------------------------------------------

    async def get_item_suppliers(self, ws_id: int, item_id: int) -> dict:
        """
        GET /api/v3/workspaces/{ws}/items/{id}/views/8/suppliers
        Returns the Approved Manufacturer/Supplier list with hasQuotes flag.
        Each supplier entry has: supplier.title, supplierPartNumber,
        manufacturer, manufacturerPartNumber, and a quotes.link.
        """
        return await self._get(
            f"{self._v3_base}/workspaces/{ws_id}/items/{item_id}/views/8/suppliers"
        )

    async def get_item_supplier_quotes(
        self, ws_id: int, item_id: int, supplier_id: int
    ) -> list:
        """
        GET /api/v3/workspaces/{ws}/items/{id}/views/8/suppliers/{sid}/quotes
        Returns quote entries for one supplier. Each quote has:
          leadTime, leadTimeMultiplier, unitPrice, minAmount, maxAmount,
          defaultQuote (bool), bomAssemblies (list of assemblies this applies to).
        Effective lead time in days = leadTime * leadTimeMultiplier.
        """
        return await self._get(
            f"{self._v3_base}/workspaces/{ws_id}/items/{item_id}/views/8/suppliers/{supplier_id}/quotes"
        )

    # ------------------------------------------------------------------
    # Attachments (v1)
    # ------------------------------------------------------------------

    async def list_item_attachments(self, ws_id: int, dms_id: int) -> list:
        return await self._get(
            f"{self._v1_base}/workspaces/{ws_id}/items/{dms_id}/attachments"
        )

    # ------------------------------------------------------------------
    # Workflow (v1)
    # ------------------------------------------------------------------

    async def get_workflow_history(self, ws_id: int, dms_id: int) -> dict:
        try:
            return await self._get(
                f"{self._v1_base}/workspaces/{ws_id}/items/{dms_id}/workflows/history"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.warning(
                    "Workflow history not available for ws=%d item=%d "
                    "(403 — workspace may not have workflows enabled)",
                    ws_id, dms_id,
                )
                return {"list": {"historySteps": []}}
            raise

    async def transition_workflow(
        self,
        ws_id: int,
        dms_id: int,
        transition_id: int,
        step: int,
        comments: str = "",
    ) -> dict:
        return await self._put(
            f"{self._v1_base}/workspaces/{ws_id}/items/{dms_id}/workflows/transitions/{transition_id}",
            body={"workflowStep": step, "workflowComments": comments},
        )

    # ------------------------------------------------------------------
    # Reports (v1)
    # ------------------------------------------------------------------

    async def get_report(self, report_id: int) -> dict:
        return await self._get(f"{self._v1_base}/reports/{report_id}")
