# Actualización diaria: scrape GES 2026 + consolidar + ranking de tiras.
# Programar con el Programador de tareas de Windows (ver docs/ACTUALIZACION_DIARIA.md).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Inicio actualización FeBAMBA" -ForegroundColor Cyan

& $Python pipelines\actualizar_temporada_activa.py
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host "Actualización falló (código $code). Revisá logs\ en el proyecto." -ForegroundColor Red
    exit $code
}

Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] OK" -ForegroundColor Green
exit 0
