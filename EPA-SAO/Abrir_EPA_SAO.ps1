param()

$ErrorActionPreference = "Stop"
$epaDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $epaDir
$publicador = Join-Path $rootDir "publicar_epa_resiliente.ps1"

& $publicador `
    -Provider "SAO" `
    -Port 8081 `
    -EpaDir $epaDir `
    -DbName "epa_entel_sao.sqlite3" `
    -CatalogName "SAO_2026.xlsx"
