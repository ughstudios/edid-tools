$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReleaseDir = Join-Path $ProjectDir "release"
$ReleasePackageDir = Join-Path $ReleaseDir "EDIDTools-windows-x64"
$ArchivePath = Join-Path $ReleaseDir "EDIDTools-windows-x64.zip"

Push-Location $ProjectDir
try {
    python -m PyInstaller --noconfirm --clean .\EDIDTools.spec

    Copy-Item -Path ".\xml" -Destination ".\dist\EDIDTools" -Recurse -Force

    New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
    New-Item -ItemType Directory -Path $ReleasePackageDir -Force | Out-Null
    Copy-Item -Path ".\dist\EDIDTools\*" -Destination $ReleasePackageDir -Recurse -Force
    if (Test-Path -LiteralPath $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
    Compress-Archive -Path ".\dist\EDIDTools" -DestinationPath $ArchivePath -Force

    Write-Host "Redistributable package created:"
    Write-Host $ArchivePath
}
finally {
    Pop-Location
}
