# Fusion Operations REST API Reference

> **Version**: v1
> **Base URL**: `https://fusionoperations.autodesk.com/api/v1/`
> **Auth**: Token via `?access_token={token}` on all requests
> **Rate Limit**: 120 requests/minute/company
> **Date Format**: ISO 8601 — `YYYY-MM-DDTHH:MM:SSZ`

---

## Authentication

### Step 1 — Obtain Token

```
GET /api/v1/authorization
Authorization: Basic base64(API_KEY:API_SECRET)
```

**Response 200**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
  "expires_in": 7200
}
```

- Tokens are valid for **2 hours**
- On 401, re-authenticate to get a new token

### Step 2 — Use Token

Append to every request:
```
GET /api/v1/production-orders/?access_token={token}
```

### Token Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/authorization` | Check/retrieve current token |
| `POST` | `/api/v1/authorization` | Create new token |
| `DELETE` | `/api/v1/authorization` | Revoke token |

---

## Pagination

All list endpoints accept:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | 1 | Page number |
| `page-size` | 25 | Results per page |
| `sort` | `id` | Sort field: `id`, `code`, `created_at` |
| `order` | `asc` | Sort direction: `asc`, `desc` |

**Response envelope**
```json
{
  "count": 250,
  "next": "/api/v1/production-orders/?page=2&access_token=...",
  "previous": null,
  "results": [...]
}
```

---

## Production Orders

### List Production Orders
```
GET /api/v1/production-orders/
```

**Query Filters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | string | Filter by order code |
| `due-date-before` | ISO date | Orders due before date |
| `due-date-after` | ISO date | Orders due after date |
| `status` | string | Filter by status |

**Response 200**
```json
{
  "count": 15,
  "results": [
    {
      "id": "PO-001",
      "code": "PO-2024-001",
      "product": { "id": "PROD-123", "code": "WIDGET-A" },
      "quantity": 100,
      "produced_quantity": 45,
      "status": "In Progress",
      "due_date": "2024-12-31T00:00:00Z",
      "created_at": "2024-11-01T08:00:00Z",
      "notes": ""
    }
  ]
}
```

---

### Get Production Order
```
GET /api/v1/production-orders/{id}
```

**Response 200** — Full production order object (same structure as list item).

---

### Create Production Order
```
POST /api/v1/production-orders/
Content-Type: application/json
```

**Request Body**
```json
{
  "code": "PO-2024-002",
  "product": { "id": "PROD-123" },
  "quantity": 200,
  "due_date": "2024-12-31T00:00:00Z",
  "notes": "Rush order"
}
```

**Response 201** — Created production order.

---

### Update Production Order
```
PUT /api/v1/production-orders/{id}
```

**Request Body** — Same as create, full replacement.

**Response 200** — Updated object.

---

### Delete Production Order
```
DELETE /api/v1/production-orders/{id}
```

**Response 204** — No content.

---

### Activate Production Order
```
POST /api/v1/production-orders/{id}/activate
```

Releases the production order to the shop floor.

**Response 200**
```json
{ "status": "Active" }
```

---

### Notify Production Problem
```
POST /api/v1/production-orders/{id}/notify
Content-Type: application/json
```

**Request Body**
```json
{
  "problem_type": "Quality Issue",
  "description": "Dimension out of tolerance on batch 3",
  "severity": "High"
}
```

**Response 200** — Problem record created.

---

### Production Order Files
```
POST   /api/v1/production-orders/{id}/files       — Upload file
GET    /api/v1/production-orders/{id}/files/{fid} — Download file
PUT    /api/v1/production-orders/{id}/files/{fid} — Update file metadata
DELETE /api/v1/production-orders/{id}/files/{fid} — Delete file
```

File uploads use `Content-Type: multipart/form-data`.

---

## Products

### List Products
```
GET /api/v1/products/
```

**Response 200**
```json
{
  "count": 88,
  "results": [
    {
      "id": "PROD-123",
      "code": "WIDGET-A",
      "description": "Standard Widget Assembly",
      "unit": "pcs",
      "bom": []
    }
  ]
}
```

---

### Get Product
```
GET /api/v1/products/{id}
```

---

### Create Product
```
POST /api/v1/products/
```

**Request Body**
```json
{
  "code": "WIDGET-B",
  "description": "Heavy Duty Widget",
  "unit": "pcs"
}
```

**Response 201** — Created product.

---

### Update Product
```
PUT /api/v1/products/{id}
```

---

### Update Product BOM
```
POST /api/v1/products/{id}/bom
Content-Type: application/json
```

**Request Body**
```json
{
  "bom_items": [
    {
      "component": { "id": "COMP-001", "code": "BOLT-M6" },
      "quantity": 4,
      "unit": "pcs"
    },
    {
      "component": { "id": "COMP-002", "code": "BRACKET-L" },
      "quantity": 1,
      "unit": "pcs"
    }
  ]
}
```

**Response 200** — Updated BOM.

---

### Product Files
```
POST /api/v1/products/{id}/files  — Upload file (multipart/form-data)
```

---

## Sales Orders

### List Sales Orders
```
GET /api/v1/sales-orders/
```

**Query Filters**: `code`, `client-id`, `due-date-before`, `due-date-after`

**Response 200**
```json
{
  "results": [
    {
      "id": "SO-001",
      "code": "SO-2024-001",
      "client": { "id": "CLIENT-1", "name": "Acme Corp" },
      "items": [
        { "product": { "id": "PROD-123" }, "quantity": 50 }
      ],
      "due_date": "2024-12-15T00:00:00Z",
      "shipping_address": "123 Main St, Springfield"
    }
  ]
}
```

