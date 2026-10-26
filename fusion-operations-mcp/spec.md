# Fusion Operations MCP Server — Specification

## Overview

The `fusion-operations-mcp` server exposes Autodesk Fusion Operations (MES) capabilities as MCP tools, enabling AI agents to interact with manufacturing execution data including production orders, products, inventory, and quality records.

---

## Architecture

### Deployment Model

```
MCP Client (Claude/Cursor/VS Code)
        │
        │ 3-legged APS OAuth token (MCP client → Apigee)
        ▼
Apigee Proxy  (handles OAuth, discovery, MCP Authorization spec)
        │
        │ x-ads-token-data header + x-ads-gateway-secret
        ▼
fusion-operations-mcp  (this server, MCP auth disabled)
        │
        │ API_KEY:API_SECRET → Bearer token
        ▼
Fusion Operations REST API  (https://fusionoperations.autodesk.com/api/v1/)
```

> Note: Fusion Operations uses its own token-based auth (API key/secret), separate from APS OAuth. The APS/Apigee layer secures the MCP interface; the server holds the Fusion Operations credentials as service-to-service secrets.

### Transport

- **Protocol**: Streamable HTTP
- **Endpoint**: `POST /mcp`
- **Base path**: `/fusion-operations-mcp`
- **Full public URL**: `https://developer.api.autodesk.com/fusion-operations-mcp/mcp`

---

## Authentication

### MCP Layer (Apigee — same as Fusion Manage MCP)

Apigee handles APS OAuth for all inbound MCP traffic. This server runs with `--disable-auth`.

Headers injected by Apigee:
- `x-ads-token-data` — user context
- `x-ads-gateway-secret` — gateway verification secret

### Fusion Operations API Layer

Fusion Operations uses its own token system, independent of APS OAuth:

1. **Obtain token**: `GET /api/v1/authorization` with `Authorization: Basic base64(API_KEY:API_SECRET)`
2. **Token validity**: 2 hours
3. **Use token**: Append `?access_token={token}` to all requests
4. **Refresh**: Re-authenticate when 401 received

The server manages token lifecycle internally (acquire on startup, refresh on expiry).

### Local Development

```env
FUSION_OPS_API_KEY=<your api key>
FUSION_OPS_API_SECRET=<your api secret>
ADS_GATEWAY_SECRET=<optional>
DEV_MODE=true
```

---

## Fusion Operations API

- **Version**: v1
- **Base URL**: `https://fusionoperations.autodesk.com/api/v1/`
- **Auth**: Query param `?access_token={token}` on all requests
- **Rate limit**: 120 requests/minute/company (HTTP 429 + `Retry-After` header)
- **Pagination**: `?page={n}&page-size={n}` (default 25/page)
- **Date format**: ISO 8601 — `YYYY-MM-DDTHH:MM:SSZ` (UTC) or without `Z` for company timezone

---

## MCP Tools

### Production Order Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_production_orders` | List production orders with filters | `GET /production-orders/` |
| `get_production_order` | Get a single production order | `GET /production-orders/{id}` |
| `create_production_order` | Create a new production order | `POST /production-orders/` |
| `update_production_order` | Update an existing production order | `PUT /production-orders/{id}` |
| `delete_production_order` | Remove a production order | `DELETE /production-orders/{id}` |
| `activate_production_order` | Activate/release a production order to the floor | `POST /production-orders/{id}/activate` |
| `notify_production_problem` | Log a problem against a production order | `POST /production-orders/{id}/notify` |

### Product Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_products` | List all products/parts | `GET /products/` |
| `get_product` | Get product details | `GET /products/{id}` |
| `create_product` | Create a new product record | `POST /products/` |
| `update_product` | Update product fields | `PUT /products/{id}` |
| `update_product_bom` | Update the Bill of Materials for a product | `POST /products/{id}/bom` |

### Sales Order Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_sales_orders` | List sales orders with filters | `GET /sales-orders/` |
| `get_sales_order` | Get a specific sales order | `GET /sales-orders/{id}` |
| `create_sales_order` | Create a new sales order | `POST /sales-orders/` |
| `update_sales_order` | Update a sales order | `PUT /sales-orders/{id}` |
| `delete_sales_order` | Remove a sales order | `DELETE /sales-orders/{id}` |

