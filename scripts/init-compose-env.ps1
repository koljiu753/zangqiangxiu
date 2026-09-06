param([string]$OutputPath)

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
if (-not $OutputPath) { $OutputPath = Join-Path $resolvedRoot ".env" }
$fullOutput = [IO.Path]::GetFullPath($OutputPath)
if (-not $fullOutput.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw "Output must stay inside the project directory"
}
function New-Secret([int]$Bytes = 32) {
    $buffer = [byte[]]::new($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToHexString($buffer).ToLowerInvariant()
}

if (Test-Path -LiteralPath $fullOutput) {
    $existing = Get-Content -LiteralPath $fullOutput -Raw
    $additions = [Collections.Generic.List[string]]::new()
    if ($existing -notmatch '(?m)^CATALOG_ACTOR_SIGNING_SECRET=') { $additions.Add("CATALOG_ACTOR_SIGNING_SECRET=$(New-Secret 32)") }
    if ($existing -notmatch '(?m)^CATALOG_S3_ACCESS_KEY=') { $additions.Add("CATALOG_S3_ACCESS_KEY=zhixiu-catalog") }
    if ($existing -notmatch '(?m)^CATALOG_S3_SECRET_KEY=') { $additions.Add("CATALOG_S3_SECRET_KEY=$(New-Secret 24)") }
    if ($existing -notmatch '(?m)^CATALOG_S3_PREFIX=') { $additions.Add("CATALOG_S3_PREFIX=production/catalog-evidence") }
    if ($existing -notmatch '(?m)^CATALOG_EVIDENCE_MAX_BYTES=') { $additions.Add("CATALOG_EVIDENCE_MAX_BYTES=10485760") }
    if ($additions.Count -gt 0) {
        [IO.File]::AppendAllText($fullOutput, "`n" + ($additions -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
        Write-Output "Added newly required Catalog settings to: $fullOutput"
    } else {
        Write-Output "Environment file already exists and is current: $fullOutput"
    }
    exit 0
}

$adminPassword = New-Secret 16
$content = @(
    "COMPOSE_PROJECT_NAME=zhixiu"
    "PUBLIC_WEB_ORIGIN=http://localhost:3000"
    "PUBLIC_CATALOG_API_BASE_URL=http://localhost:8001/api/v1"
    "PUBLIC_AI_API_BASE_URL=http://localhost:8002/v1"
    "CATALOG_ADMIN_TOKEN=$(New-Secret 32)"
    "CATALOG_ACTOR_SIGNING_SECRET=$(New-Secret 32)"
    "AI_INTERNAL_TOKEN=$(New-Secret 32)"
    "ADMIN_UI_USER=admin"
    "ADMIN_UI_PASSWORD=$adminPassword"
    "AUTH_SESSION_SECRET=$(New-Secret 48)"
    "POSTGRES_DB=zhixiu"
    "POSTGRES_USER=zhixiu"
    "POSTGRES_PASSWORD=$(New-Secret 24)"
    "MINIO_ROOT_USER=zhixiu-minio"
    "MINIO_ROOT_PASSWORD=$(New-Secret 24)"
    "AI_S3_ACCESS_KEY=zhixiu-ai"
    "AI_S3_SECRET_KEY=$(New-Secret 24)"
    "AI_S3_BUCKET=zhixiu-assets"
    "AI_S3_REGION=us-east-1"
    "AI_S3_PREFIX=production/ai-assets"
    "CATALOG_S3_ACCESS_KEY=zhixiu-catalog"
    "CATALOG_S3_SECRET_KEY=$(New-Secret 24)"
    "CATALOG_S3_PREFIX=production/catalog-evidence"
    "CATALOG_EVIDENCE_MAX_BYTES=10485760"
    "AI_ENVIRONMENT=development"
)
[IO.File]::WriteAllLines($fullOutput, $content, [Text.UTF8Encoding]::new($false))
Write-Output "Created environment file: $fullOutput"
Write-Output "Local admin user: admin"
Write-Output "Local admin password: $adminPassword"
