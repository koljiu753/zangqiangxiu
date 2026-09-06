$ErrorActionPreference = "Stop"
$preflight = Join-Path $PSScriptRoot "..\preflight.ps1"
$temporary = Join-Path ([IO.Path]::GetTempPath()) ("zhixiu-preflight-{0}.env" -f [Guid]::NewGuid())
$base = @"
CATALOG_ADMIN_TOKEN=abcdefghijklmnopqrstuvwxyz123456
CATALOG_ACTOR_SIGNING_SECRET=abcdefghijklmnopqrstuvwxyz123456
AI_INTERNAL_TOKEN=abcdefghijklmnopqrstuvwxyz123456
ADMIN_UI_USER=admin
ADMIN_UI_PASSWORD=abcdefghijklmnopqrstuvwxyz123456
AUTH_SESSION_SECRET=abcdefghijklmnopqrstuvwxyz123456
ADMIN_UI_ROLE=reviewer
ADMIN_TRUST_PROXY=false
POSTGRES_DB=zhixiu
POSTGRES_USER=zhixiu
POSTGRES_PASSWORD=abcdefghijklmnopqrstuvwxyz123456
MINIO_ROOT_USER=bootstrap
MINIO_ROOT_PASSWORD=abcdefghijklmnopqrstuvwxyz123456
AI_S3_ACCESS_KEY=ai-service
AI_S3_SECRET_KEY=abcdefghijklmnopqrstuvwxyz123456
CATALOG_S3_ACCESS_KEY=catalog-service
CATALOG_S3_SECRET_KEY=abcdefghijklmnopqrstuvwxyz123456
PUBLIC_WEB_ORIGIN=https://patterns.example.org
PUBLIC_CATALOG_API_BASE_URL=https://patterns.example.org/api/catalog/v1
PUBLIC_AI_API_BASE_URL=https://patterns.example.org/api/ai/v1
S3_ENDPOINT_URL=https://s3.example.org
"@

try {
    Set-Content -LiteralPath $temporary -Value $base -Encoding utf8NoBOM
    & $preflight -EnvironmentFile $temporary -Production
    if ($LASTEXITCODE -ne 0) { throw "Expected valid production configuration to pass" }

    Set-Content -LiteralPath $temporary -Value ($base.Replace("https://s3.example.org", "http://s3.example.org")) -Encoding utf8NoBOM
    $failedClosed = $false
    try { & $preflight -EnvironmentFile $temporary -Production } catch {
        $failedClosed = $_.Exception.Message -match "S3_ENDPOINT_URL must use https://"
    }
    if (-not $failedClosed) { throw "Expected insecure production S3 endpoint to fail closed" }
    Write-Host "[PASS] Production preflight accepts secure configuration and rejects HTTP S3."
} finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
}
