<#
  BARJ Volume Controller - GitHub bootstrap installer (Windows)

  One-line install (PowerShell):
    irm https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.ps1 | iex

  Downloads the latest source from GitHub and runs the full installer
  (packaging\barj.ps1 install), which checks dependencies and sets up the app.
#>

$ErrorActionPreference = "Stop"

$GhOwner  = "JoeRAB"
$GhRepo   = "BARJ-Volume-Controller"
$GhBranch = if ($env:BARJ_BRANCH) { $env:BARJ_BRANCH } else { "main" }

$ReleaseUrl = "https://github.com/$GhOwner/$GhRepo/releases/latest/download/$GhRepo.zip"
$BranchUrl  = "https://github.com/$GhOwner/$GhRepo/archive/refs/heads/$GhBranch.zip"

$tmp = Join-Path $env:TEMP ("barj_boot_" + [System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp "barj.zip"

Write-Host "Downloading BARJ Volume Controller from GitHub..."
try {
  Invoke-WebRequest -Uri $ReleaseUrl -OutFile $zip -UseBasicParsing
} catch {
  Write-Host "No release asset found; using latest source from '$GhBranch'."
  Invoke-WebRequest -Uri $BranchUrl -OutFile $zip -UseBasicParsing
}

Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp "src") -Force

$installer = Get-ChildItem -Path (Join-Path $tmp "src") -Recurse -Filter "barj.ps1" |
  Where-Object { $_.FullName -match "packaging" } | Select-Object -First 1

if (-not $installer) {
  Write-Host "Could not find packaging\barj.ps1 in the download." -ForegroundColor Red
  exit 1
}

Write-Host "Running installer..."
& powershell -ExecutionPolicy Bypass -File $installer.FullName install

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
