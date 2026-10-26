"""
APS / Fusion Manage authentication helpers.

In production: auth is handled by Apigee. This module parses the
x-ads-token-data header injected by the proxy and validates the
x-ads-gateway-secret.

In local dev (DEV_MODE=true): uses FUSION_MANAGE_TOKEN from env.
"""

import base64
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AuthContext:
    """Resolved auth state for a single MCP request."""

    def __init__(self, access_token: str, user_id: Optional[str], tenant: str):
        self.access_token = access_token
        self.user_id = user_id
        self.tenant = tenant

    @property
    def bearer_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "x-tenant": self.tenant,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }


def parse_token_data_header(header_value: str) -> dict:
    """Parse the x-ads-token-data header injected by Apigee."""
    try:
        return json.loads(header_value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid x-ads-token-data header: {exc}") from exc


def validate_gateway_secret(provided: Optional[str]) -> None:
    """
    Validate the x-ads-gateway-secret header to ensure requests came
    through Apigee and not directly to the server.

    Skipped when DEV_MODE=true.
    """
    if os.getenv("DEV_MODE", "").lower() == "true":
        return

    expected = os.getenv("ADS_GATEWAY_SECRET")
    if not expected:
        logger.warning("ADS_GATEWAY_SECRET not set — skipping gateway validation")
        return

    if provided != expected:
        raise PermissionError("Invalid or missing x-ads-gateway-secret")


def resolve_auth_context(
    token_data_header: Optional[str] = None,
    gateway_secret_header: Optional[str] = None,
) -> AuthContext:
    """
    Resolve the auth context for an incoming MCP request.

    Production path: parse x-ads-token-data, validate gateway secret.
    Dev path: fall back to FUSION_MANAGE_TOKEN env var.
    """
    tenant = os.getenv("FUSION_MANAGE_TENANT", "")
    if not tenant:
        raise ValueError("FUSION_MANAGE_TENANT environment variable is required")

    validate_gateway_secret(gateway_secret_header)

    # Production: token injected by Apigee
    if token_data_header:
        data = parse_token_data_header(token_data_header)
        # x-ads-token-data contains access_token as an object with userid
        # The actual bearer token we need for upstream calls comes from token exchange
        # or is provided directly — Apigee docs show access_token as a dict of claims.
        # For upstream REST calls we need the raw token string; Apigee may also inject
        # x-ads-access-token separately. Handle both shapes.
        token_obj = data.get("access_token", {})
        if isinstance(token_obj, str):
            access_token = token_obj
        else:
            # token_obj is the claims dict; the raw token isn't directly available here.
            # In practice, configure Apigee to also inject x-ads-access-token header,
            # or use token exchange to obtain a token for Fusion Manage.
            # For now, raise a clear error so the caller can configure correctly.
            raise ValueError(
                "x-ads-token-data contains token claims but not the raw access token. "
                "Configure Apigee to inject x-ads-access-token, or implement token exchange."
            )
        user_id = token_obj.get("userid") if isinstance(token_obj, dict) else None
        return AuthContext(access_token=access_token, user_id=user_id, tenant=tenant)

    # Local dev: static token from env
    dev_token = os.getenv("FUSION_MANAGE_TOKEN")
    if dev_token:
        logger.debug("Using FUSION_MANAGE_TOKEN from environment (dev mode)")
        return AuthContext(access_token=dev_token, user_id=None, tenant=tenant)

    raise ValueError(
        "No auth token available. In production, ensure Apigee injects x-ads-token-data. "
        "In dev, set FUSION_MANAGE_TOKEN in your .env file."
    )
