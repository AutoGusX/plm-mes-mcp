# PLM + MES MCP servers

Two [Model Context Protocol](https://modelcontextprotocol.io) servers that let an AI agent work across
**Autodesk Fusion Manage** (PLM) and **Fusion Operations** (MES), plus a quality monitor that reacts to
shop-floor events.

| Component | What it does | Port |
|---|---|---|
| `fusion-manage-mcp` | Fusion Manage v3 API: workspaces, items, BOMs, attachments, workflows, reports, cross-system tools (24 tools) | 8003 |
| `fusion-operations-mcp` | Fusion Operations v1 API: production orders, products, sales/purchase orders, inventory, clients, suppliers, cross-system tools (31 tools) | 8001 |
| `quality-monitor` | Subscribes to an MQTT broker, threshold-checks quality events, runs root-cause analysis through the MCP servers, and posts to Slack | 8002 (webhook) |

Cross-system scenarios (change impact analysis, work instruction generation, root cause analysis,
supplier exception handling) are described in [`use-cases.md`](use-cases.md).

> This is an independent, unofficial project. It is not affiliated with or supported by Autodesk. You need
> your own Fusion Manage tenant and Fusion Operations account.

## Bring your own tenant and keys

Nothing in this repo is tied to a specific tenant. Every credential lives in a gitignored `.env` file.

1. Install [uv](https://docs.astral.sh/uv/) and Python 3.11+.
2. For each of `fusion-manage-mcp`, `fusion-operations-mcp` and `quality-monitor`, copy `.env.example` to
   `.env` and fill it in.
   - Fusion Manage needs your tenant name (`FUSION_MANAGE_TENANT`) and an APS app (`APS_CLIENT_ID`). Run
     `uv run python get-token.py` to sign in and save a token. It expires hourly; `refresh-token.py` renews it.
   - Fusion Operations needs `FUSION_OPS_API_KEY` and `FUSION_OPS_API_SECRET`.
   - `quality-monitor` needs your MQTT broker details and, optionally, a Slack workflow URL.
3. Start the servers from their folders:
   ```
   cd fusion-manage-mcp      && PORT=8003 uv run python -m src.server --disable-auth
   cd fusion-operations-mcp  && PORT=8001 uv run python -m src.server --disable-auth
   ```
   On Windows, `start-demo.ps1` starts everything in separate windows and health-checks the servers.
4. Point your MCP client at them. `.mcp.json` has a ready-made example using `http://localhost:8003/mcp`
   and `http://localhost:8001/mcp`.

`--disable-auth` is for local use only. In a shared deployment, put the servers behind a gateway that
handles OAuth and sets `ADS_GATEWAY_SECRET`. See each server's `spec.md`.

## Workspace IDs

`fusion-manage-mcp/src/workspaces.py` maps workspace names to the IDs in the original author's tenant.
Workspace IDs differ per tenant, so update that file to match yours. The `cia-*.py`, `check-bom.py`,
`sync-chiller.py` and `discover-ops-bom.py` scripts are demo helpers built around that sample data.

## Security notes

- Never commit `.env`. It is gitignored, as are virtualenvs and local Claude state.
- Treat any token or secret you paste into an issue or pull request as compromised.
