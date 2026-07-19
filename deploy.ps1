param(
    [Parameter(Position = 0)]
    [string]$ServerIP = $(if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "18.184.78.224" }),
    [string]$User = $(if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }),
    [int]$SshPort = $(if ($env:DEPLOY_SSH_PORT) { [int]$env:DEPLOY_SSH_PORT } else { 22 }),
    [string]$KeyFile = $env:DEPLOY_KEY_FILE
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalScript = Join-Path $ScriptDir "setup_server.sh"
$LocalDashboard = Join-Path $ScriptDir "dashboard"
$RemoteScript = "/root/setup_server.sh"
$SshArgs = @("-P", "$SshPort")
$ScpArgs = @("-P", "$SshPort")

if ($KeyFile) {
    $SshArgs += @("-i", $KeyFile)
    $ScpArgs += @("-i", $KeyFile)
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Server Deployment Helper" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Target host: $User@$ServerIP:$SshPort" -ForegroundColor Gray

if (-not (Get-Command scp -ErrorAction SilentlyContinue) -or -not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Error "OpenSSH client tools (ssh/scp) not found. Install the Windows OpenSSH Client feature first."
    exit 1
}

if (-not (Test-Path $LocalScript)) {
    Write-Error "Missing local setup script: $LocalScript"
    exit 1
}

if (-not (Test-Path $LocalDashboard)) {
    Write-Error "Missing local dashboard directory: $LocalDashboard"
    exit 1
}

Write-Host "`n[Step 1] Uploading setup script and Dashboard to server..." -ForegroundColor Yellow
Write-Host "Hint: When asked for password, type it and press Enter (cursor won't move)." -ForegroundColor Gray
& scp @ScpArgs $LocalScript "${User}@${ServerIP}:${RemoteScript}"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Setup script upload failed. Verify host/user/key settings and try again."
    exit $LASTEXITCODE
}

& scp @ScpArgs -r $LocalDashboard "${User}@${ServerIP}:/var/www/"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dashboard upload failed. Verify host/user/key settings and try again."
    exit $LASTEXITCODE
}

Write-Host "`n[Step 2] Running setup script on server..." -ForegroundColor Yellow
Write-Host "This will take 10-15 minutes. Please be patient." -ForegroundColor Gray
& ssh @SshArgs "${User}@${ServerIP}" "chmod +x ${RemoteScript} && ${RemoteScript}"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Remote setup execution failed. Check server auth and /root/setup_server.sh permissions."
    exit $LASTEXITCODE
}

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "   Deployment Finished!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
