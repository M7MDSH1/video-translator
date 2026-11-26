<#
.SYNOPSIS
  Sets up Video Translator in this folder: Python packages, FFmpeg, offline models, Ollama model and a shortcut.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Cpu            # no NVIDIA GPU
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -CheckOnly      # only report what is missing
#>
param(
  [switch]$Cpu,                    # install CPU-only PyTorch (no NVIDIA GPU)
  [switch]$SkipModels,             # skip Whisper / EasyOCR / Ollama model downloads
  [string]$Model = 'gemma4:12b',   # Ollama translation model to pull
  [switch]$CheckOnly               # report status, change nothing
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

Step 'Checking what is installed'
$python = $null
if (Has 'py') { try { & py -3.12 -c "print()" *> $null; if ($LASTEXITCODE -eq 0) { $python = @('py', '-3.12') } } catch {} }
$ffmpeg = (Test-Path 'runtime\ffmpeg\bin\ffmpeg.exe') -or (Has 'ffmpeg')
$ollama = Has 'ollama'
$gpu = (-not $Cpu) -and (Has 'nvidia-smi')
Write-Host ("Python 3.12 : " + $(if ($python -or (Test-Path $venvPython)) { 'found' } else { 'MISSING' }))
Write-Host ("FFmpeg      : " + $(if ($ffmpeg) { 'found' } else { 'missing (will install with winget)' }))
Write-Host ("Ollama      : " + $(if ($ollama) { 'found' } else { 'MISSING' }))
Write-Host ("PyTorch     : " + $(if ($gpu) { 'NVIDIA GPU (CUDA 12.8)' } else { 'CPU only' }))
if ($CheckOnly) { return }

if (-not $python -and -not (Test-Path $venvPython)) {
  throw 'Python 3.12 is required. Install it with:  winget install Python.Python.3.12  then run this script again.'
}

Step 'Creating the Python environment (.venv)'
if (-not (Test-Path $venvPython)) { & $python[0] $python[1] -m venv .venv; if ($LASTEXITCODE) { throw 'Could not create .venv' } }
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE) { throw 'pip upgrade failed' }

Step 'Installing Python packages (PyTorch is a large download)'
if ($gpu) {
  & $venvPython -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cu128
} else {
  & $venvPython -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
  if ($LASTEXITCODE) { throw 'PyTorch install failed' }
  & $venvPython -m pip install -r requirements.txt
}
if ($LASTEXITCODE) { throw 'Package install failed' }

if (-not $ffmpeg) {
  Step 'Installing FFmpeg (full build with libass, from winget)'
  if (-not (Has 'winget')) { throw 'FFmpeg is missing and winget is not available. Put ffmpeg.exe and ffprobe.exe in runtime\ffmpeg\bin.' }
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  Write-Host 'FFmpeg installed. Open a NEW terminal (or sign out and in) so it is on PATH before starting the app.' -ForegroundColor Yellow
}

if (-not $SkipModels) {
  Step 'Downloading offline speech and subtitle-reading models'
  & $venvPython setup_models.py
  if ($LASTEXITCODE) { throw 'Model download failed' }
  if ($ollama) {
    Step "Pulling the translation model $Model with Ollama"
    ollama pull $Model
    if ($LASTEXITCODE) { Write-Host "Could not pull $Model. Start Ollama and run:  ollama pull $Model" -ForegroundColor Yellow }
  }
}
if (-not $ollama) {
  Write-Host "`nOllama is required for translation. Install it with:  winget install Ollama.Ollama" -ForegroundColor Yellow
  Write-Host "Then run:  ollama pull $Model" -ForegroundColor Yellow
}

Step 'Creating the Video Translator shortcut'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $PSScriptRoot 'Video Translator.lnk'))
$link.TargetPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$link.Arguments = '-m videotranslator.app'
$link.WorkingDirectory = $PSScriptRoot
$link.IconLocation = (Join-Path $PSScriptRoot 'assets\video-translator.ico') + ',0'
$link.Save()

Write-Host "`nDone. Start the app with 'Video Translator.lnk' or 'Start Video Translator.bat'." -ForegroundColor Green
