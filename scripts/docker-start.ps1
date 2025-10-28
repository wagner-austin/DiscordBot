param()
$ErrorActionPreference = 'Stop'

Write-Host "[start] Building and starting containers..."
docker compose up -d --build
Write-Host "[start] Done. Current status:"
docker compose ps

