$ErrorActionPreference = "Stop"

$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Write-Error "Missing $composeFile. Copy docker-compose.example.yml to docker-compose.yml first."
}

docker compose -f $composeFile up -d
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "xiaohongshu-mcp started."
Write-Host "MCP endpoint: http://localhost:18060/mcp"
Write-Host "Cookies are stored under docker/xiaohongshu-mcp/data; keep this directory to avoid repeated login."
