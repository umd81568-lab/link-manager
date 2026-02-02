$ServerIP = "207.180.249.220"
$User = "root"
$LocalScript = ".\setup_server.sh"
$RemoteScript = "/root/setup_server.sh"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Server Deployment Helper" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check if ssh/scp is available
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    Write-Error "SCP command not found. Please ensure OpenSSH Client is installed."
    exit
}

Write-Host "`n[Step 1] Uploading setup script and Dashboard to server..." -ForegroundColor Yellow
Write-Host "Hint: When asked for password, type it and press Enter (cursor won't move)." -ForegroundColor Gray
scp $LocalScript ${User}@${ServerIP}:${RemoteScript}
scp -r ".\dashboard" ${User}@${ServerIP}:/var/www/

if ($LASTEXITCODE -ne 0) {
    Write-Error "Upload failed. Please check your password and try again."
    exit
}

Write-Host "`n[Step 2] Running setup script on server..." -ForegroundColor Yellow
Write-Host "This will take 10-15 minutes. Please be patient." -ForegroundColor Gray
ssh ${User}@${ServerIP} "chmod +x ${RemoteScript} && ${RemoteScript}"

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "   Deployment Finished!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
