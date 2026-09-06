[CmdletBinding()]
param(
    [string]$EnvironmentFile = (Join-Path $PSScriptRoot "..\.env"),
    [string]$ComposeFile = (Join-Path $PSScriptRoot "..\compose.yaml")
)

$ErrorActionPreference = "Stop"
$requiredKeys = @(
    "CATALOG_ADMIN_TOKEN", "AI_INTERNAL_TOKEN", "ADMIN_UI_USER",
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
    } elseif ($values[$key] -match '(?i)change-me|replace-me|请替换') {
        $problems.Add("$key still contains a placeholder")
    }
}
if ($values.ContainsKey("AUTH_SESSION_SECRET") -and $values["AUTH_SESSION_SECRET"].Length -lt 32) {
    $problems.Add("AUTH_SESSION_SECRET must contain at least 32 characters")
}
foreach ($key in @("CATALOG_ADMIN_TOKEN", "AI_INTERNAL_TOKEN", "POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD", "AI_S3_SECRET_KEY", "CATALOG_S3_SECRET_KEY")) {
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
& $docker.FullName compose --project-directory $projectDirectory --env-file $envPath -f $composePath config --quiet
if ($LASTEXITCODE -ne 0) { throw "docker compose config validation failed" }

Write-Host "[PASS] Environment contains all required non-placeholder secrets."
Write-Host "[PASS] Docker Compose configuration is valid."
