param()
$ErrorActionPreference = 'Stop'

Write-Host "[clean] Stopping and removing containers + volumes..."
docker compose down -v --remove-orphans

Write-Host "[clean] Removing image 'clubbot:latest' if present..."
try { docker image rm -f clubbot:latest | Out-Null } catch { }

Write-Host "[clean] Pruning dangling images and unused volumes..."
docker image prune -f | Out-Null
docker volume prune -f | Out-Null

Write-Host "[clean] Rebuilding stack from scratch..."
docker compose build --no-cache
docker compose up -d
Write-Host "[clean] Done."

