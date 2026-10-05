<#
.SYNOPSIS
    Construit le paquet Microsoft Store (MSIX) de DoYouCopy.

.DESCRIPTION
    Part de l'application déjà construite par scripts\build_installer.ps1
    (build\dist\DoYouCopy, avec -SkipInstaller si l'installeur n'est pas voulu) et de
    build\msix (manifeste et logos, écrits par scripts\make_build_assets.py) :
    1. assemble build\msix\layout ;
    2. indexe les logos (makepri : échelles et tailles de la barre des tâches) et la
       description du paquet en anglais et en français (packaging\msix\Strings) ;
    3. crée dist\DoYouCopy-<version>-x64.msix (makeappx).

    Le paquet n'est PAS signé : c'est ce fichier qu'on dépose dans Partner Center, le
    Store le signe lui-même. Pour l'installer sur cette machine avant de le soumettre,
    -DevSign le signe avec un certificat de test (sujet = Publisher du manifeste) et
    l'approuve pour la machine (magasin « Personnes autorisées » de l'ordinateur, le
    seul qu'accepte Add-AppxPackage) : terminal administrateur requis.
    -Wack lance ensuite le Windows App Certification Kit, les tests que le Store passe
    à la soumission ; il installe le paquet pour le tester, donc implique -DevSign.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipInstaller
    powershell -ExecutionPolicy Bypass -File scripts\build_msix.ps1 -DevSign
#>
param(
    [switch]$DevSign,
    [switch]$Wack
)

$ErrorActionPreference = "Stop"
if ($Wack) { $DevSign = $true }
if ($DevSign) {
    $Admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $Admin) { throw "-DevSign et -Wack demandent un terminal administrateur (clic droit sur PowerShell > Exécuter en tant qu'administrateur)" }
}
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root "build"
$Dist = Join-Path $Root "dist"
$AppDir = Join-Path $Build "dist\DoYouCopy"
$Msix = Join-Path $Build "msix"
$Layout = Join-Path $Msix "layout"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Échec ($LASTEXITCODE) : $Exe $($Arguments -join ' ')" }
}

function Find-SdkTool {
    param([string]$Name)
    $found = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.*\x64\$Name" -ErrorAction SilentlyContinue |
        Sort-Object { [version]$_.Directory.Parent.Name } -Descending | Select-Object -First 1
    if (-not $found) { throw "$Name introuvable : installez le Windows SDK (winget install Microsoft.WindowsSDK.10.0.26100)" }
    return $found.FullName
}

if (-not (Test-Path (Join-Path $AppDir "DoYouCopy.exe"))) {
    throw "Application introuvable : lancez d'abord scripts\build_installer.ps1 -SkipInstaller"
}
if (-not (Test-Path (Join-Path $Msix "AppxManifest.xml"))) {
    throw "Manifeste introuvable : scripts\make_build_assets.py ne l'a pas écrit"
}
$MakeAppx = Find-SdkTool "makeappx.exe"
$MakePri = Find-SdkTool "makepri.exe"
[xml]$Manifest = Get-Content (Join-Path $Msix "AppxManifest.xml") -Raw -Encoding UTF8
$Version = $Manifest.Package.Identity.Version
$Publisher = $Manifest.Package.Identity.Publisher

Write-Host "==> [1/3] Contenu du paquet" -ForegroundColor Cyan
if (Test-Path $Layout) { Remove-Item -Recurse -Force $Layout }
New-Item -ItemType Directory -Force -Path $Layout | Out-Null
Copy-Item -Recurse $AppDir (Join-Path $Layout "DoYouCopy")
Copy-Item -Recurse (Join-Path $Msix "Assets") (Join-Path $Layout "Assets")
Copy-Item (Join-Path $Msix "AppxManifest.xml") $Layout

