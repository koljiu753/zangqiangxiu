[CmdletBinding()]
param(
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $projectRoot "backups" }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopDocker) { $docker = Get-Item -LiteralPath $desktopDocker }
    else { throw "docker was not found; install Docker Desktop and restart the terminal" }
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path ([System.IO.Path]::GetFullPath($OutputRoot)) $stamp
$postgresFile = Join-Path $backupDir "postgres.dump"
$minioDir = Join-Path $backupDir "minio"
$tempDump = "/tmp/zhixiu-backup-$stamp.dump"

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $docker.FullName @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker command failed with exit code $LASTEXITCODE" }
}

function Read-DotEnvValue {
    param([string]$Name, [string]$Default)
    $envFile = Join-Path $projectRoot ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
        if ($line) { return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'") }
    }
    return $Default
}

New-Item -ItemType Directory -Path $backupDir, $minioDir -Force | Out-Null
Push-Location $projectRoot
try {
    $postgresContainer = (& $docker.FullName compose ps -q postgres).Trim()
    if (-not $postgresContainer) { throw "postgres service is not running" }

    $dumpCommand = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=9 --file=''{0}''' -f $tempDump
    Invoke-Docker compose exec -T postgres sh -ec $dumpCommand
    Invoke-Docker cp "${postgresContainer}:$tempDump" $postgresFile
    Invoke-Docker compose exec -T postgres rm -f $tempDump

    $bucket = Read-DotEnvValue "AI_S3_BUCKET" "zhixiu-assets"
    $mountPath = $minioDir.Replace('\', '/')
    $mirrorCommand = 'mc alias set source http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mirror --overwrite "source/{0}" /backup' -f $bucket
    Invoke-Docker compose run --rm --no-deps --entrypoint /bin/sh --volume "${mountPath}:/backup" minio-init -ec $mirrorCommand

    $objectFiles = @(Get-ChildItem $minioDir -Recurse -File)
    $objectManifest = @($objectFiles | ForEach-Object {
        $relativePath = $_.FullName.Substring($minioDir.Length).TrimStart([char[]]"\/")
        [ordered]@{
            path = $relativePath.Replace('\', '/')
            bytes = $_.Length
            sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    $manifest = [ordered]@{
        formatVersion = 2
        createdAt = (Get-Date).ToUniversalTime().ToString("o")
        postgresFile = "postgres.dump"
        postgresSha256 = (Get-FileHash $postgresFile -Algorithm SHA256).Hash.ToLowerInvariant()
        minioBucket = $bucket
        minioDirectory = "minio"
        minioObjectCount = $objectFiles.Count
        minioBytes = ($objectFiles | Measure-Object Length -Sum).Sum
        minioObjects = $objectManifest
    }
    $manifest | ConvertTo-Json | Set-Content (Join-Path $backupDir "manifest.json") -Encoding utf8
    Write-Host "Backup completed: $backupDir"
    Write-Host "PostgreSQL SHA-256: $($manifest.postgresSha256)"
    Write-Host "MinIO objects: $($manifest.minioObjectCount)"
}
finally {
    Pop-Location
}
