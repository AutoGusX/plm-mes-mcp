# PLM & MES MCP Playground

Python playground with two HTTP MCP servers that expose Autodesk **Fusion Manage (PLM)** and
**Fusion Operations (MES)** to an AI agent, plus a **quality-monitor** that reacts to MES quality
events and a set of demo/analysis scripts. It powers the "From Integration to Orchestration"
cross-system demos (change impact analysis, quality RCA, work-instruction generation).
Unofficial/personal — not an Autodesk product.

- Runtime: Python 3.11+, `mcp==1.26.0` (FastMCP), `httpx`, `uv`-managed venvs. Windows/PowerShell.
- Agent wiring: both servers are registered as native HTTP MCP tools in `.mcp.json`.

## Components
- **fusion-manage-mcp** (PLM, Fusion Manage v3 API) — port **8003**, endpoint `/mcp`. Tenant
  set via `FUSION_MANAGE_TENANT`. Auth: APS 3-legged OAuth token in `FUSION_MANAGE_TOKEN` (expires hourly).
  Src: `fusion-manage-mcp/src/` (`server.py`, `client.py`, `auth.py`, `tools/`, `workspaces.py`).
- **fusion-operations-mcp** (MES, Fusion Operations v1 API) — port **8001**, endpoint `/mcp`.
  Auth: Fusion Ops `API_KEY:API_SECRET` → 2 hr bearer token (separate model from PLM — keep them
  separate). Src: `fusion-operations-mcp/src/`.
- **quality-monitor** — standalone always-on agent. `mqtt_subscriber.py` subscribes to the Tandem
  Connect MQTT broker (`AgenticAI/#`, MQTTS :8883), threshold-checks quality events, and writes
  them to `%TEMP%\quality-alerts.jsonl`. `rca.py` runs RCA against the PLM MCP, `slack_notifier.py`
  posts to Slack. Only **one** subscriber may run (`clean_session=False`) or it connect/disconnect loops.
- **Demo scripts** (repo root): `cia-co000463.py` / `cia-co000496.py` (change impact analysis),
  `cia-pptx-*.py` (deck generation), `check-bom.py`, `discover-ops-bom.py`, `sync-chiller.py`.
  See `use-cases.md` for the five orchestration scenarios.

## How to run
`start-demo.ps1` does everything: refresh PLM token → clear stale ports/subscriber → launch PLM MCP,
MES MCP, and the MQTT subscriber in separate windows → health-check. Prefer it — it cleans up stale
subscribers automatically. (`$Root` auto-resolves via `$PSScriptRoot`, so it runs correctly from
wherever the repo lives — no hardcoded path to maintain.)

Manual (from each server dir, with `uv` installed):
```
# PLM  — refresh token first (expires hourly), then start
cd fusion-manage-mcp;    uv run python refresh-token.py
cd fusion-manage-mcp;    $env:PORT='8003'; uv run python -m src.server --disable-auth
# MES
cd fusion-operations-mcp; uv run python -m src.server --disable-auth
# Quality monitor (its own venv)
cd quality-monitor;      .\.venv\Scripts\python mqtt_subscriber.py
```
Both servers run `--disable-auth` locally (Apigee handles MCP OAuth in the cloud deployment). If
`get-token.py`/`refresh-token.py` reports no refresh token, run the full browser flow via `get-token.py`.

## Conventions & gotchas
- **FastMCP host/port go in the constructor, NOT `run()`.** `mcp = FastMCP(..., host=, port=,
  streamable_http_path="/mcp")` then `mcp.run(transport="streamable-http")` with no args. On
  `mcp==1.26.0` passing host/port to `run()` is ignored/errors — this cost real debugging time.
- **ALWAYS POST to Slack after every quality-event RCA.** Slack delivery is a required step of the
  RCA workflow, not optional (it was silently skipped once). Payload uses three fields — `Message`,
  `Related_COs`, `Related_Productions` — and must be **plain ASCII only** (no Unicode arrows, em
  dashes, or bullets). Webhook + shape live in `quality-monitor/slack_notifier.py` / `.env`.
- **PLM token = the hard dependency.** It expires hourly; 401s from PLM calls almost always mean an
  expired token — refresh and restart the PLM server. For browser/content-script contexts the current
  way to mint a Fusion Manage bearer token is a same-origin `GET /api/v3/token` with
  `credentials:'include'` (the HttpOnly `JSESSIONID` cookie is auto-attached); it is no longer
  reliably in `localStorage['O2AuthToken']`.
- **Key workspace IDs:** Items/parts/assemblies **and** Change Orders both live in **ws 57**. Related
  COs for a parts item come via **views/11**. Fusion Operations products are keyed by `code` (not id).
- **Ports:** PLM 8003, MES 8001, quality-monitor local webhook 8002, OAuth callback 3001.

## Security
⚠ The APS `CLIENT_ID` is currently **hardcoded** in `fusion-manage-mcp/get-token.py` and
`refresh-token.py`. It should be moved to `.env` (e.g. `APS_CLIENT_ID`) and read via `dotenv`. Do
not commit real tokens or the MQTT/Slack credentials.

## Git hygiene
Gitignored: all `.env` files (PLM, MES, quality-monitor), `.venv/`/`venv/`, `.claude/`, and generated
`*.pptx` demo decks (regenerable from the `cia-pptx-*.py` scripts). `.env.example` files are committed
as templates.
</content>
</invoke>
