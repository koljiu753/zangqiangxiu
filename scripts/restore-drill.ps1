[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory,
    [switch]$KeepTemporaryTargets
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupDir = (Resolve-Path $BackupDirectory).Path
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopDocker) { $docker = Get-Item -LiteralPath $desktopDocker }
    else { throw "docker was not found; install Docker Desktop and restart the terminal" }
}
$manifestPath = Join-Path $backupDir "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "manifest.json not found in $backupDir" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$postgresFile = Join-Path $backupDir $manifest.postgresFile
$minioDir = Join-Path $backupDir $manifest.minioDirectory
$actualHash = (Get-FileHash $postgresFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.postgresSha256) { throw "PostgreSQL backup checksum mismatch" }

if ($manifest.formatVersion -ge 2) {
    $listedObjects = @($manifest.minioObjects)
    if ($listedObjects.Count -ne [int]$manifest.minioObjectCount) { throw "MinIO manifest object count mismatch" }
    foreach ($object in $listedObjects) {
        $objectPath = [IO.Path]::GetFullPath((Join-Path $minioDir ([string]$object.path)))
        if (-not $objectPath.StartsWith([IO.Path]::GetFullPath($minioDir) + [IO.Path]::DirectorySeparatorChar)) {
            throw "Unsafe MinIO object path in manifest: $($object.path)"
        }
        if (-not (Test-Path -LiteralPath $objectPath -PathType Leaf)) { throw "MinIO backup object missing: $($object.path)" }
        $file = Get-Item -LiteralPath $objectPath
        if ($file.Length -ne [long]$object.bytes) { throw "MinIO backup object size mismatch: $($object.path)" }
        $hash = (Get-FileHash -LiteralPath $objectPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $object.sha256) { throw "MinIO backup object checksum mismatch: $($object.path)" }
    }
}

$suffix = ([guid]::NewGuid().ToString("N")).Substring(0, 10)
$tempDatabase = "zhixiu_restore_$suffix"
$tempBucket = "zhixiu-restore-$suffix"
$containerDump = "/tmp/$tempDatabase.dump"
$databaseCreated = $false
$bucketCreated = $false

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $docker.FullName @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker command failed with exit code $LASTEXITCODE" }
}

Push-Location $projectRoot
try {
    $postgresContainer = (& $docker.FullName compose ps -q postgres).Trim()
    if (-not $postgresContainer) { throw "postgres service is not running" }
    Invoke-Docker cp $postgresFile "${postgresContainer}:$containerDump"
    Invoke-Docker compose exec -T postgres sh -ec ('createdb -U "$POSTGRES_USER" ''{0}''' -f $tempDatabase)
    $databaseCreated = $true
    Invoke-Docker compose exec -T postgres sh -ec ('pg_restore -U "$POSTGRES_USER" -d ''{0}'' --no-owner --no-privileges ''{1}''' -f $tempDatabase, $containerDump)
    $tableCount = (& $docker.FullName compose exec -T postgres sh -ec ('psql -U "$POSTGRES_USER" -d ''{0}'' -Atc "select count(*) from information_schema.tables where table_schema=''public'';"' -f $tempDatabase)).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$tableCount -lt 1) { throw "restored database has no public tables" }

    $mountPath = $minioDir.Replace('\', '/')
    $restoreObjectsCommand = 'mc alias set target http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mb "target/{0}" >/dev/null; mc mirror /backup "target/{0}" >/dev/null; count=$(mc ls --recursive "target/{0}" | wc -l); test "$count" -eq ''{1}''' -f $tempBucket, $manifest.minioObjectCount
    # Mark it before invocation so finally also attempts cleanup if mirroring or validation fails.
    # The generated prefix guarantees this can never target the live bucket.
    $bucketCreated = $true
    Invoke-Docker compose run --rm --no-deps --entrypoint /bin/sh --volume "${mountPath}:/backup:ro" minio-init -ec $restoreObjectsCommand

    Write-Host "Restore drill passed."
    Write-Host "Temporary database: $tempDatabase ($tableCount public tables)"
    Write-Host "Temporary bucket: $tempBucket ($($manifest.minioObjectCount) objects)"
}
finally {
    if (-not $KeepTemporaryTargets) {
        if ($databaseCreated) {
            & $docker.FullName compose exec -T postgres sh -ec ('dropdb -U "$POSTGRES_USER" --if-exists ''{0}''' -f $tempDatabase) | Out-Null
        }
        & $docker.FullName compose exec -T postgres rm -f $containerDump 2>$null
        if ($bucketCreated) {
            & $docker.FullName compose run --rm --no-deps --entrypoint /bin/sh minio-init -ec ('mc alias set target http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc rb --force "target/{0}" >/dev/null' -f $tempBucket) | Out-Null
        }
        Write-Host "Temporary restore targets removed."
    }
    else {
        Write-Warning "Temporary targets were kept by request: database=$tempDatabase bucket=$tempBucket"
    }
    Pop-Location
}
