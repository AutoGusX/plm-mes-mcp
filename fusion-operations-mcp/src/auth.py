"""
Fusion Operations authentication.

Fusion Operations uses its own token system (API_KEY:API_SECRET → bearer token),
separate from APS OAuth. This module manages that token lifecycle.

The MCP interface itself is protected by APS OAuth via Apigee (handled externally).
This module only handles the Fusion Operations API credentials.
"""

import base64
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FUSION_OPS_BASE_URL = "https://fusionoperations.autodesk.com/api/v1"
TOKEN_BUFFER_SECONDS = 120  # Refresh 2 minutes before expiry


class FusionOpsTokenManager:
    """
    Manages the Fusion Operations API token lifecycle.
    Tokens are valid for 2 hours; this class auto-refreshes as needed.
    """

    def __init__(self, api_key: str, api_secret: str):
        self._api_key = api_key
        self._api_secret = api_secret
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    @property
    def _credentials_b64(self) -> str:
        raw = f"{self._api_key}:{self._api_secret}"
        return base64.b64encode(raw.encode()).decode()

    def is_expired(self) -> bool:
        return time.time() >= (self._expires_at - TOKEN_BUFFER_SECONDS)

    async def get_token(self) -> str:
        if self._token is None or self.is_expired():
            await self._refresh()
        return self._token

    async def _refresh(self) -> None:
        logger.debug("Refreshing Fusion Operations token")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{FUSION_OPS_BASE_URL}/authorization",
                headers={
                    "Authorization": f"Basic {self._credentials_b64}",
                    "Content-Type": "application/json",
                },
                json={"scopes": ["productions_write"]},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["token"]
            # API returns a 2-hour token; no expires_in field in response
            expires_in = data.get("expires_in", 7200)
            self._expires_at = time.time() + expires_in
            logger.debug("Fusion Operations token refreshed, expires in %ds", expires_in)


def validate_gateway_secret(provided: Optional[str]) -> None:
    """Validate x-ads-gateway-secret. Skipped in DEV_MODE."""
    if os.getenv("DEV_MODE", "").lower() == "true":
        return

    expected = os.getenv("ADS_GATEWAY_SECRET")
    if not expected:
        logger.warning("ADS_GATEWAY_SECRET not set — skipping gateway validation")
        return

    if provided != expected:
        raise PermissionError("Invalid or missing x-ads-gateway-secret")


def create_token_manager() -> FusionOpsTokenManager:
    """Create a token manager from environment variables."""
    api_key = os.getenv("FUSION_OPS_API_KEY")
    api_secret = os.getenv("FUSION_OPS_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError(
            "FUSION_OPS_API_KEY and FUSION_OPS_API_SECRET must be set in environment"
        )

    return FusionOpsTokenManager(api_key=api_key, api_secret=api_secret)
