param(
    [Parameter(Mandatory = $true)][string]$Provider,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$EpaDir,
    [Parameter(Mandatory = $true)][string]$DbName,
    [Parameter(Mandatory = $true)][string]$CatalogName,
    [string]$Token = "entel-epa-admin",
    [switch]$NoBrowser,
    [switch]$ExitAfterReady
)

$ErrorActionPreference = "Continue"

$EpaDir = (Resolve-Path -LiteralPath $EpaDir).Path
Set-Location -LiteralPath $EpaDir

$projectRoot = Split-Path -Parent $EpaDir
$panelRoot = $projectRoot
if ((Split-Path -Leaf (Split-Path -Parent $projectRoot)) -ieq "ST") {
    $panelRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)
}
$pythonRoot = Split-Path -Parent $panelRoot

$localUrl = "http://127.0.0.1:$Port"
$localAdminUrl = "$localUrl/admin?token=$Token"
$logDir = Join-Path $projectRoot "logs\EPA_$Provider"

$global:epaProcess = $null
$global:tunnelProcess = $null
$global:epaStartedByThisScript = $false
$global:cleanupDone = $false

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Banner {
    Clear-Host
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host " EPA $Provider - publicador resiliente" -ForegroundColor Cyan
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host "1) Levanta EPA local." -ForegroundColor Yellow
    Write-Host "2) Busca un tunel limpio sin warning para clientes." -ForegroundColor Yellow
    Write-Host "3) Si lo limpio falla, usa Serveo solo como respaldo." -ForegroundColor Yellow
    Write-Host "4) Si todo falla, deja modo local listo para presentar." -ForegroundColor Yellow
    Write-Host ""
}

function Read-LogsText {
    param([string]$OutLog, [string]$ErrLog)
    $txt = ""
    if (Test-Path -LiteralPath $OutLog) { $txt += Get-Content -LiteralPath $OutLog -Raw -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $ErrLog) { $txt += "`n" + (Get-Content -LiteralPath $ErrLog -Raw -ErrorAction SilentlyContinue) }
    return $txt
}

function Test-Url {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Test-PublicAdmin {
    param([string]$PublicAdminUrl, [int]$TimeoutSec = 6)
    try {
        $r = Invoke-WebRequest -Uri $PublicAdminUrl -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($r.StatusCode -ne 200) { return $false }
        if ($r.Content -match "Error 1033|Cloudflare Tunnel error|Bad Gateway|Tunnel unavailable") { return $false }
        return ($r.Content -match "EPA Entel|Nueva atenci|Panel|Admin")
    } catch {
        return $false
    }
}

function Resolve-HostAny {
    param([string]$HostName, [string]$Server = "")
    try {
        if (Get-Command Resolve-DnsName -ErrorAction SilentlyContinue) {
            if ($Server) {
                $r = Resolve-DnsName -Name $HostName -Type A -Server $Server -DnsOnly -ErrorAction Stop
            } else {
                $r = Resolve-DnsName -Name $HostName -Type A -DnsOnly -ErrorAction Stop
            }
            $ips = @($r | Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress -ErrorAction SilentlyContinue)
            return ($ips.Count -gt 0)
        }
    } catch {}

    try {
        if ($Server) { $raw = nslookup $HostName $Server 2>$null } else { $raw = nslookup $HostName 2>$null }
        $txt = ($raw | Out-String)
        return ($txt -match "Address:\s+\d+\.\d+\.\d+\.\d+" -and $txt -notmatch "NXDOMAIN|Non-existent|can't find")
    } catch {
        return $false
    }
}

function Stop-PortListeners {
    param([int]$PortToFree)
    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $PortToFree -State Listen -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $ownerPid = [int]$listener.OwningProcess
            if ($ownerPid -gt 0 -and $ownerPid -ne $PID) {
                Write-Host "Liberando puerto $PortToFree ocupado por PID $ownerPid" -ForegroundColor DarkYellow
                Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}
}

function Get-EpaManagedProcesses {
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            (
                ($_.Name -ieq "cloudflared.exe" -and ($cmd -match "127\.0\.0\.1:$Port" -or $cmd -match "localhost:$Port")) -or
                ($_.Name -ieq "ssh.exe" -and ($cmd -match "localhost:$Port" -or $cmd -match "127\.0\.0\.1:$Port")) -or
                ($_.Name -match "(?i)^(python|pythonw|python3(\.\d+)?)\.exe$" -and $cmd -match "EPA\.PY" -and $cmd -like "*$EpaDir*")
            )
        }
    } catch {
        @()
    }
}

