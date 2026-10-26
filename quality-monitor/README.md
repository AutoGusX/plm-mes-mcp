# Quality Monitor — Setup & Run Guide

Always-on agent that listens for quality events from Fusion Operations via MQTT,
runs root cause analysis against PLM and MES, and posts alerts to Slack.

---

## Architecture

```
Fusion Operations (cloud)
        │  MQTT publish → AgenticAI/<topic>
        ▼
Autodesk Tandem Connect Broker  (mqtts://... port 8883)
        │  subscribe AgenticAI/#
        ▼
quality-monitor/mqtt_subscriber.py       ← you start this
        │  quality threshold check (waste / rework)
        │  writes alerts to: C:\Users\<you>\AppData\Local\Temp\quality-alerts.jsonl
        │
        ├─ rca.py  →  PLM MCP Server :8003  →  Fusion Manage API
        │             search item + get related COs via views/11
        │
        └─ slack_notifier.py  →  Slack webhook
```

> **mqtt_subscriber.py is the JSONL writer.**
> It is a standalone process — separate from both MCP servers.
> The file `quality-alerts.jsonl` does not exist until the first quality
> threshold is breached and the subscriber receives the MQTT event.
> If the file is missing, check that the subscriber is running and connected,
> not the MCP servers.

> **Only one instance may run at a time.**
> The subscriber uses `client_id="quality-monitor-persistent"` with
> `clean_session=False`. Running multiple instances causes each to
> immediately kick out the others, resulting in a connect/disconnect loop
> where no messages are ever received. Use `start-demo.ps1` to start
> everything cleanly — it kills stale instances automatically.

---

## Ports

| Service                  | Port | Notes                         |
|--------------------------|------|-------------------------------|
| PLM MCP (Fusion Manage)  | 8003 | MCP endpoint: `/mcp`          |
| MES MCP (Fusion Ops)     | 8001 | MCP endpoint: `/mcp`          |
| Quality Monitor webhook  | 8002 | Local test only: `POST /webhooks/production-event` |

---

## Step 1 — Refresh the PLM token

The Fusion Manage token expires every hour. **Do this first, every session.**

```bash
cd "D:/MCP for PLM and MES/fusion-manage-mcp"
uv run python refresh-token.py
```

Expected output:
```
Token refreshed and saved to .env
  expires_in: 3599s (~59 min)
```

> If it fails with "No FUSION_MANAGE_REFRESH_TOKEN", run `get-token.py` instead
> to do the full browser OAuth flow.

---

## Step 2 — Start the MCP servers

Open **two terminals** and run one command in each.

**Terminal A — PLM MCP (Fusion Manage)**
```bash
cd "D:/MCP for PLM and MES/fusion-manage-mcp"
PORT=8003 uv run python -m src.server --disable-auth
```
Ready when you see: `Uvicorn running on http://0.0.0.0:8003`

**Terminal B — MES MCP (Fusion Operations)**
```bash
cd "D:/MCP for PLM and MES/fusion-operations-mcp"
uv run python -m src.server --disable-auth
```
Ready when you see: `Uvicorn running on http://0.0.0.0:8001`

---

## Step 3 — Start the MQTT subscriber

Open a **third terminal**.

```bash
cd "D:/MCP for PLM and MES/quality-monitor"
.venv/Scripts/python mqtt_subscriber.py
```

Expected startup output:
```
Connecting to <broker-host>:8883 as user '<username>'...
Connected to broker <broker-host>:8883
Subscribed to topic: AgenticAI/#
Subscription confirmed — granted QoS: [0]
```

The subscriber is now idle, waiting for incoming MQTT messages.

---

## Step 4 — Connect an agent

Point your AI agent (Claude in Cursor, Claude Desktop, etc.) at both MCP servers
using **Streamable HTTP** transport.

**MCP server URLs:**
```
PLM (Fusion Manage):   http://localhost:8003/mcp
MES (Fusion Ops):      http://localhost:8001/mcp
```

