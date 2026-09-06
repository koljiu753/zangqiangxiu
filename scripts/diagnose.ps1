[CmdletBinding()]
param(
    [string]$ComposeFile,
    [int]$Tail = 120,
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ComposeFile) { $ComposeFile = Join-Path $scriptDirectory "..\compose.yaml" }
$composePath = (Resolve-Path -LiteralPath $ComposeFile).Path
$projectDirectory = Split-Path -Parent $composePath
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectDirectory ("diagnostics\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$composeArgs = @("compose", "--project-directory", $projectDirectory, "-f", $composePath)

function Save-CommandOutput {
    param([string]$FileName, [scriptblock]$Command)
    try {
        $content = & $Command 2>&1
        $exitCode = $LASTEXITCODE
        @("exit_code=$exitCode", "captured_at=$((Get-Date).ToString('o'))", "", ($content -join "`n")) |
            Set-Content -LiteralPath (Join-Path $outputPath $FileName) -Encoding utf8
    } catch {
        @("capture_error=$($_.Exception.Message)", "captured_at=$((Get-Date).ToString('o'))") |
            Set-Content -LiteralPath (Join-Path $outputPath $FileName) -Encoding utf8
    }
}

Write-Host "Collecting diagnostics in $outputPath" -ForegroundColor Cyan
Save-CommandOutput "docker-info.txt" { docker info }
Save-CommandOutput "compose-ps.txt" { docker @composeArgs ps --all }
Save-CommandOutput "compose-images.txt" { docker @composeArgs images }
Save-CommandOutput "compose-logs.txt" { docker @composeArgs logs --no-color --timestamps --tail $Tail }
Save-CommandOutput "docker-disk-usage.txt" { docker system df }

$services = @("postgres", "minio", "catalog", "ai", "web")
foreach ($service in $services) {
    Save-CommandOutput "$service-inspect.txt" {
        $id = (& docker @composeArgs ps -q $service 2>$null | Select-Object -First 1)
        if (-not $id) { throw "Container for service '$service' was not found." }
        docker inspect --format '{{json .State}}' $id
    }
}

$healthLog = Join-Path $outputPath "health-check.txt"
& (Join-Path $scriptDirectory "health-check.ps1") -ComposeFile $composePath *>&1 |
    Set-Content -LiteralPath $healthLog -Encoding utf8
$healthExitCode = $LASTEXITCODE

@"
Zhixiu diagnostics bundle
Captured: $((Get-Date).ToString('o'))
Compose file: $composePath
Log tail: $Tail lines per service
Health exit code: $healthExitCode

The bundle intentionally excludes compose config and container environment variables
because they can contain database, object-storage, admin, and session secrets.
"@ | Set-Content -LiteralPath (Join-Path $outputPath "README.txt") -Encoding utf8

Write-Host "Diagnostics collected: $outputPath" -ForegroundColor Green
Write-Host "Health check exit code: $healthExitCode"
exit $healthExitCode