function Get-TunnelManagedProcesses {
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            (
                ($_.Name -ieq "cloudflared.exe" -and ($cmd -match "127\.0\.0\.1:$Port" -or $cmd -match "localhost:$Port")) -or
                ($_.Name -ieq "ssh.exe" -and ($cmd -match "localhost:$Port" -or $cmd -match "127\.0\.0\.1:$Port"))
            )
        }
    } catch {
        @()
    }
}

function Stop-ManagedProcesses {
    param([string]$Reason = "")
    if ($Reason) { Write-Host $Reason -ForegroundColor Yellow }
    try {
        foreach ($p in @(Get-EpaManagedProcesses)) {
            Write-Host "Cerrando PID $($p.ProcessId): $($p.Name)" -ForegroundColor DarkYellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Stop-TunnelProcesses {
    param([string]$Reason = "")
    if ($Reason) { Write-Host $Reason -ForegroundColor Yellow }
    try {
        foreach ($p in @(Get-TunnelManagedProcesses)) {
            Write-Host "Cerrando tunel PID $($p.ProcessId): $($p.Name)" -ForegroundColor DarkYellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Stop-CurrentTunnel {
    try {
        if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
            Write-Host "Cerrando tunel activo..." -ForegroundColor Yellow
            $global:tunnelProcess.Kill()
            $global:tunnelProcess.WaitForExit(3000) | Out-Null
        }
    } catch {}
}

function Stop-CurrentEPA {
    try {
        if ($global:epaStartedByThisScript -and $global:epaProcess -and -not $global:epaProcess.HasExited) {
            Write-Host "Cerrando EPA local..." -ForegroundColor Yellow
            $global:epaProcess.Kill()
            $global:epaProcess.WaitForExit(3000) | Out-Null
        }
    } catch {}
}

function Stop-All {
    if ($global:cleanupDone) { return }
    $global:cleanupDone = $true
    Stop-CurrentTunnel
    Stop-CurrentEPA
    Stop-ManagedProcesses -Reason "Limpieza final EPA $Provider."
}

Register-EngineEvent PowerShell.Exiting -Action { Stop-All } | Out-Null
try {
    [Console]::add_CancelKeyPress({
        param($sender, $eventArgs)
        $eventArgs.Cancel = $true
        Stop-All
        exit
    })
} catch {}

function Get-PythonExe {
    $venvDir = Join-Path $env:USERPROFILE "Documents\Codex\PythonEnvs\PanelAdherencia"
    $pythonVenv = Join-Path $venvDir "Scripts\python.exe"
    if (Test-Path -LiteralPath $pythonVenv) { return $pythonVenv }

    $pyCmd = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        & $pyCmd.Source -3 -m venv $venvDir
    } else {
        $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
        if ($pythonCmd) { & $pythonCmd.Source -m venv $venvDir }
    }

    if (Test-Path -LiteralPath $pythonVenv) { return $pythonVenv }

    $fallback = Get-Command "python" -ErrorAction SilentlyContinue
    if ($fallback) {
        if ($fallback.Source) { return $fallback.Source }
        return $fallback.Name
    }
    return ""
}

function Start-LocalEPA {
    Stop-PortListeners -PortToFree $Port
    Start-Sleep -Milliseconds 600

    if (Test-Url -Url $localAdminUrl -TimeoutSec 1) {
        Write-Host "EPA local ya estaba activa: $localAdminUrl" -ForegroundColor Green
        return $true
    }

    $pythonExe = Get-PythonExe
    if (-not $pythonExe) {
        Write-Host "ERROR: No se encontro Python ni .venv." -ForegroundColor Red
        return $false
    }

    $serverOutLog = Join-Path $logDir "epa_server.out.log"
    $serverErrLog = Join-Path $logDir "epa_server.err.log"
    Remove-Item -LiteralPath $serverOutLog, $serverErrLog -ErrorAction SilentlyContinue

    $env:EPA_ADMIN_TOKEN = $Token
    $env:EPA_HOST = "127.0.0.1"
    $env:EPA_PORT = [string]$Port
    $env:EPA_STRICT_PORT = "1"
    $env:EPA_PROVIDER = $Provider
    $env:EPA_DB = Join-Path $EpaDir $DbName
    $env:EPA_CATALOG_XLSX = Join-Path $projectRoot $CatalogName

    Write-Host "Iniciando EPA local $Provider en $localUrl ..." -ForegroundColor Green
    $global:epaProcess = Start-Process -FilePath $pythonExe `
        -ArgumentList @("-u", "EPA.PY") `
        -WorkingDirectory $EpaDir `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serverOutLog `
        -RedirectStandardError $serverErrLog
    $global:epaStartedByThisScript = $true

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Url -Url $localAdminUrl -TimeoutSec 2) {
            Write-Host "EPA local OK: $localAdminUrl" -ForegroundColor Green
            return $true
        }
        if ($global:epaProcess -and $global:epaProcess.HasExited) {
            Write-Host "ERROR: La EPA local se cerro al iniciar." -ForegroundColor Red
            $txt = Read-LogsText -OutLog $serverOutLog -ErrLog $serverErrLog
            if ($txt.Trim()) { Write-Host $txt -ForegroundColor Gray }
            return $false
        }
        if (($i % 5) -eq 0) { Write-Host "Esperando EPA local... $i/30" -ForegroundColor DarkYellow }
    }

    Write-Host "ERROR: La EPA local no respondio." -ForegroundColor Red
    return $false
}

function Start-CloudflareTunnel {
    $cloudflared = Get-Command "cloudflared" -ErrorAction SilentlyContinue
    if (-not $cloudflared) {
        Write-Host "Cloudflare no esta instalado; se pasa al tunel SSH limpio." -ForegroundColor Yellow
        return $null
    }

    for ($attempt = 1; $attempt -le 1; $attempt++) {
        Stop-CurrentTunnel
        Stop-TunnelProcesses -Reason "Preparando tunel limpio Cloudflare intento $attempt/1."

        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $outLog = Join-Path $logDir "cloudflared_$stamp.out.log"
        $errLog = Join-Path $logDir "cloudflared_$stamp.err.log"
        Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

        Write-Host "Intentando Cloudflare limpio, solo si responde sin DNS raro..." -ForegroundColor Green
        $args = @("tunnel", "--no-autoupdate", "--protocol", "http2", "--edge-ip-version", "4", "--url", $localUrl)
        $global:tunnelProcess = Start-Process -FilePath $cloudflared.Source `
            -ArgumentList $args `
            -PassThru `
            -WindowStyle Hidden `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog

        $publicUrl = $null
        for ($i = 1; $i -le 45; $i++) {
            Start-Sleep -Seconds 1
            $txt = Read-LogsText -OutLog $outLog -ErrLog $errLog
            $m = [regex]::Match($txt, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
            if ($m.Success) {
                $publicUrl = $m.Value.Trim()
                break
            }
            if ($global:tunnelProcess -and $global:tunnelProcess.HasExited) { break }
        }

        if (-not $publicUrl) {
            Write-Host "Cloudflare no entrego URL publica." -ForegroundColor Red
            Stop-CurrentTunnel
            continue
        }

        $hostName = ([System.Uri]$publicUrl).Host
        if (-not (Resolve-HostAny -HostName $hostName)) {
            Write-Host "Cloudflare entrego URL, pero este Windows no resuelve DNS: $hostName" -ForegroundColor Red
            Stop-CurrentTunnel
            continue
        }

        $admin = "$publicUrl/admin?token=$Token"
        if (Test-PublicAdmin -PublicAdminUrl $admin -TimeoutSec 8) {
            return @{
                Provider = "Cloudflare limpio"
                PublicUrl = $publicUrl
                AdminUrl = $admin
                Process = $global:tunnelProcess
                HasWarning = $false
            }
        }

        Write-Host "Cloudflare resolvio DNS, pero el panel publico no respondio." -ForegroundColor Red
        Stop-CurrentTunnel
    }
    return $null
}

function Start-LocalhostRunTunnel {
    $ssh = Get-Command "ssh" -ErrorAction SilentlyContinue
    if (-not $ssh) {
        Write-Host "No se encontro ssh.exe para localhost.run." -ForegroundColor Red
        return $null
    }

    Stop-CurrentTunnel
    Stop-TunnelProcesses -Reason "Preparando tunel SSH localhost.run."

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outLog = Join-Path $logDir "localhost_run_$stamp.out.log"
    $errLog = Join-Path $logDir "localhost_run_$stamp.err.log"
    Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

    Write-Host "Intentando localhost.run por SSH..." -ForegroundColor Green
    $args = @(
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        "-R", "80:127.0.0.1:$Port",
        "nokey@localhost.run"
    )
    $global:tunnelProcess = Start-Process -FilePath $ssh.Source `
        -ArgumentList $args `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog

    $publicUrl = $null
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 1
        $txt = Read-LogsText -OutLog $outLog -ErrLog $errLog
        $m = [regex]::Match($txt, "https://[a-zA-Z0-9-]+\.lhr\.life")
        if ($m.Success) {
            $publicUrl = $m.Value.Trim()
            break
        }
        if ($global:tunnelProcess -and $global:tunnelProcess.HasExited) { break }
    }

    if (-not $publicUrl) {
        Write-Host "localhost.run no entrego URL publica." -ForegroundColor Red
        $txt = Read-LogsText -OutLog $outLog -ErrLog $errLog
        if ($txt.Trim()) { Write-Host $txt -ForegroundColor Gray }
        Stop-CurrentTunnel
        return $null
    }

    $admin = "$publicUrl/admin?token=$Token"
    for ($i = 1; $i -le 2; $i++) {
        if (Test-PublicAdmin -PublicAdminUrl $admin -TimeoutSec 3) {
            return @{
                Provider = "localhost.run"
                PublicUrl = $publicUrl
                AdminUrl = $admin
                Process = $global:tunnelProcess
                HasWarning = $false
            }
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "localhost.run entrego URL, pero el panel publico no respondio." -ForegroundColor Red
    Stop-CurrentTunnel
    return $null
}

function Start-ServeoTunnel {
    $ssh = Get-Command "ssh" -ErrorAction SilentlyContinue
    if (-not $ssh) {
        Write-Host "No se encontro ssh.exe para Serveo." -ForegroundColor Red
        return $null
    }

    Stop-CurrentTunnel
    Stop-TunnelProcesses -Reason "Preparando tunel SSH Serveo."

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outLog = Join-Path $logDir "serveo_$stamp.out.log"
    $errLog = Join-Path $logDir "serveo_$stamp.err.log"
    Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

    Write-Host "Intentando Serveo por SSH..." -ForegroundColor Green
    $args = @(
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        "-R", "80:127.0.0.1:$Port",
        "serveo.net"
    )
    $global:tunnelProcess = Start-Process -FilePath $ssh.Source `
        -ArgumentList $args `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog

    $publicUrl = $null
    for ($i = 1; $i -le 35; $i++) {
        Start-Sleep -Seconds 1
        $txt = Read-LogsText -OutLog $outLog -ErrLog $errLog
        $m = [regex]::Match($txt, "https://[^\s]+\.serveousercontent\.com")
        if ($m.Success) {
            $publicUrl = $m.Value.Trim()
            break
        }
        if ($global:tunnelProcess -and $global:tunnelProcess.HasExited) { break }
    }

    if (-not $publicUrl) {
        Write-Host "Serveo no entrego URL publica." -ForegroundColor Red
        $txt = Read-LogsText -OutLog $outLog -ErrLog $errLog
        if ($txt.Trim()) { Write-Host $txt -ForegroundColor Gray }
        Stop-CurrentTunnel
        return $null
    }

    $admin = "$publicUrl/admin?token=$Token"
    for ($i = 1; $i -le 10; $i++) {
        if (Test-PublicAdmin -PublicAdminUrl $admin -TimeoutSec 8) {
            return @{
                Provider = "Serveo"
                PublicUrl = $publicUrl
                AdminUrl = $admin
                Process = $global:tunnelProcess
                HasWarning = $true
            }
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "Serveo entrego URL, pero el panel publico no respondio." -ForegroundColor Red
    Stop-CurrentTunnel
    return $null
}

function Open-BrowserSafe {
    param([string]$Url)
    if ($NoBrowser) { return }
    try { Start-Process $Url | Out-Null }
    catch {
        Write-Host "No pude abrir navegador automatico. Copia esta URL:" -ForegroundColor Yellow
        Write-Host $Url -ForegroundColor White
    }
}

function First-Hashtable {
    param([object]$Value)
    if ($Value -is [hashtable]) { return $Value }
    foreach ($item in @($Value)) {
        if ($item -is [hashtable]) { return $item }
    }
    return $null
}

function Get-LocalAdminWithPublicBase {
    param([string]$PublicUrl)
    if (-not $PublicUrl) { return $localAdminUrl }
    return "$localAdminUrl&public_base=$([System.Uri]::EscapeDataString($PublicUrl))"
}

function Show-ReadyAndWait {
    param([hashtable]$Tunnel)

    if ($Tunnel) {
        $hasWarning = ($Tunnel.ContainsKey("HasWarning") -and [bool]$Tunnel.HasWarning)
        $adminUrl = [string]$Tunnel.AdminUrl
        $adminOpenUrl = $adminUrl
        if ($hasWarning) {
            $adminOpenUrl = Get-LocalAdminWithPublicBase -PublicUrl ([string]$Tunnel.PublicUrl)
        }
        try {
            Set-Clipboard -Value $adminOpenUrl
            $copied = $true
        } catch {
            $copied = $false
        }

        Write-Host ""
        Write-Host "==============================================" -ForegroundColor Cyan
        Write-Host " EPA $Provider PUBLICA OK por $($Tunnel.Provider)" -ForegroundColor Cyan
        Write-Host "==============================================" -ForegroundColor Cyan
        if ($hasWarning) {
            Write-Host "ADMIN SIN WARNING (abre local, genera links con base publica):" -ForegroundColor Yellow
        } else {
            Write-Host "LINK ADMIN CON TOKEN (usa este para generar links):" -ForegroundColor Yellow
        }
        Write-Host $adminOpenUrl -ForegroundColor White
        if ($copied) {
            Write-Host "Copiado al portapapeles." -ForegroundColor Green
        }
        Write-Host ""
        if ($hasWarning) {
            Write-Host "ATENCION: este proveedor muestra warning al cliente. Usalo solo si no hay tunel limpio." -ForegroundColor Red
        } else {
            Write-Host "Tunel limpio para clientes: no deberia mostrar pagina de warning." -ForegroundColor Green
        }
        Write-Host "Base publica de encuestas:" -ForegroundColor Yellow
        Write-Host $Tunnel.PublicUrl -ForegroundColor White
        Write-Host ""
        Write-Host "Manten esta ventana abierta durante la demo." -ForegroundColor Green
        Open-BrowserSafe -Url $adminOpenUrl
    } else {
        try {
            Set-Clipboard -Value $localAdminUrl
            $copiedLocal = $true
        } catch {
            $copiedLocal = $false
        }

        Write-Host ""
        Write-Host "==============================================" -ForegroundColor Yellow
        Write-Host " MODO LOCAL DE RESPALDO" -ForegroundColor Yellow
        Write-Host "==============================================" -ForegroundColor Yellow
        Write-Host "Los tuneles publicos no respondieron. La EPA local SI esta lista:" -ForegroundColor Green
        Write-Host $localAdminUrl -ForegroundColor White
        if ($copiedLocal) {
            Write-Host "Link local copiado al portapapeles." -ForegroundColor Green
        }
        Write-Host ""
        Write-Host "Para presentar en el mismo PC, usa esa URL. Para clientes externos necesitas reintentar con internet estable." -ForegroundColor Yellow
        Open-BrowserSafe -Url $localAdminUrl
    }

    Write-Host ""
        Write-Host "Controles: L abre local | P abre admin publico | Q cierra todo" -ForegroundColor Cyan
    if ($ExitAfterReady) { return }
    while ($true) {
        Start-Sleep -Milliseconds 500
        if ($Tunnel -and $global:tunnelProcess -and $global:tunnelProcess.HasExited) {
            Write-Host "El tunel publico se cerro. Mantengo EPA local activa." -ForegroundColor Red
            $Tunnel = $null
        }
        try {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq "Q") { break }
                if ($key.Key -eq "L") { Open-BrowserSafe -Url $localAdminUrl }
                if ($key.Key -eq "P" -and $Tunnel) { Open-BrowserSafe -Url $adminOpenUrl }
            }
        } catch {}
    }
}

Banner

if (-not (Test-Path -LiteralPath (Join-Path $EpaDir "EPA.PY"))) {
    Write-Host "ERROR: No encuentro EPA.PY en $EpaDir" -ForegroundColor Red
    Read-Host "Presiona ENTER para cerrar"
    exit 1
}

Stop-ManagedProcesses -Reason "Limpieza inicial EPA $Provider."

if (-not (Start-LocalEPA)) {
    Stop-All
    Read-Host "Presiona ENTER para cerrar"
    exit 1
}

$tunnel = First-Hashtable (Start-CloudflareTunnel)
if (-not $tunnel) {
    Write-Host "Pasando a tunel limpio alternativo localhost.run..." -ForegroundColor Yellow
    $tunnel = First-Hashtable (Start-LocalhostRunTunnel)
}
if (-not $tunnel) {
    Write-Host "No hubo tunel limpio estable. Usando Serveo como respaldo con warning del proveedor." -ForegroundColor Yellow
    $tunnel = First-Hashtable (Start-ServeoTunnel)
}

try {
    Show-ReadyAndWait -Tunnel $tunnel
}
finally {
    Stop-All
}
