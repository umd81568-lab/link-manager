Param(
    [string]$Token = "",
    [string]$ProjectName = "sovereign-guardian",
    [string]$Domain1 = "pccpoicegov.life",
    [string]$Domain2 = "pccpolicegovbd.work",
    [string]$ZipPath = ""
)

if (-not $Token) {
    if ($env:CLOUDFLARE_API_TOKEN) { $Token = $env:CLOUDFLARE_API_TOKEN }
    elseif ($env:CF_API_TOKEN) { $Token = $env:CF_API_TOKEN }
}
if (-not $Token) { Write-Error "Cloudflare API token is required"; exit 1 }
$Headers = @{ Authorization = "Bearer $Token" }
Add-Type -AssemblyName System.Net.Http

function Get-AccountId() {
    try {
        $resp = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/accounts" -Headers $Headers
        if ($resp.success -and $resp.result.Count -gt 0) { return $resp.result[0].id }
        else { Write-Error "No Cloudflare accounts accessible with this token"; exit 1 }
    } catch { Write-Error "Failed to list accounts: $_"; exit 1 }
}

function Get-Zone($name) {
    try {
        $resp = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/zones?name=$name" -Headers $Headers
        if ($resp.success -and $resp.result.Count -gt 0) { return $resp.result[0] }
        else { return $null }
    } catch { return $null }
}

function Get-Zones() {
    try {
        $resp = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/zones" -Headers $Headers
        if ($resp.success -and $resp.result.Count -gt 0) { return $resp.result }
        else { return @() }
    } catch { return @() }
}

function Ensure-Project($accountId, $projectName) {
    try {
        $check = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects" -Headers $Headers
        $exists = $check.result | Where-Object { $_.name -eq $projectName }
        if ($exists) { return $true }
        $body = @{ name = $projectName; production_branch = "main" } | ConvertTo-Json
        $create = Invoke-RestMethod -Method POST -Uri "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects" -Headers ($Headers + @{ 'Content-Type' = 'application/json' }) -Body $body
        return $create.success
    } catch { Write-Error "Failed to create project: $_"; exit 1 }
}

function Deploy-Minimal($accountId, $projectName) {
    $indexContent = @"
<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sovereign Guardian</title>
<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;padding:40px;background:#0b0f14;color:#e6edf3} .card{max-width:800px;margin:auto;background:#121826;border:1px solid #263041;border-radius:12px;padding:24px} .btn{display:inline-block;background:#00f2ea;color:#0b0f14;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600} .muted{color:#9aa7b2;font-size:14px}</style>
</head><body>
<div class="card">
  <h1>Deployment OK</h1>
  <p class="muted">Cloudflare Pages মিনিমাল সাইট লাইভ আছে। পূর্ণ ড্যাশবোর্ড শীঘ্রই আপলোড হবে।</p>
  <a class="btn" href="/" aria-label="Home">Go Home</a>
</div>
</body></html>
"@

    $sha1 = [System.BitConverter]::ToString((New-Object System.Security.Cryptography.SHA1Managed).ComputeHash([System.Text.Encoding]::UTF8.GetBytes($indexContent))).Replace("-","" ).ToLower()
    $manifestObj = @{ files = @{ "index.html" = @{ size = ($indexContent.Length); checksum = "sha1:$sha1" } } }
    $manifestJson = ($manifestObj | ConvertTo-Json -Compress)

    $deployUri = "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects/$projectName/deployments"

    $handler = New-Object System.Net.Http.HttpClientHandler
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Token)

    $content = New-Object System.Net.Http.MultipartFormDataContent
    $manifestContent = New-Object System.Net.Http.StringContent($manifestJson, [System.Text.Encoding]::UTF8, "application/json")
    $indexBytes = [System.Text.Encoding]::UTF8.GetBytes($indexContent)
    $indexContentObj = New-Object System.Net.Http.ByteArrayContent($indexBytes)
    $indexContentObj.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue("text/html")

    $content.Add($manifestContent, "manifest")
    $content.Add($indexContentObj, "files[index.html]", "index.html")

    try {
        $resp = $client.PostAsync($deployUri, $content).Result
        $resp.EnsureSuccessStatusCode() | Out-Null
        $body = $resp.Content.ReadAsStringAsync().Result | ConvertFrom-Json
        return $body.success
    } catch {
        Write-Error "Deployment failed: $_"
        exit 1
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Attach-Domain($accountId, $projectName, $domain) {
    try {
        $body = @{ domain = $domain } | ConvertTo-Json
        $resp = Invoke-RestMethod -Method POST -Uri "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects/$projectName/domains" -Headers ($Headers + @{ 'Content-Type' = 'application/json' }) -Body $body
        return $resp.success
    } catch { Write-Error "Attach domain failed for $domain : $_"; return $false }
}

function Get-ContentType($name) {
    $ext = [System.IO.Path]::GetExtension($name).ToLower()
    switch ($ext) {
        ".html" { return "text/html" }
        ".css" { return "text/css" }
        ".js" { return "application/javascript" }
        ".json" { return "application/json" }
        default { return "application/octet-stream" }
    }
}

function Deploy-Zip($accountId, $projectName, $zipPath) {
    if (-not (Test-Path $zipPath)) { Write-Error "Zip not found: $zipPath"; exit 1 }
    $deployUri = "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects/$projectName/deployments"

    $handler = New-Object System.Net.Http.HttpClientHandler
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Token)

    $content = New-Object System.Net.Http.MultipartFormDataContent

    $manifest = @{ files = @{} }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.EndsWith("/")) { continue }
            $ms = New-Object System.IO.MemoryStream
            $zs = $entry.Open()
            $zs.CopyTo($ms)
            $zs.Dispose()
            $bytes = $ms.ToArray()
            $ms.Dispose()
            $sha1 = [System.BitConverter]::ToString((New-Object System.Security.Cryptography.SHA1Managed).ComputeHash($bytes)).Replace("-","" ).ToLower()
            $manifest.files[$entry.FullName] = @{ size = $bytes.Length; checksum = "sha1:$sha1" }
            $ba = New-Object System.Net.Http.ByteArrayContent($bytes)
            $ba.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue((Get-ContentType $entry.FullName))
            $content.Add($ba, "files[$($entry.FullName)]", $entry.FullName)
        }
    } finally {
        $zip.Dispose()
    }

    $manifestJson = ($manifest | ConvertTo-Json -Compress)
    $manifestContent = New-Object System.Net.Http.StringContent($manifestJson, [System.Text.Encoding]::UTF8, "application/json")
    $content.Add($manifestContent, "manifest")

    try {
        $resp = $client.PostAsync($deployUri, $content).Result
        $resp.EnsureSuccessStatusCode() | Out-Null
        $body = $resp.Content.ReadAsStringAsync().Result | ConvertFrom-Json
        return $body.success
    } catch {
        Write-Error "Zip deployment failed: $_"
        exit 1
    } finally {
        $client.Dispose(); $handler.Dispose()
    }
}

