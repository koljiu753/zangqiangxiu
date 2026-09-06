[CmdletBinding()]
param(
    [string]$EnvironmentFile,
    [string]$ComposeFile,
    [switch]$Production
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $EnvironmentFile) { $EnvironmentFile = Join-Path $scriptDirectory "..\.env" }
if (-not $ComposeFile) { $ComposeFile = Join-Path $scriptDirectory "..\compose.yaml" }
$requiredKeys = @(
    "CATALOG_ADMIN_TOKEN", "CATALOG_ACTOR_SIGNING_SECRET", "AI_INTERNAL_TOKEN", "ADMIN_UI_USER",
    "ADMIN_UI_PASSWORD", "AUTH_SESSION_SECRET", "POSTGRES_DB",
    "POSTGRES_USER", "POSTGRES_PASSWORD", "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD", "AI_S3_ACCESS_KEY", "AI_S3_SECRET_KEY",
    "CATALOG_S3_ACCESS_KEY", "CATALOG_S3_SECRET_KEY"
)

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $name, $value = $line -split '=', 2
        $values[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
    }
    return $values
}

$envPath = [IO.Path]::GetFullPath($EnvironmentFile)
$composePath = [IO.Path]::GetFullPath($ComposeFile)
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Environment file not found: $envPath. Run scripts/init-compose-env.ps1 first."
}
if (-not (Test-Path -LiteralPath $composePath)) { throw "Compose file not found: $composePath" }

$values = Read-DotEnv $envPath
$problems = [Collections.Generic.List[string]]::new()
foreach ($key in $requiredKeys) {
    if (-not $values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($values[$key])) {
        $problems.Add("missing $key")
    } elseif ($values[$key] -match '(?i)change-me|replace-me|placeholder') {
        $problems.Add("$key still contains a placeholder")
    }
}
if ($values.ContainsKey("AUTH_SESSION_SECRET") -and $values["AUTH_SESSION_SECRET"].Length -lt 32) {
    $problems.Add("AUTH_SESSION_SECRET must contain at least 32 characters")
}
if ($Production) {
    foreach ($key in @("PUBLIC_WEB_ORIGIN", "PUBLIC_CATALOG_API_BASE_URL", "PUBLIC_AI_API_BASE_URL", "S3_ENDPOINT_URL", "ADMIN_UI_ROLE")) {
        if (-not $values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($values[$key])) {
            $problems.Add("production requires $key")
        }
    }
    foreach ($key in @("PUBLIC_WEB_ORIGIN", "PUBLIC_CATALOG_API_BASE_URL", "PUBLIC_AI_API_BASE_URL", "S3_ENDPOINT_URL")) {
        if ($values.ContainsKey($key) -and $values[$key] -notmatch '^https://') {
            $problems.Add("$key must use https:// in production")
        }
    }
    if ($values.ContainsKey("PUBLIC_WEB_ORIGIN")) {
        try {
            $webOrigin = [Uri]$values["PUBLIC_WEB_ORIGIN"]
            if (-not $webOrigin.IsAbsoluteUri -or $webOrigin.AbsolutePath -ne "/" -or $webOrigin.Query -or $webOrigin.Fragment) {
                $problems.Add("PUBLIC_WEB_ORIGIN must be an origin without a path, query or fragment")
            }
        } catch {
            $problems.Add("PUBLIC_WEB_ORIGIN must be a valid absolute URI")
        }
    }
    if ($values.ContainsKey("ADMIN_UI_ROLE") -and $values["ADMIN_UI_ROLE"] -notin @("reviewer", "publisher")) {
        $problems.Add("ADMIN_UI_ROLE must be reviewer or publisher")
    }
    if ($values.ContainsKey("ADMIN_TRUST_PROXY") -and $values["ADMIN_TRUST_PROXY"] -notin @("true", "false")) {
        $problems.Add("ADMIN_TRUST_PROXY must be true or false")
    }
}
foreach ($key in @("CATALOG_ADMIN_TOKEN", "CATALOG_ACTOR_SIGNING_SECRET", "AI_INTERNAL_TOKEN", "POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD", "AI_S3_SECRET_KEY", "CATALOG_S3_SECRET_KEY")) {
    if ($values.ContainsKey($key) -and $values[$key].Length -lt 24) {
        $problems.Add("$key must contain at least 24 characters")
    }
}
if ($problems.Count -gt 0) { throw ("Environment preflight failed:`n - " + ($problems -join "`n - ")) }

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopDocker) { $docker = Get-Item -LiteralPath $desktopDocker }
    else { throw "docker was not found; install Docker Desktop and restart the terminal" }
}
$projectDirectory = Split-Path -Parent $composePath
$composeArguments = @("compose", "--project-directory", $projectDirectory, "--env-file", $envPath, "-f", $composePath)
if ($Production) {
    $productionCompose = Join-Path $projectDirectory "compose.production.yaml"
    if (-not (Test-Path -LiteralPath $productionCompose)) { throw "Production Compose overlay not found: $productionCompose" }
    $composeArguments += @("-f", $productionCompose)
}
$composeArguments += @("config", "--quiet")
& $docker.FullName @composeArguments
if ($LASTEXITCODE -ne 0) { throw "docker compose config validation failed" }

Write-Host "[PASS] Environment contains all required non-placeholder secrets."
Write-Host "[PASS] Docker Compose configuration is valid."
