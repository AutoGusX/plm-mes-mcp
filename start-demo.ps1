# ==============================================================================
# start-demo.ps1  —  Single-command demo startup
#
# Usage (from any directory):
#   powershell -ExecutionPolicy Bypass -File ".\start-demo.ps1"
#
# What it does:
#   1. Refreshes the PLM token (expires every hour)
#   2. Clears any stale processes on ports 8001 and 8003
#   3. Kills any leftover mqtt_subscriber processes
#   4. Starts PLM MCP (:8003), MES MCP (:8001), and the MQTT subscriber
#      each in its own terminal window
#   5. Health-checks the MCP servers before exiting
# ==============================================================================

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot   # repo root = wherever this script lives (portable across machines)

Write-Host ""
Write-Host "=== Demo startup ===" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 1. Refresh PLM token
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[1/4] Refreshing PLM token..." -ForegroundColor Yellow
Push-Location "$Root\fusion-manage-mcp"
uv run python refresh-token.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Token refresh failed. Run get-token.py for a full OAuth flow." -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# ------------------------------------------------------------------------------
# 2. Clear stale port holders (8001, 8003)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/4] Clearing ports 8001 and 8003..." -ForegroundColor Yellow
foreach ($port in @(8001, 8003)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "  Killed PID $($conn.OwningProcess) on port $port"
    } else {
        Write-Host "  Port $port is free"
    }
}

# ------------------------------------------------------------------------------
# 3. Kill stale mqtt_subscriber processes
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] Clearing stale MQTT subscriber processes..." -ForegroundColor Yellow
$mqttProcs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*mqtt_subscriber*" }
if ($mqttProcs) {
    foreach ($proc in $mqttProcs) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  Killed PID $($proc.ProcessId) (mqtt_subscriber)"
    }
} else {
    Write-Host "  No stale subscriber processes found"
}

# Also remove a stale PID file if present
$pidFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "quality-monitor.pid")
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force
    Write-Host "  Removed stale PID file"
}

# ------------------------------------------------------------------------------
# 4. Start services (each in its own window)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] Starting services..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root\fusion-manage-mcp'; `$env:PORT='8003'; uv run python -m src.server --disable-auth"
) -WindowStyle Normal
Write-Host "  PLM MCP starting on :8003"

Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root\fusion-operations-mcp'; uv run python -m src.server --disable-auth"
) -WindowStyle Normal
Write-Host "  MES MCP starting on :8001"

Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root\quality-monitor'; .\.venv\Scripts\python mqtt_subscriber.py"
) -WindowStyle Normal
Write-Host "  MQTT subscriber starting..."

# ------------------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "Waiting for MCP servers to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$plm_ok = $false
$mes_ok = $false

try {
    $r = Invoke-WebRequest -Uri "http://localhost:8003/mcp" -Method POST `
        -ContentType "application/json" -Body "{}" -UseBasicParsing `
        -ErrorAction SilentlyContinue
    $plm_ok = $true
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ge 400) { $plm_ok = $true }
}

try {
    $r = Invoke-WebRequest -Uri "http://localhost:8001/mcp" -Method POST `
        -ContentType "application/json" -Body "{}" -UseBasicParsing `
        -ErrorAction SilentlyContinue
    $mes_ok = $true
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ge 400) { $mes_ok = $true }
}

Write-Host ""
Write-Host "=== Status ===" -ForegroundColor Cyan
Write-Host "  PLM MCP  :8003  $(if ($plm_ok) { '✓ ready' } else { '? check window' })"
Write-Host "  MES MCP  :8001  $(if ($mes_ok) { '✓ ready' } else { '? check window' })"
Write-Host "  MQTT subscriber  — check its window for 'Subscribed to topic'"
Write-Host ""
Write-Host "MCP endpoints:"
Write-Host "  http://localhost:8003/mcp"
Write-Host "  http://localhost:8001/mcp"
Write-Host ""
