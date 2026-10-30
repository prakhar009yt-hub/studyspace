param(
    [ValidateSet('Start', 'Status', 'Stop')][string]$Action = 'Start',
    [ValidateRange(1024, 65535)][int]$Port = 8503
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts/free-host-lib.ps1')
$projectDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv/Scripts/python.exe'
$tailscaleCommand = Get-Command tailscale -ErrorAction SilentlyContinue
$tailscaleExecutable = if ($tailscaleCommand) { $tailscaleCommand.Source } else { Join-Path $env:ProgramFiles 'Tailscale/tailscale.exe' }
if (-not (Test-Path -LiteralPath $tailscaleExecutable)) {
    throw 'Install Tailscale from https://tailscale.com/download/windows and sign in with a personal account on your PC and other devices. Then run Start-Free.ps1 again. No paid server is required.'
}
$stateFile = Join-Path $projectDirectory 'data/free-host.json'
$target = "http://127.0.0.1:$Port"
$state = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json } else { $null }

Push-Location -LiteralPath $projectDirectory
try {
    $statusText = & $tailscaleExecutable status --json
    if ($LASTEXITCODE -ne 0) { throw 'Tailscale is not ready. Open its Windows app and sign in first.' }
    $status = ($statusText -join "`n") | ConvertFrom-Json
    if ($status.BackendState -ne 'Running') { throw 'Open Tailscale and sign in. Its status must be Running before starting private access.' }
    $dnsName = [string](Get-StudyspaceProperty (Get-StudyspaceProperty $status 'Self') 'DNSName')
    $dnsName = $dnsName.TrimEnd('.')
    if (-not $dnsName.EndsWith('.ts.net')) { throw 'Enable MagicDNS and HTTPS for your personal Tailscale network, then retry.' }
    $remoteUrl = "https://$dnsName/"
    $serveText = & $tailscaleExecutable serve status --json
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing Tailscale Serve settings. No changes made.' }
    $serveConfig = ($serveText -join "`n") | ConvertFrom-Json
    $route = Get-StudyspaceServeState $serveConfig $target
    if ($route.Public) { throw 'Tailscale Funnel is enabled on HTTPS 443. This helper only creates private access. Review and disable that public route yourself before continuing.' }
    if ($route.HasRoute -and -not $route.Matches) { throw 'Tailscale HTTPS 443 already serves another app or additional paths. Nothing was overwritten. Use a separate device or configure that route manually.' }

    if ($Action -eq 'Status') {
        Write-Host "Private workspace URL: $remoteUrl"
        Write-Host "Studyspace route active: $($route.Matches)"
        Write-Host 'Only devices/users permitted by your Tailscale network policy can connect. The PC and app must be running.'
        return
    }
    if ($Action -eq 'Stop') {
        if (-not $state -or -not $state.owned -or $state.target -ne $target -or $state.url -ne $remoteUrl) { throw 'No matching private route owned by this helper. Nothing was changed.' }
        if ($route.Matches) {
            & $tailscaleExecutable serve --https=443 off
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop the private route. Check Tailscale status.' }
        }
        $state.owned = $false
        $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
        Write-Host 'Private remote access stopped. Your local app and saved notes remain available.'
        return
    }

    if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Install the project first using README.md.' }
    $healthy = $false
    try { $healthy = (Invoke-WebRequest "$target/_stcore/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { }
    if ($healthy) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        $processInfo = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" } else { $null }
        if (-not $processInfo -or $processInfo.CommandLine -notlike "*$projectDirectory*" -or $processInfo.CommandLine -notmatch 'streamlit.*dashboard.py') {
            throw 'The selected port responds, but this project could not be verified as its owner. Nothing was shared. Choose another -Port.'
        }
        if ($listener.LocalAddress -notin @('127.0.0.1', '::1')) { throw 'This app is not bound only to loopback. Restart it with --server.address=127.0.0.1 before using this helper.' }
    } else {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw 'The selected port is occupied. Choose another -Port.' }
        $dataDirectory = Join-Path $projectDirectory 'data'
        New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
        $dashboard = Join-Path $projectDirectory 'dashboard.py'
        $arguments = @('-m', 'streamlit', 'run', ('"' + $dashboard + '"'), '--server.address=127.0.0.1', "--server.port=$Port", '--server.headless=true')
        $process = Start-Process -FilePath $pythonExecutable -ArgumentList $arguments -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dataDirectory 'free-host.stdout.log') -RedirectStandardError (Join-Path $dataDirectory 'free-host.stderr.log')
        $deadline = (Get-Date).AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 500
            try { $healthy = (Invoke-WebRequest "$target/_stcore/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
            if ($process.HasExited) { throw 'Studyspace stopped during startup. Check data/free-host.stderr.log.' }
        } while (-not $healthy -and (Get-Date) -lt $deadline)
        if (-not $healthy) { throw 'Studyspace did not become ready. No private route was created. Check data/free-host.stderr.log.' }
    }

    if (-not $route.Matches) {
        & $tailscaleExecutable serve --bg --https=443 $target
        if ($LASTEXITCODE -ne 0) { throw 'Tailscale Serve needs setup. Follow the Tailscale HTTPS setup link it displayed, then rerun this script.' }
    }
    $verifiedText = & $tailscaleExecutable serve status --json
    if ($LASTEXITCODE -ne 0) { throw 'Could not verify the route after setup. Inspect Tailscale Serve status before using it.' }
    $verifiedRoute = Get-StudyspaceServeState (($verifiedText -join "`n") | ConvertFrom-Json) $target
    if (-not $verifiedRoute.Matches -or $verifiedRoute.Public) { throw 'The expected private route was not verified. Check Tailscale settings; no ready URL will be advertised.' }
    $owned = (-not $route.HasRoute) -or ($state -and $state.owned -and $state.target -eq $target -and $state.url -eq $remoteUrl)
    New-Item -ItemType Directory -Path (Split-Path $stateFile) -Force | Out-Null
    @{ target = $target; url = $remoteUrl; owned = [bool]$owned } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
    Write-Host "Private Studyspace is ready: $remoteUrl"
    Write-Host 'No public Funnel or router port forwarding is enabled. Access follows your Tailscale network policy; use a personal network containing only trusted devices/users.'
    Write-Host 'Keep this PC awake and online. Electricity/internet and any provider API charges still apply.'
    Write-Host "Optional Vercel setting: STUDYSPACE_BACKEND_URL=$remoteUrl"
} finally {
    Pop-Location
}