### Purchase Order Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_purchase_orders` | List purchase orders | `GET /purchase-orders/` |
| `get_purchase_order` | Get a specific purchase order | `GET /purchase-orders/{id}` |
| `create_purchase_order` | Create a new purchase order | `POST /purchase-orders/` |
| `update_purchase_order` | Update a purchase order | `PUT /purchase-orders/{id}` |

### Inventory Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_inventory_movements` | List inventory movements | `GET /inventory-movements/` |
| `create_inventory_movement` | Record a stock transfer | `POST /inventory-movements/` |

### Client & Supplier Tools

| Tool | Description | API |
|------|-------------|-----|
| `list_clients` | List all clients/customers | `GET /clients/` |
| `get_client` | Get a specific client | `GET /clients/{id}` |
| `create_client` | Create a new client | `POST /clients/` |
| `list_suppliers` | List all suppliers | `GET /suppliers/` |
| `get_supplier` | Get a specific supplier | `GET /suppliers/{id}` |
| `create_supplier` | Create a new supplier | `POST /suppliers/` |

---

## Tool Input/Output Contracts

### `list_production_orders`
**Input**: `page?: int, page_size?: int, code?: str, due_date_before?: str`
**Output**: Paginated list of production order objects

### `create_production_order`
**Input**:
```json
{
  "code": "PO-2024-001",
  "product_id": "PROD-123",
  "quantity": 100,
  "due_date": "2024-12-31T00:00:00Z",
  "notes": "Optional notes"
}
```
**Output**: Created production order

### `activate_production_order`
**Input**: `order_id: str`
**Output**: `{ success: bool, status: str }`

### `update_product_bom`
**Input**:
```json
{
  "product_id": "PROD-123",
  "bom_items": [
    { "component_id": "COMP-001", "quantity": 2, "unit": "pcs" }
  ]
}
```
**Output**: Updated BOM confirmation

### `create_inventory_movement`
**Input**:
```json
{
  "product_id": "PROD-123",
  "quantity": 50,
  "from_location": "Warehouse A",
  "to_location": "Production Floor",
  "movement_date": "2024-01-15T08:00:00Z"
}
```
**Output**: Created movement record

---

## Error Handling

| HTTP Code | Meaning | Behavior |
|-----------|---------|----------|
| 400 | Invalid request | Return validation details to LLM |
| 401 | Token expired | Auto-refresh token and retry once |
| 403 | Forbidden (gateway secret) | Reject |
| 404 | Resource not found | Return descriptive message |
| 429 | Rate limit exceeded | Retry after `Retry-After` seconds |
| 500 | Fusion Operations error | Surface upstream error |

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FUSION_OPS_API_KEY` | Yes | Fusion Operations API key |
| `FUSION_OPS_API_SECRET` | Yes | Fusion Operations API secret |
| `ADS_GATEWAY_SECRET` | Prod | x-ads-gateway-secret value |
| `DEV_MODE` | No | `true` to bypass gateway secret validation |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING` |

### Apigee Proxy Config (api_spec.yaml)

```yaml
title: Fusion Operations MCP Server
name: fusion-operations-mcp
enable-mcp: true
add-oxygen-profile: false
base_path: /fusion-operations-mcp
paths:
  /mcp:
    post: {}
targets:
  - url: http://<internal-alb-url>
```

---

## Webhook Support (Inbound, Phase 2)

Fusion Operations supports 36 webhook event types. A future `/webhooks` endpoint on this server can receive and surface events as MCP notifications:

- `production_order.created` / `updated` / `completed`
- `inventory_movement.created`
- `sales_order.created` / `updated`
- `downtime.started` / `ended`

Webhooks use HMAC-SHA1 signature verification.

---

## Local Dev Quick Start

```bash
cd fusion-operations-mcp
uv sync
cp .env.example .env
# fill in FUSION_OPS_API_KEY, FUSION_OPS_API_SECRET

uv run python -m src.server --disable-auth

claude mcp add --transport http \
  --client-id {YOUR_CLIENT_ID} --client-secret {YOUR_CLIENT_SECRET} \
  --callback-port 8181 \
  fusion-operations-mcp http://localhost:8001/mcp
```

---

## Future Tools (Phase 2)

Planned tools for PLM↔MES data flow:

- `sync_product_from_plm` — Pull a released BOM from Fusion Manage and create/update a product in Fusion Operations
- `create_production_order_from_sales_order` — Generate PO from a Fusion Manage sales item
- `report_production_actuals_to_plm` — Push production record data back to a Fusion Manage item
- `get_production_status_for_item` — Given a PLM item number, find its current production order status
