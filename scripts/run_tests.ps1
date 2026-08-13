param()

# Start Postgres via docker-compose (requires Docker running)
docker-compose -f (Join-Path $PSScriptRoot '..\docker-compose.yml') up -d

Write-Host "Esperando a que Postgres esté listo..."
Start-Sleep -Seconds 5

# Export environment variables for the test run
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGDATABASE = "eventos"
$env:PGUSER = "eventos"
$env:PGPASSWORD = "eventos"
$env:SECRET_KEY = "test-secret-key-for-usuarios-module"

# Run pytest using the workspace venv python
Start-Process -FilePath "c:/CODIP/back/Eventos-Backend/.venv/Scripts/python.exe" -ArgumentList "-m pytest -q" -NoNewWindow -Wait

# Teardown
docker-compose -f (Join-Path $PSScriptRoot '..\docker-compose.yml') down -v
