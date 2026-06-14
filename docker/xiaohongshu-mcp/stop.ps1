$ErrorActionPreference = "Stop"

$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Write-Error "Missing $composeFile. Cannot stop xiaohongshu-mcp."
}

docker compose -f $composeFile stop --timeout 60
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "xiaohongshu-mcp stopped gracefully."
Write-Host "Do not remove docker/xiaohongshu-mcp/data unless you want to login again."