Write-Host "==> [2/3] Index des ressources (makepri)" -ForegroundColor Cyan
# Indexed apart from the application: only the logos, the manifest texts (one
# Resources.resw per language) and the manifest, so that the thousands of files of
# DoYouCopy\ are not read as resources.
$PriRoot = Join-Path $Msix "pri"
if (Test-Path $PriRoot) { Remove-Item -Recurse -Force $PriRoot }
New-Item -ItemType Directory -Force -Path $PriRoot | Out-Null
Copy-Item -Recurse (Join-Path $Msix "Assets") (Join-Path $PriRoot "Assets")
Copy-Item -Recurse (Join-Path $Root "packaging\msix\Strings") (Join-Path $PriRoot "Strings")
Copy-Item (Join-Path $Msix "AppxManifest.xml") $PriRoot
Invoke-Checked $MakePri @("new", "/pr", $PriRoot, "/cf", (Join-Path $Root "packaging\msix\priconfig.xml"),
    "/mn", (Join-Path $PriRoot "AppxManifest.xml"), "/of", (Join-Path $Layout "resources.pri"), "/o")

Write-Host "==> [3/3] Paquet (makeappx)" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
$Package = Join-Path $Dist "DoYouCopy-$Version-x64.msix"
$Output = & $MakeAppx pack /d $Layout /p $Package /o 2>&1  # one line per file: shown on failure only
if ($LASTEXITCODE -ne 0) { $Output | Write-Host; throw "Échec ($LASTEXITCODE) : makeappx pack" }

if ($DevSign) {
    Write-Host "==> Signature de test" -ForegroundColor Cyan
    $Cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $Publisher -and $_.NotAfter -gt (Get-Date) } |
        Select-Object -First 1
    if (-not $Cert) {
        $Cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher -KeyUsage DigitalSignature `
            -FriendlyName "DoYouCopy (test MSIX)" -CertStoreLocation Cert:\CurrentUser\My `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
    }
    # Add-AppxPackage only accepts a test signature trusted by the machine (the
    # user's own TrustedPeople store is not enough: error 0x800B0109).
    $Trusted = Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object { $_.Thumbprint -eq $Cert.Thumbprint }
    if (-not $Trusted) {
        $Cer = Join-Path $Msix "devcert.cer"
        Export-Certificate -Cert $Cert -FilePath $Cer | Out-Null
        Import-Certificate -FilePath $Cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null
        Write-Host "    Certificat de test approuvé (Ordinateur local > Personnes autorisées, empreinte $($Cert.Thumbprint))"
    }
    $SignTool = Find-SdkTool "signtool.exe"
    Invoke-Checked $SignTool @("sign", "/fd", "SHA256", "/sha1", $Cert.Thumbprint, "/s", "My", $Package)
}

if ($Wack) {
    Write-Host "==> Windows App Certification Kit" -ForegroundColor Cyan
    $AppCert = "${env:ProgramFiles(x86)}\Windows Kits\10\App Certification Kit\appcert.exe"
    if (-not (Test-Path $AppCert)) { throw "appcert.exe introuvable (Windows SDK, composant App Certification Kit)" }
    $Report = Join-Path $Dist "DoYouCopy-$Version-wack.xml"
    if (Test-Path $Report) { Remove-Item $Report }
    Invoke-Checked $AppCert @("reset")
    Invoke-Checked $AppCert @("test", "-appxpackagepath", $Package, "-reportoutputpath", $Report)
    [xml]$Result = Get-Content $Report -Raw
    Write-Host "    Résultat : $($Result.REPORT.OVERALL_RESULT) (rapport : $Report)"
}

$Size = [math]::Round((Get-Item $Package).Length / 1MB)
$Hash = (Get-FileHash $Package -Algorithm SHA256).Hash.ToLower()
Write-Host ""
Write-Host "Paquet MSIX : $Package ($Size Mo)" -ForegroundColor Green
Write-Host "SHA-256     : $Hash"
if ($DevSign) {
    Write-Host "Installer   : Add-AppxPackage `"$Package`""
} else {
    Write-Host "Non signé : à déposer dans Partner Center (le Store le signe)."
}
