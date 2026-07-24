[CmdletBinding()]
param(
  [switch]$Force,
  [string]$Repo = "https://huggingface.co/Supertone/supertonic-3"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $root "assets"

Write-Host "voicewright setup_assets" -ForegroundColor Cyan
Write-Host ("  repo:   " + $Repo)
Write-Host ("  target: " + $assets)

if ((Test-Path $assets) -and -not $Force) {
  Write-Host "assets/ already exists. Use -Force to re-download." -ForegroundColor Yellow
  exit 0
}
if ($Force -and (Test-Path $assets)) {
  Write-Host "Removing existing assets/ ..." -ForegroundColor Yellow
  Remove-Item -Recurse -Force $assets
}

$null = & git --version
if ($LASTEXITCODE -ne 0) { throw "git not found. Install from https://git-scm.com" }

Write-Host "Initializing git-lfs ..." -ForegroundColor Cyan
& git lfs install
if ($LASTEXITCODE -ne 0) { throw "git-lfs required. Install from https://git-lfs.com and re-run." }

Write-Host "Downloading model from Hugging Face (1-2 GB, may take a while) ..." -ForegroundColor Cyan
& git clone $Repo $assets
if ($LASTEXITCODE -ne 0) { throw "git clone failed." }

$voiceDir = Join-Path $assets "voice_styles"
if (Test-Path $voiceDir) {
  Write-Host "`nAvailable voice presets:" -ForegroundColor Green
  Get-ChildItem $voiceDir -Filter *.json | ForEach-Object { Write-Host ("  - " + $_.Name) }
} else {
  Write-Host "Warning: voice_styles directory not found in cloned repo." -ForegroundColor Yellow
}

Write-Host "`nNext step: voicewright doctor" -ForegroundColor Green
