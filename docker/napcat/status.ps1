$ErrorActionPreference = "Stop"

$containerName = "mini-agent-napcat"

$container = docker ps -a --filter "name=^/$containerName$" --format "{{.Names}} {{.Status}}"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($container)) {
    Write-Host "NapCat container does not exist."
} else {
    Write-Host "NapCat container status: $container"
}

$connections = Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue
if ($connections) {
    Write-Host "OneBot WebSocket connected: $($connections.Count) established connection(s)."
} else {
    Write-Host "OneBot WebSocket not connected: no established connection on port 8765."
}