**Example `mcp.json` / `claude_desktop_config.json` entry:**
```json
{
  "mcpServers": {
    "fusion-manage": {
      "url": "http://localhost:8003/mcp"
    },
    "fusion-operations": {
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

---

## MQTT broker configuration

| Setting   | Value                                                                                           |
|-----------|-------------------------------------------------------------------------------------------------|
| URL       | `mqtts://<your-broker-host>` (from your Tandem Connect integration) |
| Port      | `8883` (MQTTS — TLS required)                                                                   |
| Username  | `<your-mqtt-username>` |
| Password  | `<your-mqtt-password>` |
| Topic     | `AgenticAI/#`                                                                                   |

Copy `quality-monitor/.env.example` to `quality-monitor/.env` and fill these in. The `.env` file is gitignored and read automatically at startup.

---

## Quality alert thresholds

Configured in `quality-monitor/.env`:

| Variable               | Default | Meaning                                           |
|------------------------|---------|---------------------------------------------------|
| `WASTE_THRESHOLD`      | `1`     | Alert if `produced-waste` array has ≥ N items     |
| `REWORK_TRIGGERS_ALERT`| `true`  | Alert if `rework: true` on the production event   |

---

## Slack alert payload

Alerts POST to the Slack workflow trigger with three fields:

| Field                 | Content                                                  |
|-----------------------|----------------------------------------------------------|
| `Message`             | Product, operation, order, worker, and trigger reasons   |
| `Related_COs`         | Change Orders linked to the product via PLM views/11     |
| `Related_Productions` | Production order code and consumed raw materials         |

Webhook URL is in `quality-monitor/.env` as `SLACK_WEBHOOK_URL`.

---

## Local test (no MQTT needed)

To fire a test alert and verify Slack end-to-end without waiting for the broker:

```bash
cd "D:/MCP for PLM and MES/quality-monitor"
.venv/Scripts/python -c "
import asyncio
from rca import get_related_cos
from slack_notifier import send_quality_alert

signals = {
    'triggered': True,
    'reasons': [\"1 waste item(s) on operation 'Paint'\"],
    'waste_items': [{'product': {'code': 'YOUR-PART-CODE'}, 'quantity': 2}],
    'rework': False,
    'product': {'id': 123, 'code': 'YOUR-PART-CODE'},
    'operation': 'Paint',
    'order': {'id': 987, 'code': 'YOUR-ORDER-CODE'},
    'worker': 'Worker Name',
    'consumptions': [],
    'event_time': '2026-04-01T10:00:00Z',
}

async def run():
    cos = await get_related_cos('YOUR-PART-CODE')
    print('Related COs:', cos)
    ok = await send_quality_alert(signals, related_cos=cos)
    print('Slack sent:', ok)

asyncio.run(run())
"
```

Replace `YOUR-PART-CODE` with a real part code from your Fusion Manage tenant.

---

## Troubleshooting

**MQTT subscriber exits immediately with `getaddrinfo failed`**
→ DNS for the new broker hasn't propagated yet. Run `nslookup <broker-host>` and
  wait until it returns an IP address, then retry.

**MQTT subscriber connects but immediately disconnects**
→ Port 1883 is blocked on your network. Confirm port 8883 is used (`MQTT_BROKER_PORT=8883` in `.env`).

**RCA returns `PLM item found but could not resolve DMS ID`**
→ The search matched an item but the response shape changed. Check the raw result
  by running `search_items_global` directly against the PLM MCP server.

**RCA returns 403 on `views/11`**
→ The parts workspace item may require a different view number. Verify in the
  Fusion Manage UI which view shows Change Orders for a parts item and update
  `PLM_ITEMS_WS_ID` and the view call in `rca.py` accordingly.

**PLM calls return 401**
→ Token expired. Run `refresh-token.py` and restart the PLM MCP server.
