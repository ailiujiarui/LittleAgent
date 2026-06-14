$ErrorActionPreference = "Stop"

$containerName = "mini-agent-xiaohongshu-mcp"

$container = docker ps -a --filter "name=^/$containerName$" --format "{{.Names}} {{.Status}}"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($container)) {
    Write-Host "xiaohongshu-mcp container does not exist."
} else {
    Write-Host "xiaohongshu-mcp container status: $container"
}

try {
    $body = @{
        jsonrpc = "2.0"
        method = "initialize"
        params = @{
            protocolVersion = "2025-03-26"
            capabilities = @{}
            clientInfo = @{
                name = "mini-agent-status"
                version = "0.1.0"
            }
        }
        id = 1
    } | ConvertTo-Json -Depth 5
    $response = Invoke-WebRequest `
        -Uri "http://localhost:18060/mcp" `
        -Method Post `
        -ContentType "application/json" `
        -Headers @{ Accept = "application/json, text/event-stream" } `
        -Body $body `
        -TimeoutSec 5 `
        -UseBasicParsing
    Write-Host "MCP endpoint reachable: HTTP $($response.StatusCode)"
} catch {
    Write-Host "MCP endpoint not reachable: $($_.Exception.Message)"
}
