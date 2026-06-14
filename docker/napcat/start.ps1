$ErrorActionPreference = "Stop"

$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Write-Error "Missing $composeFile. Create the local NapCat compose file first."
}

docker compose -f $composeFile up -d
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "NapCat started."
Write-Host "Keep docker/napcat/qq-config. Removing it will require QR login again."
