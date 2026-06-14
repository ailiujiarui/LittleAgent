$ErrorActionPreference = "Stop"

$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Write-Error "Missing $composeFile. Cannot stop NapCat."
}

docker compose -f $composeFile stop --timeout 60
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "NapCat stopped gracefully."
Write-Host "Do not use docker kill. Do not remove docker/napcat/qq-config."
