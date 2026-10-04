<#
.SYNOPSIS
    Construit l'installeur Windows de DoYouCopy : PyInstaller (dossier) puis Inno Setup.

.DESCRIPTION
    1. Installe PyInstaller dans .venv (créé par scripts\install_rocm.ps1).
    2. Télécharge la wheel CTranslate2 de PyPI (CPU + CUDA, empreinte vérifiée) et la
       décompresse dans build\ct2_cpu : c'est le moteur embarqué. Les accélérations
       AMD / NVIDIA sont téléchargées à la fin de l'installation, selon la carte.
    3. Génère l'icône et les informations de version, lance PyInstaller.
    4. Vérifie que l'exécutable démarre et charge son moteur (--probe).
    5. Signe l'exécutable si un certificat est fourni, puis compile l'installeur.

    Signature (facultative) : -CertFile chemin\vers\cert.pfx (mot de passe dans la
    variable d'environnement DOYOUCOPY_SIGN_PASSWORD) ou -CertThumbprint (certificat
    du magasin Windows). Sans certificat, l'installeur n'est pas signé et Windows
    SmartScreen affichera un avertissement.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#>
param(
    [string]$CertFile = "",
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Build = Join-Path $Root "build"
$Cache = Join-Path $Build "cache"
$Dist = Join-Path $Root "dist"
$AppDir = Join-Path $Build "dist\DoYouCopy"

$Ct2Url = "https://files.pythonhosted.org/packages/c2/fc/a9e9e0ce1c0a29bc4c17bf56ccb4274293c0bbb2b8aae561727d82fcb0ca/ctranslate2-4.8.2-cp313-cp313-win_amd64.whl"
$Ct2Sha = "399c20a7336b6358f69ce3c615e090eabc08f29735a079fd1ac1e464119e0861"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Échec ($LASTEXITCODE) : $Exe $($Arguments -join ' ')" }
}

function Find-Tool {
    param([string]$Name, [string[]]$Candidates)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in $Candidates) {
        $found = Get-ChildItem -Path $candidate -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

if (-not (Test-Path $Py)) { throw "Environnement .venv introuvable : lancez d'abord scripts\install_rocm.ps1" }
$Sign = [bool]($CertFile -or $CertThumbprint)
$SignTool = $null
if ($Sign) {
    $SignTool = Find-Tool "signtool.exe" @("${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe")
    if (-not $SignTool) { throw "signtool.exe introuvable (Windows SDK)" }
    if ($CertFile) {
        $SignArgs = @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256", "/f", $CertFile)
        if ($env:DOYOUCOPY_SIGN_PASSWORD) { $SignArgs += @("/p", $env:DOYOUCOPY_SIGN_PASSWORD) }
    } else {
        $SignArgs = @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256", "/sha1", $CertThumbprint)
    }
}

Write-Host "==> [1/5] PyInstaller" -ForegroundColor Cyan
& $Py -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('PyInstaller') is None)"
if ($LASTEXITCODE -ne 0) {  # CI installs it from requirements\build.txt (locked)
    Invoke-Checked $Py @("-m", "pip", "install", "--quiet", "pyinstaller>=6.10")
}

Write-Host "==> [2/5] Moteur CTranslate2 embarqué (CPU + CUDA)" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Cache | Out-Null
$Ct2Wheel = Join-Path $Cache (Split-Path -Leaf $Ct2Url)
if (-not (Test-Path $Ct2Wheel) -or (Get-FileHash $Ct2Wheel -Algorithm SHA256).Hash -ne $Ct2Sha) {
    Invoke-WebRequest -Uri $Ct2Url -OutFile $Ct2Wheel -UseBasicParsing
}
if ((Get-FileHash $Ct2Wheel -Algorithm SHA256).Hash -ne $Ct2Sha) { throw "Empreinte SHA-256 incorrecte : $Ct2Wheel" }
$Ct2Dir = Join-Path $Build "ct2_cpu"
if (Test-Path $Ct2Dir) { Remove-Item -Recurse -Force $Ct2Dir }
Invoke-Checked $Py @("-c", "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])", $Ct2Wheel, $Ct2Dir)
# NVIDIA cuDNN is proprietary: not shipped. The CPU engine loads without it, and the
# NVIDIA acceleration downloaded at install time brings its own copy.
Remove-Item (Join-Path $Ct2Dir "ctranslate2\cudnn64_9.dll")

Write-Host "==> [3/5] Application (PyInstaller)" -ForegroundColor Cyan
$Version = (& $Py (Join-Path $PSScriptRoot "make_build_assets.py")).Trim()
if (-not $SkipPyInstaller) {
    Invoke-Checked $Py @(
        "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", (Join-Path $Build "dist"), "--workpath", (Join-Path $Build "pyinstaller"),
        (Join-Path $Root "packaging\doyoucopy.spec")
    )
}

Write-Host "==> [4/5] Vérification de l'exécutable" -ForegroundColor Cyan
$Exe = Join-Path $AppDir "DoYouCopy.exe"
$Probe = Join-Path $Build "probe.json"
if (Test-Path $Probe) { Remove-Item $Probe }
$env:DOYOUCOPY_RUNTIME_DIR = Join-Path $Build "probe-runtime"  # ignore les runtimes déjà installés
$process = Start-Process -FilePath $Exe -ArgumentList @("--probe", "`"$Probe`"") -Wait -PassThru
Remove-Item Env:\DOYOUCOPY_RUNTIME_DIR
if (-not (Test-Path $Probe)) { throw "DoYouCopy.exe --probe n'a rien écrit (code $($process.ExitCode))" }
$result = Get-Content $Probe -Raw | ConvertFrom-Json
if ($result.error) { throw "Le moteur embarqué ne se charge pas : $($result.error)" }
Write-Host "    CTranslate2 $($result.ct2) chargé, GPU CUDA : $($result.devices)"

Write-Host "==> [5/5] Installeur (Inno Setup)" -ForegroundColor Cyan
$Iscc = Find-Tool "ISCC.exe" @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
if (-not $Iscc) { throw "Inno Setup 6 introuvable : winget install JRSoftware.InnoSetup" }
$IsccArgs = @("/Qp", "/DAppVersion=$Version", "/DSourceDir=$AppDir", "/DOutputDir=$Dist")
if ($Sign) {
    Invoke-Checked $SignTool ($SignArgs + @($Exe))
    $IsccArgs += @("/DSign=1", "/Smysign=`"$SignTool`" $($SignArgs -join ' ') `$f")
} else {
    Write-Warning "Installeur NON signé : Windows SmartScreen affichera un avertissement."
}
Invoke-Checked $Iscc ($IsccArgs + @((Join-Path $Root "installer\doyoucopy.iss")))

$Setup = Join-Path $Dist "DoYouCopy-Setup-$Version.exe"
$Size = [math]::Round((Get-Item $Setup).Length / 1MB)
$Hash = (Get-FileHash $Setup -Algorithm SHA256).Hash.ToLower()
Write-Host ""
Write-Host "Installeur : $Setup ($Size Mo)" -ForegroundColor Green
Write-Host "SHA-256    : $Hash"
