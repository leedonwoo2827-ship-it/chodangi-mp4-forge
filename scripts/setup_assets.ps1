[CmdletBinding()]
param(
  [switch]$Force,
  [string]$Repo = "https://huggingface.co/Supertone/supertonic-3"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $root "assets"
# 존재 판정은 assets 폴더가 아니라 '실제 모델 파일' 로 한다.
# assets\ 는 fonts 때문에 이미 있을 수 있어, 폴더만 보면 다운로드를 건너뛰어 버린다.
$modelFile = Join-Path $assets "onnx\vocoder.onnx"

Write-Host "voicewright setup_assets" -ForegroundColor Cyan
Write-Host ("  repo:   " + $Repo)
Write-Host ("  target: " + $assets)
Write-Host ("  model:  " + $modelFile)

if ((Test-Path $modelFile) -and -not $Force) {
  Write-Host "model already present (assets\onnx\vocoder.onnx). Use -Force to re-download." -ForegroundColor Yellow
  exit 0
}

$null = & git --version
if ($LASTEXITCODE -ne 0) { throw "git not found. Install from https://git-scm.com" }

Write-Host "Initializing git-lfs ..." -ForegroundColor Cyan
& git lfs install
if ($LASTEXITCODE -ne 0) { throw "git-lfs required. Install from https://git-lfs.com and re-run." }

# 임시 폴더로 clone 한 뒤 assets\ 로 '병합' 한다.
# (assets\ 를 통째로 지우면 fonts 등 기존 자산이 날아가고, git clone 은 비어있지 않은
#  폴더로는 clone 이 안 되므로 임시 clone -> 병합이 안전하다.)
$tmp = Join-Path $root "_supertonic_dl"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }

Write-Host "Downloading model from Hugging Face (1-2 GB, may take a while) ..." -ForegroundColor Cyan
& git clone $Repo $tmp
if ($LASTEXITCODE -ne 0) {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  throw "git clone failed."
}

Write-Host "Merging model into assets\ (기존 fonts 등은 보존) ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $assets | Out-Null
Get-ChildItem -Force $tmp | Where-Object { $_.Name -ne ".git" } | ForEach-Object {
  Copy-Item -Recurse -Force -Path $_.FullName -Destination $assets
}
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

# 다운로드 후 실제 모델 파일을 확인한다(git-lfs 가 포인터만 받고 실파일을 못 받는 경우 방지).
if (-not (Test-Path $modelFile)) {
  throw "download finished but model file is missing: $modelFile`n" +
        "  git-lfs 가 실제 파일을 받지 못했을 수 있습니다. 'git lfs install' 확인 후 -Force 로 다시 실행하세요."
}
Write-Host ("model OK: " + $modelFile) -ForegroundColor Green

$voiceDir = Join-Path $assets "voice_styles"
if (Test-Path $voiceDir) {
  Write-Host "`nAvailable voice presets:" -ForegroundColor Green
  Get-ChildItem $voiceDir -Filter *.json | ForEach-Object { Write-Host ("  - " + $_.Name) }
} else {
  Write-Host "Warning: voice_styles directory not found in cloned repo." -ForegroundColor Yellow
}

Write-Host "`nNext step: voicewright doctor" -ForegroundColor Green