$z1 = Get-Zone -name $Domain1
if ($z1) { Write-Host "Zone OK: $($z1.name) [$($z1.id)]" } else { Write-Warning "Zone not found or not accessible: $Domain1" }
$z2 = Get-Zone -name $Domain2
if ($z2) { Write-Host "Zone OK: $($z2.name) [$($z2.id)]" } else { Write-Warning "Zone not found or not accessible: $Domain2" }

# Determine account id reliably even if zones aren't accessible
$accountId = Get-AccountId
Write-Host "Account: $accountId"

if (-not (Ensure-Project -accountId $accountId -projectName $ProjectName)) { Write-Error "Failed to ensure project"; exit 1 }
Write-Host "Project ready: $ProjectName"

if ($ZipPath -and (Test-Path $ZipPath)) {
    if (-not (Deploy-Zip -accountId $accountId -projectName $ProjectName -zipPath $ZipPath)) { Write-Error "Deployment failed"; exit 1 }
    Write-Host "ZIP deployment completed"
} else {
    if (-not (Deploy-Minimal -accountId $accountId -projectName $ProjectName)) { Write-Error "Deployment failed"; exit 1 }
    Write-Host "Minimal deployment completed"
}

if ($z1) {
    $attach1 = $Domain1
    if ($Domain1 -eq $z1.name) { $attach1 = "sg.$($z1.name)" }
    if (Attach-Domain -accountId $accountId -projectName $ProjectName -domain $attach1) { Write-Host "Domain attached: $attach1" }
}
if ($z2) {
    $attach2 = $Domain2
    if ($Domain2 -eq $z2.name) { $attach2 = "sg.$($z2.name)" }
    if (Attach-Domain -accountId $accountId -projectName $ProjectName -domain $attach2) { Write-Host "Domain attached: $attach2" }
}
if (-not $z1 -and -not $z2) {
    $zones = Get-Zones
    if ($zones.Count -gt 0) {
        $root = $zones[0].name
        $autoDomain = "sg.$root"
        if (Attach-Domain -accountId $accountId -projectName $ProjectName -domain $autoDomain) { Write-Host "Domain attached: $autoDomain" }
    }
}

# Attach explicitly provided Domain1/Domain2 even if zone lookup failed
if ($Domain1 -and $Domain1.Length -gt 0) {
    if (Attach-Domain -accountId $accountId -projectName $ProjectName -domain $Domain1) { Write-Host "Domain attached: $Domain1" }
}
if ($Domain2 -and $Domain2.Length -gt 0) {
    if (Attach-Domain -accountId $accountId -projectName $ProjectName -domain $Domain2) { Write-Host "Domain attached: $Domain2" }
}

# Show project URLs
try {
    $projInfo = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects/$ProjectName" -Headers $Headers
    if ($projInfo.success) {
        $domains = $projInfo.result.domains
        if ($domains -and $domains.Count -gt 0) {
            Write-Host ("Domains: " + ($domains -join ', '))
        } else {
            Write-Host ("Default Pages domain: https://$ProjectName.pages.dev")
        }
        # Fetch latest deployment to show preview URL
        $deps = Invoke-RestMethod -Method GET -Uri "https://api.cloudflare.com/client/v4/accounts/$accountId/pages/projects/$ProjectName/deployments" -Headers $Headers
        if ($deps.success -and $deps.result.Count -gt 0) {
            $latest = $deps.result[0]
            if ($latest.urls -and $latest.urls.preview) { Write-Host ("Latest Preview: " + $latest.urls.preview) }
        }
    }
} catch { Write-Warning "Unable to fetch project URLs: $_" }

Write-Host "All done"
