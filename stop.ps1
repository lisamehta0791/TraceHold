<#
.SYNOPSIS
  Stop the Exasol database cleanly when you are done (the web server stops with Ctrl+C).
  Exasol is given up to 3 minutes to shut down; never force-kill it.
#>
$Docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $Docker)) { $Docker = "docker" }
Write-Host "Stopping Exasol (this can take up to a minute)..."
& $Docker stop -t 180 tracehold-exasol | Out-Null
Write-Host "Stopped. Run .\setup.ps1 to start everything again."
