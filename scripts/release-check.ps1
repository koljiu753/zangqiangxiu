[CmdletBinding()]
param(
    [switch]$SkipContainerBuild,
    [string]$PythonExecutable,
    [string]$EnvironmentFile,
    [switch]$Production
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
if (-not $EnvironmentFile) { $EnvironmentFile = Join-Path $root ".env" }
$version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+([+-][0-9A-Za-z.-]+)?$') {
    throw "VERSION must be a semantic version; found '$version'"
}

function Invoke-Step {
    param([string]$Name, [string]$WorkingDirectory, [string]$Command, [string[]]$Arguments)
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

Write-Host "Zhixiu release gate v$version" -ForegroundColor Green
& (Join-Path $PSScriptRoot "preflight.ps1") -EnvironmentFile $EnvironmentFile -Production:$Production

if (-not $PythonExecutable) {
    $releasePython = Join-Path $root ".release-venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $releasePython) { $releasePython } else { "python" }
}
Invoke-Step "Catalog tests" (Join-Path $root "catalog-service") $PythonExecutable @("-m", "pytest", "-q")
Invoke-Step "AI tests" (Join-Path $root "ai-service") $PythonExecutable @("-m", "pytest", "-q")
Invoke-Step "Data tests" (Join-Path $root "data") $PythonExecutable @("-m", "unittest", "discover", "-s", "tests", "-v")
Invoke-Step "Web tests" (Join-Path $root "web") "npm.cmd" @("test", "--", "--run")
Invoke-Step "Web lint" (Join-Path $root "web") "npm.cmd" @("run", "lint")
Invoke-Step "Web production build" (Join-Path $root "web") "npm.cmd" @("run", "build")
Invoke-Step "Web production dependency audit" (Join-Path $root "web") "npm.cmd" @("audit", "--omit=dev", "--audit-level=high", "--registry=https://registry.npmjs.org")

if (-not $SkipContainerBuild) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
        if (Test-Path -LiteralPath $desktopDocker) { $docker = Get-Item -LiteralPath $desktopDocker }
        else { throw "docker was not found; install Docker Desktop and restart the terminal" }
    }
    $buildArguments = @("compose", "--env-file", $EnvironmentFile, "-f", (Join-Path $root "compose.yaml"))
    if ($Production) { $buildArguments += @("-f", (Join-Path $root "compose.production.yaml")) }
    $buildArguments += "build"
    Invoke-Step "Container image build" $root $docker.FullName $buildArguments
}

Write-Host "`nRelease gate passed for v$version." -ForegroundColor Green
