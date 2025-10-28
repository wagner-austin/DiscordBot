param()
$ErrorActionPreference = 'Stop'

Write-Host "[stop] Stopping containers..."
docker compose down --remove-orphans
Write-Host "[stop] Done."

