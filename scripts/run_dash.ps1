# Levanta el dashboard Dash (analisis/dashboard_zonas_dash.py).
# Uso: .\scripts\run_dash.ps1
#      (o desde scripts/: .\run_dash.ps1)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "FeBAMBA Dash — http://127.0.0.1:8050/" -ForegroundColor Cyan
Write-Host "Raiz: $RepoRoot" -ForegroundColor DarkGray

python analisis\dashboard_zonas_dash.py