---

### Get Sales Order
```
GET /api/v1/sales-orders/{id}
```

---

### Create Sales Order
```
POST /api/v1/sales-orders/
```

**Request Body**
```json
{
  "code": "SO-2024-002",
  "client": { "id": "CLIENT-1" },
  "items": [
    { "product": { "id": "PROD-123" }, "quantity": 100 }
  ],
  "due_date": "2025-01-31T00:00:00Z",
  "shipping_address": "456 Oak Ave, Shelbyville"
}
```

---

### Update Sales Order
```
PUT /api/v1/sales-orders/{id}
```

---

### Delete Sales Order
```
DELETE /api/v1/sales-orders/{id}
```

**Response 204**

---

## Purchase Orders

### List Purchase Orders
```
GET /api/v1/purchase-orders/
```

**Response 200**
```json
{
  "results": [
    {
      "id": "PUR-001",
      "code": "PUR-2024-001",
      "supplier": { "id": "SUP-1", "name": "Parts Inc" },
      "items": [
        { "product": { "id": "COMP-001" }, "quantity": 500 }
      ],
      "expected_date": "2024-11-30T00:00:00Z"
    }
  ]
}
```

---

### Get Purchase Order
```
GET /api/v1/purchase-orders/{id}
```

---

### Create Purchase Order
```
POST /api/v1/purchase-orders/
```

**Request Body**
```json
{
  "code": "PUR-2024-002",
  "supplier": { "id": "SUP-1" },
  "items": [
    { "product": { "id": "COMP-001" }, "quantity": 1000 }
  ],
  "expected_date": "2025-01-15T00:00:00Z"
}
```

---

### Update Purchase Order
```
PUT /api/v1/purchase-orders/{id}
```

---

## Inventory Movements

### List Inventory Movements
```
GET /api/v1/inventory-movements/
```

**Response 200**
```json
{
  "results": [
    {
      "id": "INV-001",
      "product": { "id": "PROD-123" },
      "quantity": 50,
      "from_location": "Warehouse A",
      "to_location": "Production Floor",
      "movement_date": "2024-01-15T08:00:00Z",
      "created_by": "operator@company.com"
    }
  ]
}
```

---

### Create Inventory Movement
```
POST /api/v1/inventory-movements/
```

**Request Body**
```json
{
  "product": { "id": "PROD-123" },
  "quantity": 50,
  "from_location": "Warehouse A",
  "to_location": "Production Floor",
  "movement_date": "2024-01-15T08:00:00Z",
  "notes": "Transfer for PO-2024-001"
}
```

**Response 201** — Created movement record.

---

## Clients

### List Clients
```
GET /api/v1/clients/
```

**Response 200**
```json
{
  "results": [
    {
      "id": "CLIENT-1",
      "name": "Acme Corp",
      "email": "orders@acme.com",
      "phone": "+1-555-0100",
      "address": "123 Main St, Springfield"
    }
  ]
}
```

---

### Get Client
```
GET /api/v1/clients/{id}
```

---

### Create Client
```
POST /api/v1/clients/
```

**Request Body**
```json
{
  "name": "Globex Corp",
  "email": "purchasing@globex.com",
  "phone": "+1-555-0200",
  "address": "742 Evergreen Terrace"
}
```

---

### Update / Delete Client
```
PUT    /api/v1/clients/{id}
DELETE /api/v1/clients/{id}
```

---

## Suppliers

Same CRUD pattern as Clients:

```
GET    /api/v1/suppliers/
GET    /api/v1/suppliers/{id}
POST   /api/v1/suppliers/
PUT    /api/v1/suppliers/{id}
DELETE /api/v1/suppliers/{id}
```

---

## Webhooks

### Supported Event Types (36 total)

**Production Orders**: `production_order.created`, `production_order.updated`, `production_order.activated`, `production_order.completed`, `production_order.deleted`

**Sales Orders**: `sales_order.created`, `sales_order.updated`, `sales_order.deleted`

**Purchase Orders**: `purchase_order.created`, `purchase_order.updated`, `purchase_order.deleted`

**Products**: `product.created`, `product.updated`, `product.deleted`, `product.bom_updated`

**Inventory**: `inventory_movement.created`

**Clients/Suppliers**: `client.created`, `client.updated`, `supplier.created`, `supplier.updated`

**Downtime**: `downtime.started`, `downtime.ended`

**Punch Clock**: `punch_clock.in`, `punch_clock.out`

**Lots**: `lot.created`, `lot.updated`

### Webhook Payload Structure
```json
{
  "event": "production_order.created",
  "timestamp": "2024-01-15T08:00:00Z",
  "data": { ... },
  "signature": "sha1=abc123..."
}
```

### Signature Verification (HMAC-SHA1)
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload, hashlib.sha1).hexdigest()
assert f"sha1={expected}" == request.headers["X-Hub-Signature"]
```

---

## Error Responses

All errors return:
```json
{
  "error": "Descriptive error message",
  "invalid_fields": ["field_name"]
}
```

| HTTP | Meaning |
|------|---------|
| 400 | Invalid request body or field values |
| 401 | Missing or expired access token |
| 404 | Resource not found |
| 429 | Rate limit exceeded — check `Retry-After` header |
| 500 | Fusion Operations server error |
