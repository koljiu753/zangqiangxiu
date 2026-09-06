[CmdletBinding()]
param(
    [string]$CatalogBaseUrl = "http://127.0.0.1:8001/api/v1",
    [string]$AiBaseUrl = "http://127.0.0.1:8002/v1",
    [switch]$Repair,
    [int]$HttpTimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $name, $value = $line -split '=', 2
        $name = $name.Trim()
        if ($name) { $values[$name] = $value.Trim().Trim('"').Trim("'") }
    }
    return $values
}

$dotenv = Read-DotEnv (Join-Path $projectRoot ".env")
$catalogToken = if ($env:CATALOG_ADMIN_TOKEN) { $env:CATALOG_ADMIN_TOKEN } else { $dotenv["CATALOG_ADMIN_TOKEN"] }
$aiToken = if ($env:ZHIXIU_AI_INTERNAL_TOKEN) { $env:ZHIXIU_AI_INTERNAL_TOKEN } elseif ($env:AI_INTERNAL_TOKEN) { $env:AI_INTERNAL_TOKEN } else { $dotenv["AI_INTERNAL_TOKEN"] }
if (-not $catalogToken) { throw "Catalog admin token is not configured in the environment or project .env" }
if (-not $aiToken) { throw "AI internal token is not configured in the environment or project .env" }

$catalogHeaders = @{ "X-Admin-Token" = $catalogToken }
$aiHeaders = @{ "X-Service-Token" = $aiToken }
$CatalogBaseUrl = $CatalogBaseUrl.TrimEnd('/')
$AiBaseUrl = $AiBaseUrl.TrimEnd('/')

function Invoke-JsonRequest {
    param([string]$Uri, [hashtable]$Headers, [string]$Method = "GET", [object]$Body)
    $parameters = @{ Uri = $Uri; Headers = $Headers; Method = $Method; TimeoutSec = $HttpTimeoutSeconds }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = $Body | ConvertTo-Json -Depth 5 -Compress
    }
    try { return Invoke-RestMethod @parameters }
    catch { throw "HTTP request failed for $Method $Uri (credentials omitted): $($_.Exception.Message)" }
}

function Get-CatalogPatterns {
    $records = [System.Collections.Generic.List[object]]::new()
    $page = 1
    do {
        $response = Invoke-JsonRequest -Uri "$CatalogBaseUrl/admin/patterns?page=$page&pageSize=100" -Headers $catalogHeaders
        foreach ($item in $response.items) { $records.Add($item) }
        $pages = [int]$response.pages
        $page++
    } while ($page -le $pages)
    return $records.ToArray()
}

function Get-ConsistencyReport {
    $catalog = @(Get-CatalogPatterns)
    $referenceResponse = Invoke-JsonRequest -Uri "$AiBaseUrl/references?scope=internal" -Headers $aiHeaders
    $references = @($referenceResponse | ForEach-Object { $_ })
    $catalogById = @{}
    foreach ($pattern in $catalog) { $catalogById[[string]$pattern.id] = $pattern }
    $referencesByPattern = @{}
    foreach ($reference in $references) {
        $patternId = [string]$reference.pattern_id
        if (-not $patternId -or -not $catalogById.ContainsKey($patternId)) { continue }
        if (-not $referencesByPattern.ContainsKey($patternId)) { $referencesByPattern[$patternId] = [System.Collections.Generic.List[object]]::new() }
        $referencesByPattern[$patternId].Add($reference)
    }

    $missing = [System.Collections.Generic.List[object]]::new()
    $mismatch = [System.Collections.Generic.List[object]]::new()
    $orphan = [System.Collections.Generic.List[object]]::new()
    foreach ($pattern in $catalog) {
        $patternId = [string]$pattern.id
        if (-not $referencesByPattern.ContainsKey($patternId)) {
            $missing.Add([pscustomobject]@{ patternId = $patternId; catalogStatus = $pattern.status; catalogVisibility = $pattern.visibility })
            continue
        }
        $shouldPublish = $pattern.status -eq "published" -and $pattern.visibility -eq "public"
        $expectedReview = if ($shouldPublish) { "approved" } else { "draft" }
        $expectedVisibility = if ($shouldPublish) { "public" } else { "internal_only" }
        foreach ($reference in $referencesByPattern[$patternId]) {
            if ($reference.review_status -ne $expectedReview -or $reference.visibility -ne $expectedVisibility) {
                $mismatch.Add([pscustomobject]@{
                    patternId = $patternId; assetId = $reference.asset_id; expectedPublished = $shouldPublish
                    actualReview = $reference.review_status; actualVisibility = $reference.visibility
                })
            }
        }
    }
    foreach ($reference in $references) {
        $patternId = [string]$reference.pattern_id
        if (-not $patternId -or -not $catalogById.ContainsKey($patternId)) {
            $orphan.Add([pscustomobject]@{ patternId = $(if ($patternId) { $patternId } else { "<none>" }); assetId = $reference.asset_id })
        }
    }
    return [pscustomobject]@{ catalog = $catalog; references = $references; missing = $missing; mismatch = $mismatch; orphan = $orphan }
}

function Write-Report {
    param($Report, [string]$Heading)
    Write-Host $Heading -ForegroundColor Cyan
    Write-Host "Catalog=$(@($Report.catalog).Count) AI references=$(@($Report.references).Count) missing=$($Report.missing.Count) mismatch=$($Report.mismatch.Count) orphan=$($Report.orphan.Count)"
    foreach ($item in $Report.missing) { Write-Host "[missing] pattern=$($item.patternId) catalog=$($item.catalogStatus)/$($item.catalogVisibility)" -ForegroundColor Yellow }
    foreach ($item in $Report.mismatch) { Write-Host "[mismatch] pattern=$($item.patternId) asset=$($item.assetId) actual=$($item.actualReview)/$($item.actualVisibility) expectedPublished=$($item.expectedPublished)" -ForegroundColor Yellow }
    foreach ($item in $Report.orphan) { Write-Host "[orphan] pattern=$($item.patternId) asset=$($item.assetId)" -ForegroundColor Yellow }
}

$report = Get-ConsistencyReport
Write-Report $report "Catalog / AI consistency report (read-only check)"

if ($Repair -and $report.mismatch.Count -gt 0) {
    $repairs = @($report.mismatch | Group-Object patternId)
    foreach ($group in $repairs) {
        $item = $group.Group[0]
        $encodedId = [Uri]::EscapeDataString($item.patternId)
        $null = Invoke-JsonRequest -Uri "$AiBaseUrl/internal/references/by-pattern/$encodedId/publication" -Headers $aiHeaders -Method "PUT" -Body @{ published = [bool]$item.expectedPublished }
        Write-Host "[repaired] pattern=$($item.patternId) AI publication state aligned to Catalog"
    }
    $report = Get-ConsistencyReport
    Write-Report $report "Post-repair consistency report"
}

$driftCount = $report.missing.Count + $report.mismatch.Count + $report.orphan.Count
if ($driftCount -gt 0) { exit 2 }
Write-Host "Catalog and AI reference states are consistent." -ForegroundColor Green
exit 0
