<#
.SYNOPSIS
  Start TraceHold. The same command works the first time and every time after.

    .\setup.ps1             first time: sets everything up (about 15 minutes), then starts the app
                            afterwards: detects the existing data and starts the app (about 1 minute)
    .\setup.ps1 -Reload     regenerate the synthetic data and re-run the whole analysis
    .\setup.ps1 -Rebuild    rebuild the web interface (after changing frontend code)
    .\setup.ps1 -Scale 0.2  use a smaller dataset when (re)loading data
    .\setup.ps1 -NoBrowser  do not open the browser automatically

  Requirements: Docker Desktop, the Exasol Personal starter kit, Python 3.11+, Node.js 20+.
#>
param(
    [double]$Scale = 1.0,
    [switch]$Reload,
    [switch]$Rebuild,
    [switch]$NoBrowser,
    [int]$Port = 8000
)
# Native tools (docker, python) report progress on stderr; with "Stop", Windows
# PowerShell 5.1 would treat that as fatal. Errors are checked explicitly instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$Docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $Docker)) { $Docker = "docker" }
$Container = "exasol-nano"
$Volume = "lienlens-exasol-data"
$Image = "exasol/nano:2026.2.0-nano.3-amd64"
$PwFile = "$env:USERPROFILE\.exasol-starter-kit\credentials\nano_sys_password"
$Py = ".\.venv\Scripts\python.exe"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "`n[!] $m" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------ 1. prerequisites
Step "Checking prerequisites"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "Python 3.11+ is not installed or not on PATH." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js 20+ (npm) is not installed or not on PATH." }
if (-not (Test-Path $PwFile)) { Fail "Exasol Personal starter kit not found ($PwFile). Install it first: https://github.com/exasol/exasol-personal" }
Write-Host "Python, Node.js and the Exasol starter kit are present."

# ------------------------------------------------------------------ 2. Docker
Step "Docker engine"
& $Docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting Docker Desktop..."
    Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep 5
        & $Docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { Fail "Docker did not start. Open Docker Desktop and run this script again." }
}
Write-Host "Docker is running."

# ------------------------------------------------------------------ 3. Python environment
Step "Python environment"
if (-not (Test-Path $Py)) { python -m venv .venv }
& $Py -m pip install -q --disable-pip-version-check -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Installing Python packages failed (see above)." }
$env:PYTHONPATH = Join-Path $PSScriptRoot "backend"
$env:PYTHONIOENCODING = "utf-8"
Write-Host "Ready."

# ------------------------------------------------------------------ 4. Exasol Personal
Step "Exasol Personal database"
# 3 GB keeps Exasol inside a 4 GB Docker VM; a 180 s stop timeout lets it shut
# down cleanly (killing it mid-write can corrupt its storage).
$RunArgs = @("--restart", "unless-stopped", "--stop-timeout", "180", "--shm-size=512m", "--pids-limit=-1",
             "-m", "3g", "-p", "127.0.0.1:8563:8563", "-v", "${Volume}:/exa")
function Wait-Exasol {
    Write-Host "Waiting for Exasol to accept connections (up to 6 minutes)..."
    for ($i = 0; $i -lt 72; $i++) {
        & $Py -m app.status db 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host "Exasol is up on 127.0.0.1:8563."; return }
        Start-Sleep 5
    }
    Fail "Exasol did not become ready. Check: docker logs --tail 40 $Container"
}
$state = & $Docker inspect -f '{{.State.Status}}' $Container 2>$null
if (-not $state) {
    Write-Host "First run: creating the database (this takes a minute)..."
    & $Docker volume create $Volume | Out-Null
    & $Docker run -d --name $Container @RunArgs -v "${PwFile}:/run/secrets/sys_password:ro" `
        $Image init sys_password_file=/run/secrets/sys_password | Out-Null
    Wait-Exasol
    # 'init' is valid only once; recreate the container without it so restarts work.
    & $Docker stop -t 180 $Container | Out-Null
    & $Docker rm $Container | Out-Null
    & $Docker run -d --name $Container @RunArgs $Image | Out-Null
} elseif ($state -ne "running") {
    & $Docker start $Container | Out-Null
}
Wait-Exasol

# ------------------------------------------------------------------ 5. data and analysis
$state = (& $Py -m app.status results | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0) { Fail "Exasol is not answering yet. Wait a minute and run this script again (your data is safe)." }
if ($Reload -or $state -eq "EMPTY") {
    Step "Synthetic data"
    if ($Reload -or -not (Test-Path "data\L\manifest.json")) {
        Write-Host "Generating about 2.4 million synthetic transactions (2-3 minutes)..."
        python backend\generator\generate.py --scale $Scale --seed 2026 --out data\L
        if ($LASTEXITCODE -ne 0) { Fail "Data generation failed (see above)." }
    }
    Step "Loading the data into Exasol"
    & $Py -m app.load data\L --fresh
    if ($LASTEXITCODE -ne 0) { Fail "Loading data into Exasol failed (see above)." }
    $state = "DATA"
}
if ($state -eq "DATA") {
    Step "Running the analysis inside Exasol (2-4 minutes on a laptop; progress is printed below)"
    & $Py -m app.engine
    if ($LASTEXITCODE -ne 0) { Fail "The analysis failed (see above)." }
    Step "Checking the results against the ground truth"
    & $Py -m app.evaluation | Out-Null
    Write-Host "Evaluation written to backend\results\evaluation.json"
} else {
    Step "Data and analysis results are already in Exasol (use -Reload to rebuild them)"
}

Step "AI features: letters, AI tables, read-only question user (safe to repeat)"
& $Py -m app.ai_setup
if ($LASTEXITCODE -ne 0) { Write-Host "AI setup did not finish; TraceHold still works without the AI features." -ForegroundColor Yellow }

# ------------------------------------------------------------------ 6. web interface
if ($Rebuild -or -not (Test-Path "frontend\dist\index.html")) {
    Step "Building the web interface"
    Push-Location frontend
    if (-not (Test-Path "node_modules")) { npm install --no-fund --no-audit }
    npm run build
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { Fail "Building the web interface failed (see above)." }
}

# ------------------------------------------------------------------ 7. start
Step "Starting TraceHold on http://127.0.0.1:$Port  (press Ctrl+C to stop)"
if (-not $NoBrowser) { Start-Job -ScriptBlock {
    param($p)
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$p/api/health" -TimeoutSec 3 | Out-Null; Start-Process "http://127.0.0.1:$p"; return }
        catch { Start-Sleep 2 }
    }
} -ArgumentList $Port | Out-Null }
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port $Port
