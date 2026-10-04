<#
.SYNOPSIS
    Crée le venv DoYouCopy avec faster-whisper accéléré par ROCm (AMD Radeon, Windows).

.DESCRIPTION
    1. Crée .venv avec la version de Python demandée.
    2. Installe le runtime ROCm 7.2 en paquets pip (TheRock), celui contre lequel
       CTranslate2 est compilé.
    3. Installe la wheel ROCm Windows de CTranslate2 depuis la release GitHub.
    4. Installe DoYouCopy et ses dépendances (ctranslate2 épinglé par constraints.txt).
    5. Vérifie le GPU, puis télécharge les modèles (sauf -SkipModels).

    Compatible Windows PowerShell 5.1 et PowerShell 7.
#>
param(
    [string]$Python = "3.13",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

$RocmBase = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2"
$RocmVersion = "7.2.0.dev0"
$Ct2Version = "4.8.2"
$Ct2Zip = "https://github.com/OpenNMT/CTranslate2/releases/download/v$Ct2Version/rocm-python-wheels-Windows.zip"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Échec ($LASTEXITCODE) : $Exe $($Arguments -join ' ')"
    }
}

Write-Host "==> [1/5] Environnement virtuel (Python $Python)" -ForegroundColor Cyan
if (-not (Test-Path $Py)) {
    Invoke-Checked "py" @("-$Python", "-m", "venv", $Venv)
}
Invoke-Checked $Py @("-m", "pip", "install", "--upgrade", "pip")

Write-Host "==> [2/5] Runtime ROCm $RocmVersion (pip, ~1,1 Go)" -ForegroundColor Cyan
Invoke-Checked $Py @(
    "-m", "pip", "install",
    "$RocmBase/rocm_sdk_core-$RocmVersion-py3-none-win_amd64.whl",
    "$RocmBase/rocm_sdk_libraries_custom-$RocmVersion-py3-none-win_amd64.whl",
    "$RocmBase/rocm-$RocmVersion.tar.gz"
)

Write-Host "==> [3/5] CTranslate2 $Ct2Version (build ROCm)" -ForegroundColor Cyan
$Tag = (& $Py -c "import sys; print(f'cp{sys.version_info[0]}{sys.version_info[1]}')").Trim()
$Work = Join-Path $env:TEMP "doyoucopy-ct2-rocm-$Ct2Version"
$ZipPath = Join-Path $Work "wheels.zip"
New-Item -ItemType Directory -Force -Path $Work | Out-Null
if (-not (Test-Path $ZipPath)) {
    Invoke-WebRequest -Uri $Ct2Zip -OutFile $ZipPath -UseBasicParsing
}
Expand-Archive -Path $ZipPath -DestinationPath $Work -Force
$Wheel = Get-ChildItem -Path $Work -Recurse -Filter "ctranslate2-$Ct2Version-$Tag-$Tag-win_amd64.whl" | Select-Object -First 1
if (-not $Wheel) {
    throw "Aucune wheel CTranslate2 ROCm pour $Tag dans $Ct2Zip"
}
Invoke-Checked $Py @("-m", "pip", "install", "--force-reinstall", "--no-deps", $Wheel.FullName)
Invoke-Checked $Py @("-m", "pip", "install", "numpy", "pyyaml>=5.3,<7")

Write-Host "==> [4/5] DoYouCopy et dépendances" -ForegroundColor Cyan
Push-Location $Root
try {
    Invoke-Checked $Py @("-m", "pip", "install", "-c", "constraints.txt", "-e", ".[dev]")
} finally {
    Pop-Location
}

Write-Host "==> [5/5] Vérification GPU" -ForegroundColor Cyan
Invoke-Checked $Py @((Join-Path $PSScriptRoot "check_gpu.py"))

if (-not $SkipModels) {
    Write-Host "==> Téléchargement des modèles (large-v3-turbo + large-v3, ~4,6 Go)" -ForegroundColor Cyan
    Invoke-Checked $Py @((Join-Path $PSScriptRoot "download_models.py"))
}

Write-Host ""
Write-Host "Installation terminée. Lancer l'application :" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\doyoucopy.exe"
