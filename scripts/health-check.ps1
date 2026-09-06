[CmdletBinding()]
param(
    [string]$ComposeFile,
    [string]$EnvironmentFile,
    [int]$HttpTimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ComposeFile) { $ComposeFile = Join-Path $scriptDirectory "..\compose.yaml" }
if (-not $EnvironmentFile) { $EnvironmentFile = Join-Path $scriptDirectory "..\.env" }
$script:Failures = 0
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopDocker) { $docker = Get-Item -LiteralPath $desktopDocker }
}
$script:DockerCommand = if ($docker) { $docker.FullName } else { "docker" }

function Write-CheckResult {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    if ($Passed) {
        Write-Host "[PASS] $Name - $Detail" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red
        $script:Failures++
    }
}

function Invoke-Docker {
    param([string[]]$Arguments)
    $output = & $script:DockerCommand @Arguments 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($output -join "`n") }
}

function Test-HttpEndpoint {
    param([string]$Name, [string]$Uri)
    try {
        $response = Invoke-WebRequest -Uri $Uri -TimeoutSec $HttpTimeoutSeconds -UseBasicParsing
        Write-CheckResult $Name ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) "HTTP $($response.StatusCode)"
    } catch {
        Write-CheckResult $Name $false $_.Exception.Message
    }
}

function Test-HttpStatus {
    param([string]$Name, [string]$Uri, [int]$ExpectedStatus, [string]$ExpectedLocation)
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($HttpTimeoutSeconds)
    try {
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        $statusMatches = [int]$response.StatusCode -eq $ExpectedStatus
        $location = if ($response.Headers.Location) { $response.Headers.Location.ToString() } else { "" }
        $locationMatches = -not $ExpectedLocation -or $location -eq $ExpectedLocation
        Write-CheckResult $Name ($statusMatches -and $locationMatches) "HTTP $([int]$response.StatusCode), location=$location"
    } catch {
        Write-CheckResult $Name $false $_.Exception.Message
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Test-AnonymousPostStatus {
    param([string]$Name, [string]$Uri, [string]$Json, [int]$ExpectedStatus)
    $client = [Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds($HttpTimeoutSeconds)
    try {
        $content = [Net.Http.StringContent]::new($Json, [Text.Encoding]::UTF8, "application/json")
        $response = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        Write-CheckResult $Name ([int]$response.StatusCode -eq $ExpectedStatus) "HTTP $([int]$response.StatusCode)"
    } catch {
        Write-CheckResult $Name $false $_.Exception.Message
    } finally { $client.Dispose() }
}

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match ('^\s*' + [Regex]::Escape($Name) + '=(.*)$')) { return $matches[1].Trim().Trim('"').Trim("'") }
    }
    return $null
}

$composePath = (Resolve-Path -LiteralPath $ComposeFile).Path
$projectDirectory = Split-Path -Parent $composePath
$composeArgs = @("compose", "--project-directory", $projectDirectory, "-f", $composePath)

Write-Host "Zhixiu deployment health check" -ForegroundColor Cyan
Write-Host "Compose file: $composePath"

$dockerInfo = Invoke-Docker @("info", "--format", "{{.ServerVersion}}")
Write-CheckResult "Docker daemon" ($dockerInfo.ExitCode -eq 0) $(if ($dockerInfo.ExitCode -eq 0) { "server $($dockerInfo.Output.Trim())" } else { $dockerInfo.Output.Trim() })
if ($dockerInfo.ExitCode -ne 0) { exit 1 }

$expectedServices = @("postgres", "minio", "catalog", "ai", "web")
$containerIdsResult = Invoke-Docker ($composeArgs + @("ps", "-q"))
if ($containerIdsResult.ExitCode -ne 0) {
    Write-CheckResult "Compose project" $false $containerIdsResult.Output.Trim()
    exit 1
}

foreach ($service in $expectedServices) {
    $idResult = Invoke-Docker ($composeArgs + @("ps", "-q", $service))
    $containerId = $idResult.Output.Trim()
    if ($idResult.ExitCode -ne 0 -or -not $containerId) {
        Write-CheckResult "Container $service" $false "not running"
        continue
    }

    $inspect = Invoke-Docker @("inspect", "--format", "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", $containerId)
    $parts = $inspect.Output.Trim().Split("|", 2)
    $running = $inspect.ExitCode -eq 0 -and $parts[0] -eq "running"
    $health = if ($parts.Count -gt 1) { $parts[1] } else { "unknown" }
    $healthy = $running -and ($health -eq "healthy" -or $health -eq "none")
    Write-CheckResult "Container $service" $healthy "state=$($parts[0]), health=$health"
}

$postgres = Invoke-Docker ($composeArgs + @("exec", "-T", "postgres", "sh", "-ec", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'))
Write-CheckResult "PostgreSQL connectivity" ($postgres.ExitCode -eq 0) $postgres.Output.Trim()

$minio = Invoke-Docker ($composeArgs + @("exec", "-T", "minio", "curl", "-fsS", "http://localhost:9000/minio/health/ready"))
Write-CheckResult "MinIO connectivity" ($minio.ExitCode -eq 0) $(if ($minio.ExitCode -eq 0) { "ready endpoint reachable" } else { $minio.Output.Trim() })

Test-HttpEndpoint "Web" "http://127.0.0.1:3000/"
Test-HttpStatus "Admin authentication redirect" "http://127.0.0.1:3000/admin" 307 "/admin/login?next=%2Fadmin"
Test-HttpEndpoint "Admin login" "http://127.0.0.1:3000/admin/login"
Test-HttpEndpoint "Catalog readiness" "http://127.0.0.1:8001/ready"
Test-HttpEndpoint "AI readiness" "http://127.0.0.1:8002/ready"
Test-AnonymousPostStatus "AI reference registration isolation" "http://127.0.0.1:8002/v1/references" '{"asset_id":"healthcheck-missing","review_status":"approved","visibility":"public"}' 401
Test-AnonymousPostStatus "AI internal analysis isolation" "http://127.0.0.1:8002/v1/analyses" '{"asset_id":"healthcheck-missing","tasks":["similar"],"scope":"internal"}' 401

$adminToken = Read-DotEnvValue $EnvironmentFile "CATALOG_ADMIN_TOKEN"
if ($adminToken) {
    try {
        $adminHeaders = @{ "X-Admin-Token" = $adminToken }
        $draftPage = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v1/admin/patterns?status=draft&pageSize=1" -Headers $adminHeaders -TimeoutSec $HttpTimeoutSeconds
        if (@($draftPage.items).Count -gt 0) {
            $draftId = [Uri]::EscapeDataString([string]$draftPage.items[0].id)
            Test-HttpStatus "Catalog draft isolation" "http://127.0.0.1:8001/api/v1/patterns/$draftId" 404 ""
            Test-HttpStatus "Web draft image isolation" "http://127.0.0.1:3000/patterns/$draftId/image" 404 ""
        } else {
            Write-CheckResult "Draft isolation sample" $true "no draft records currently exist"
        }
    } catch {
        Write-CheckResult "Draft isolation sample" $false $_.Exception.Message
    }
} else {
    Write-CheckResult "Draft isolation sample" $false "CATALOG_ADMIN_TOKEN is unavailable in the environment file"
}

if ($script:Failures -gt 0) {
    Write-Host "Health check failed: $script:Failures check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "All health checks passed." -ForegroundColor Green
exit 0
