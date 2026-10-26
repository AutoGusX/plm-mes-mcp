# Fusion Manage REST API Reference

> **Version**: v3 (primary) · v1 (search, reports, workflow history)
> **Base URL v3**: `https://{tenant}.autodeskplm.com/api/v3/`
> **Base URL v1**: `https://{tenant}.autodeskplm360.net/api/rest/v1/`

---

## Authentication

### 3-Legged OAuth (v3)

All v3 endpoints require a user-level Bearer token obtained via APS OAuth 2.0 Authorization Code flow.

**Authorize**
```
GET https://developer.api.autodesk.com/authentication/v2/authorize
  ?response_type=code
  &client_id={CLIENT_ID}
  &redirect_uri={CALLBACK_URL}
  &scope=data:read data:write
```

**Token Exchange**
```
POST https://developer.api.autodesk.com/authentication/v2/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code={auth_code}
&client_id={CLIENT_ID}
&client_secret={CLIENT_SECRET}
&redirect_uri={CALLBACK_URL}
```

**Response**
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJ..."
}
```

**Token Refresh**
```
POST https://developer.api.autodesk.com/authentication/v2/token
grant_type=refresh_token&refresh_token={REFRESH_TOKEN}&client_id=...&client_secret=...
```

Tokens expire in **60 minutes**; refresh tokens valid **15 days**.

### Required Headers (v3)

```http
Authorization: Bearer {access_token}
x-tenant: {tenant_name}
Accept: application/json
Content-Type: application/json
```

### Authentication (v1 — Basic)

```http
Authorization: Basic base64({username}:{password})
```

---

## Pagination

All list endpoints support:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | 1 | Page number |
| `size` | 100 | Items per page |

---

## Workspaces

### List Workspaces
```
GET /api/rest/v1/workspaces
```

**Response 200**
```json
{
  "workspaces": [
    {
      "id": 2,
      "category": "Items",
      "label": "Parts & Assemblies",
      "uri": "/api/rest/v1/workspaces/2"
    }
  ]
}
```

---

### Get Workspace Sections (v3)
```
GET /api/v3/workspaces/{wsId}/sections
```

Returns the section/field structure of a workspace — useful for knowing which field IDs to use when creating or updating items.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `wsId` | int | Workspace ID |

**Response 200**
```json
{
  "sections": [
    {
      "id": 1,
      "label": "General",
      "fields": [
        { "id": "TITLE", "label": "Title", "type": "text", "required": true },
        { "id": "DESCRIPTION", "label": "Description", "type": "textarea" }
      ]
    }
  ]
}
```

---

## Items

### List Workspace Items
```
GET /api/rest/v1/workspaces/{id}/items
```

**Query Parameters**

| Param | Default | Description |
|-------|---------|-------------|
| `page` | 1 | Page number |
| `size` | 100 | Items per page |
| `includeRelationships` | true | Include relationship data |

**Response 200**
```json
{
  "list": [
    {
      "dmsId": 344,
      "workspaceId": 2,
      "title": "Widget Assembly",
      "uri": "/api/rest/v1/workspaces/2/items/344",
      "fields": [
        { "fieldId": "TITLE", "value": "Widget Assembly" },
        { "fieldId": "ITEM_NUMBER", "value": "ASSY-001" }
      ],
      "relationships": []
    }
  ],
  "total": 1245,
  "page": 1,
  "pageSize": 100
}
```

---

### Get Workspace Item (v3)
```
GET /api/v3/workspaces/{wsId}/items/{itemId}
```

**Response 200** — Full item object with all sections and field values.

---

### Search Workspace Items
```
POST /api/rest/v1/workspaces/{id}/items/search
```

**Request Body**
```json
{
  "searchDefinition": {
    "pageNo": 1,
    "pageSize": 50,
    "logicClause": "AND",
    "fields": [
      {
        "fieldID": "TITLE",
        "fieldTypeID": "text"
      }
    ],
    "sorting": [
      {
        "fieldID": "TITLE",
        "sortOrder": "ASC"
      }
    ],
    "filteringCriteria": [
      {
        "filterType": { "filterID": "CONTAINS" },
        "filterValue": "Widget"
      }
    ]
  }
}
```

**Response 200**
```json
{
  "reportResult": {
    "totalResultCount": 12,
    "columnKey": ["TITLE", "ITEM_NUMBER", "STATUS"],
    "row": [
      { "cells": ["Widget Assembly", "ASSY-001", "Released"] }
    ]
  }
}
```

---

### Create Workspace Item (v3)
```
POST /api/v3/workspaces/{wsId}/items
```

**Request Body**
```json
{
  "sections": [
    {
      "fields": [
        {
          "__self__": "/api/v3/workspaces/2/views/1/fields/TITLE",
          "value": "My New Part",
          "title": "Title"
        },
        {
          "__self__": "/api/v3/workspaces/2/views/1/fields/DESCRIPTION",
          "value": "Part description here"
        }
      ]
    }
  ]
}
```

**Response 201**
```json
{
  "id": 512,
  "uri": "/api/v3/workspaces/2/items/512",
  "title": "My New Part"
}
```

---

### Update Workspace Item (v3)
```
PATCH /api/v3/workspaces/{wsId}/items/{itemId}
```

Same body structure as create. Only include fields to be updated.

**Response 200** — Updated item object.

---

## Attachments

### List Item Attachments
```
GET /api/rest/v1/workspaces/{id}/items/{dmsID}/attachments
```

**Response 200**
```json
[
  {
    "uri": "/api/rest/v1/workspaces/24/items/344/attachments/1",
    "fileID": 1,
    "fileName": "drawing.pdf",
    "fileSize": 204800,
    "fileVersion": 3,
    "fileStatus": "Active",
    "createdBy": "john.smith@company.com",
    "createdDate": "2024-01-15T10:30:00Z"
  }
]
```

---

### Get Specific Attachment
```
GET /api/rest/v1/workspaces/{id}/items/{dmsID}/attachments/{fieldID}
```

---

## Workflow

### Get Workflow History
```
GET /api/rest/v1/workspaces/{id}/items/{dmsID}/workflows/history
```

**Response 200**
```json
{
  "historySteps": [
    {
      "step": 1,
      "transitionName": "Submit for Review",
      "actualUserDisplayName": "Jane Doe",
      "actualUserID": "jdoe@company.com",
      "timestampFormatted": "2024-01-10 09:15:00",
      "comments": "Ready for review"
    },
    {
      "step": 2,
      "transitionName": "Approve",
      "actualUserDisplayName": "Bob Smith",
      "actualUserID": "bsmith@company.com",
      "timestampFormatted": "2024-01-12 14:30:00",
      "comments": "LGTM"
    }
  ]
}
```

---

### Transition Item Workflow
```
PUT /api/rest/v1/workspaces/{id}/items/{dmsID}/workflows/transitions/{transitionID}
```

**Request Body**
```json
{
  "workflowStep": 3,
  "workflowComments": "Approved after review"
}
```

> `workflowStep` must be current step + 1.

**Response 204** — No content on success.

---

## Reports

### Get Report
```
GET /api/rest/v1/reports/{reportID}
```

**Response 200**
```json
{
  "reportDefinition": {
    "id": 71,
    "name": "Released Parts Report",
    "description": "All parts in Released state"
  },
  "reportResult": {
    "totalResultCount": 87,
    "columnKey": ["ITEM_NUMBER", "TITLE", "RELEASE_DATE"],
    "row": [
      { "cells": ["PART-001", "Bracket Assembly", "2024-01-01"] }
    ]
  }
}
```

---

## Field Discovery

To find available field IDs for a workspace:

```
GET /api/rest/v1/workspaces/{id}/metafields/assigned/
```

Returns all field definitions including `fieldID`, `fieldTypeID`, `label`, `required`, and validation rules.

---

## Error Responses

All errors follow this structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Field TITLE is required",
    "details": []
  }
}
```

| HTTP | Code | Description |
|------|------|-------------|
| 400 | `VALIDATION_ERROR` | Missing or invalid field values |
| 401 | `UNAUTHORIZED` | Invalid or expired token |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Workspace, item, or attachment not found |
| 409 | `CONFLICT` | Workflow step conflict |
| 500 | `SERVER_ERROR` | Fusion Manage internal error |

---

## Key Tenant URL Pattern

| Environment | URL |
|-------------|-----|
| Production (v3) | `https://{tenant}.autodeskplm.com/api/v3/` |
| Production (v1) | `https://{tenant}.autodeskplm360.net/api/rest/v1/` |

The tenant name is the subdomain of your Fusion Manage instance.
