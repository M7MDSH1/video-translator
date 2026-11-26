<#
.SYNOPSIS
  Sets up Video Translator in this folder: Python, packages, FFmpeg, offline models, Ollama with its model, and a shortcut.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Cpu            # no NVIDIA GPU
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -CheckOnly      # only report what is missing
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -OllamaOnly     # only install/start Ollama and download the model
#>
param(
  [switch]$Cpu,                    # install CPU-only PyTorch (no NVIDIA GPU)
  [switch]$SkipModels,             # skip Whisper / EasyOCR / Ollama model downloads
  [string]$Model = 'gemma4:12b',   # Ollama translation model to pull
  [switch]$CheckOnly,              # report status, change nothing
  [switch]$OllamaOnly              # only install/start Ollama and download the translation model
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$wingetArgs = @('-e', '--accept-source-agreements', '--accept-package-agreements')

function Find-Ollama {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $path = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'  # a fresh install is not on PATH in this window yet
  if (Test-Path $path) { return $path }
}
function Test-Ollama { try { Invoke-WebRequest 'http://127.0.0.1:11434/api/version' -UseBasicParsing -TimeoutSec 3 | Out-Null; $true } catch { $false } }
# Installs Ollama if missing, starts it if stopped, downloads the model. Never throws: the rest of the setup is still useful.
function Install-Translation {
  Step 'Setting up Ollama (it runs the translation model on this PC)'
  $exe = Find-Ollama
  if (-not $exe) {
    if (-not (Has 'winget')) { Write-Host 'Ollama is missing and winget is not available. Install it from https://ollama.com/download, then run this again.' -ForegroundColor Yellow; return }
    winget install --id Ollama.Ollama @wingetArgs
    $exe = Find-Ollama
    if (-not $exe) { Write-Host 'Ollama could not be installed. Install it from https://ollama.com/download, then run this again.' -ForegroundColor Yellow; return }
  }
  if (-not (Test-Ollama)) {
    Write-Host 'Starting Ollama...'
    $app = Join-Path (Split-Path $exe) 'ollama app.exe'
    if (Test-Path $app) { Start-Process $app } else { Start-Process $exe 'serve' -WindowStyle Hidden }
    for ($i = 0; $i -lt 30 -and -not (Test-Ollama); $i++) { Start-Sleep 2 }
  }
  if (-not (Test-Ollama)) { Write-Host 'Ollama is installed but did not start. Open Ollama from the Start menu, then run this again.' -ForegroundColor Yellow; return }
  Step "Downloading the translation model $Model (the default is about 8 GB, so this can take a long time)"
  & $exe pull $Model
  if ($LASTEXITCODE) { Write-Host "Could not download $Model. Check the internet connection and the model name, then run this again." -ForegroundColor Yellow }
  else { Write-Host "Translation is ready: Ollama is running and $Model is installed." -ForegroundColor Green }
}
if ($OllamaOnly) { Install-Translation; return }

Step 'Checking what is installed'
$python = $null
if (Has 'py') { try { & py -3.12 -c "print()" *> $null; if ($LASTEXITCODE -eq 0) { $python = @('py', '-3.12') } } catch {} }
$ffmpeg = (Test-Path 'runtime\ffmpeg\bin\ffmpeg.exe') -or (Has 'ffmpeg')
$ollama = [bool](Find-Ollama)
$gpu = (-not $Cpu) -and (Has 'nvidia-smi')
Write-Host ("Python 3.12 : " + $(if ($python -or (Test-Path $venvPython)) { 'found' } else { 'missing (will install with winget)' }))
Write-Host ("FFmpeg      : " + $(if ($ffmpeg) { 'found' } else { 'missing (will install with winget)' }))
Write-Host ("Ollama      : " + $(if ($ollama) { 'found' } else { 'missing (will install with winget)' }))
Write-Host ("PyTorch     : " + $(if ($gpu) { 'NVIDIA GPU (CUDA 12.8)' } else { 'CPU only' }))
if ($CheckOnly) { return }

if (-not $python -and -not (Test-Path $venvPython)) {
  if (-not (Has 'winget')) { throw 'Python 3.12 is required. Install it from https://www.python.org/downloads/ then run this again.' }
  Step 'Installing Python 3.12 (from winget)'
  winget install --id Python.Python.3.12 @wingetArgs
  $fresh = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'  # not on PATH in this window yet
  if (-not (Test-Path $fresh)) { throw 'Python 3.12 could not be installed. Install it from https://www.python.org/downloads/ then run this again.' }
  $python = @($fresh)
}

Step 'Creating the Python environment (.venv)'
if (-not (Test-Path $venvPython)) { $rest = @($python | Select-Object -Skip 1); & $python[0] @rest -m venv .venv; if ($LASTEXITCODE) { throw 'Could not create .venv' } }
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
  winget install --id Gyan.FFmpeg @wingetArgs
  Write-Host 'FFmpeg installed. Open a NEW terminal (or sign out and in) so it is on PATH before starting the app.' -ForegroundColor Yellow
}

if (-not $SkipModels) {
  Step 'Downloading offline speech and subtitle-reading models'
  & $venvPython setup_models.py
  if ($LASTEXITCODE) { throw 'Model download failed' }
  Install-Translation
} else {
  Write-Host "`nTranslation still needs Ollama and a model. Set them up later with:  .\install.ps1 -OllamaOnly" -ForegroundColor Yellow
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
