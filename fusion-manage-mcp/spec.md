# Fusion Manage MCP Server — Specification

## Overview

The `fusion-manage-mcp` server exposes Autodesk Fusion Manage (PLM) capabilities as MCP tools, enabling AI agents to interact with product lifecycle management data. It is deployed as a Cloud MCP server behind an Autodesk Apigee proxy, following the [APS MCP Authorization pattern](https://aps.autodesk.com).

---

## Architecture

### Deployment Model

```
MCP Client (Claude/Cursor/VS Code)
        │
        │ 3-legged APS OAuth token
        ▼
Apigee Proxy  (handles OAuth, discovery, MCP Authorization spec)
        │
        │ x-ads-token-data header + x-ads-gateway-secret
        ▼
fusion-manage-mcp  (this server, auth disabled — Apigee owns it)
        │
        │ Bearer token (3L or token exchange) + x-tenant header
        ▼
Fusion Manage v3 REST API  (https://{tenant}.autodeskplm.com/api/v3/)
```

### Transport

- **Protocol**: Streamable HTTP (only supported transport for Autodesk Cloud MCP)
- **Endpoint**: `POST /mcp`
- **Base path**: `/fusion-manage-mcp`
- **Full public URL**: `https://developer.api.autodesk.com/fusion-manage-mcp/mcp`

---

## Authentication

### Production (Apigee-mediated)

The MCP server runs with `--disable-auth`. Apigee handles all OAuth choreography and injects two headers:

| Header | Description |
|--------|-------------|
| `x-ads-token-data` | JSON blob with `access_token`, `scope`, `expires_in`, `client_id`, `userid` |
| `x-ads-gateway-secret` | Shared secret to verify the request came through Apigee (not direct) |

The server parses `x-ads-token-data` to obtain the user's access token, then uses it when calling Fusion Manage v3 API.

**x-ads-token-data shape:**
```json
{
  "access_token": { "userid": "MQY6JZF9XKX5", "oxygenid": "MQY6JZF9XKX5" },
  "scope": "mcp:read mcp:write",
  "expires_in": 3597,
  "client_id": "ThZzxufQsXGfjimiMiG3tU7rfOH4yQI0lGBSXvNjNIpU0ztT"
}
```

### Local Development

Set environment variables:

```env
FUSION_MANAGE_TOKEN=<3-legged APS access token>
FUSION_MANAGE_TENANT=<your tenant name>
ADS_GATEWAY_SECRET=<optional — skip gateway secret validation in dev>
DEV_MODE=true
```

To obtain a 3-legged token locally, use the APS OAuth 2.0 Authorization Code flow against:
- Authorize: `https://developer.api.autodesk.com/authentication/v2/authorize`
- Token: `POST https://developer.api.autodesk.com/authentication/v2/token`

Required scopes: `data:read data:write`

---

## APS App Registration

1. Create an app at [Autodesk Platform Services](https://aps.autodesk.com/myapps/)
2. Set app type to **Web App** or **Public MCP App** (for CIMD support)
3. Add callback URLs per MCP host:
   - Claude Code: `http://localhost:8181/callback`
   - Claude Desktop: `https://claude.ai/api/mcp/auth_callback`
   - Cursor: `cursor://anysphere.cursor-mcp/oauth/callback`
4. Note your `CLIENT_ID` and `CLIENT_SECRET`

---

## Fusion Manage API

- **Version**: v3 (primary), v1 for advanced search/reports
- **Base URL (v3)**: `https://{tenant}.autodeskplm.com/api/v3/`
- **Base URL (v1)**: `https://{tenant}.autodeskplm360.net/api/rest/v1/`
- **Required headers (v3)**:
  ```
  Authorization: Bearer {access_token}
  x-tenant: {tenant_name}
  Accept: application/json
  Content-Type: application/json
  ```

---

## MCP Tools

### Workspace Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_workspaces` | List all workspaces in the tenant | `GET /api/v3/workspaces` |
| `get_workspace` | Get metadata for a workspace | `GET /api/v3/workspaces/{wsId}` |
| `get_workspace_sections` | Get field sections/structure of a workspace | `GET /api/v3/workspaces/{wsId}/sections` |

### Item Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_workspace_items` | List items in a workspace (paginated) | `GET /api/v3/workspaces/{wsId}/items` |
| `get_workspace_item` | Get a single item by ID | `GET /api/v3/workspaces/{wsId}/items/{itemId}` |
| `search_workspace_items` | Search items with filters and sorting | `POST /api/v1/workspaces/{wsId}/items/search` |
| `create_workspace_item` | Create a new item in a workspace | `POST /api/v3/workspaces/{wsId}/items` |
| `update_workspace_item` | Update fields on an existing item | `PATCH /api/v3/workspaces/{wsId}/items/{itemId}` |

### Attachment Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_item_attachments` | List all file attachments on an item | `GET /api/v1/workspaces/{wsId}/items/{dmsId}/attachments` |

### Workflow Tools

| Tool | Description | API |
|------|-------------|-----|
| `get_workflow_history` | Get full workflow/lifecycle history of an item | `GET /api/v1/workspaces/{wsId}/items/{dmsId}/workflows/history` |
| `transition_workflow` | Move an item to the next workflow state | `PUT /api/v1/workspaces/{wsId}/items/{dmsId}/workflows/transitions/{transitionId}` |

### Report Tools

| Tool | Description | API |
|------|-------------|-----|
| `get_report` | Retrieve report data by report ID | `GET /api/v1/reports/{reportId}` |

---

## Tool Input/Output Contracts

### `list_workspaces`
**Input**: none
**Output**: Array of `{ id, label, category, uri }`

### `list_workspace_items`
**Input**: `wsId: int, page?: int, page_size?: int`
**Output**: Paginated list of items with fields and metadata

### `search_workspace_items`
**Input**:
```json
{
  "wsId": 2,
  "query": "optional free text",
  "filters": [{ "fieldID": "TITLE", "value": "Widget" }],
  "page": 1,
  "page_size": 50,
  "sort_field": "TITLE",
  "sort_order": "ASC"
}
```
**Output**: `{ total: int, items: [...] }`

### `create_workspace_item`
**Input**:
```json
{
  "wsId": 2,
  "fields": [{ "fieldId": "TITLE", "value": "My Part" }]
}
```
**Output**: Created item object

### `transition_workflow`
**Input**: `wsId: int, dms_id: int, transition_id: int, step: int, comments?: str`
**Output**: `{ success: bool }`

---

## Error Handling

| HTTP Code | Meaning | Behavior |
|-----------|---------|----------|
| 400 | Bad request / validation error | Return error message to LLM |
| 401 | Unauthorized | Raise auth error, instruct re-auth |
| 403 | Forbidden (gateway secret mismatch) | Reject request |
| 404 | Item/workspace not found | Return descriptive not-found message |
| 429 | Rate limited | Retry after indicated delay |
| 500 | Fusion Manage server error | Surface upstream error detail |

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FUSION_MANAGE_TENANT` | Yes | Tenant name (e.g. `mycompany`) |
| `FUSION_MANAGE_TOKEN` | Dev only | Static 3L token for local dev |
| `ADS_GATEWAY_SECRET` | Prod | x-ads-gateway-secret value |
| `DEV_MODE` | No | Set `true` to bypass gateway secret check |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING` |

### Apigee Proxy Config (api_spec.yaml)

```yaml
title: Fusion Manage MCP Server
name: fusion-manage-mcp
enable-mcp: true
add-oxygen-profile: false
base_path: /fusion-manage-mcp
paths:
  /mcp:
    post: {}
targets:
  - url: http://<internal-alb-url>
```

---

## Local Dev Quick Start

```bash
# Install
cd fusion-manage-mcp
uv sync

# Set env
cp .env.example .env
# fill in FUSION_MANAGE_TENANT, FUSION_MANAGE_TOKEN

# Run (auth disabled — Apigee handles it in prod)
uv run python -m src.server --disable-auth

# Add to Claude Code for local testing
claude mcp add --transport http \
  --client-id {YOUR_CLIENT_ID} --client-secret {YOUR_CLIENT_SECRET} \
  --callback-port 8181 \
  fusion-manage-mcp http://localhost:8000/mcp
```

---

## Future Tools (Phase 2)

The following tools are planned for the PLM↔MES data flow phase:

- `sync_bom_to_operations` — Push BOM from Fusion Manage to Fusion Operations as a product
- `get_ecr_items` — Fetch Engineering Change Requests for routing to MES
- `update_item_from_production_record` — Write back actual production data to PLM item fields
- `get_released_parts` — Query workspace for items in "Released" workflow state
