param(
    [string]$OutputDir = "dist\Inventorius-portable",
    [string]$PythonDir = "",
    [string]$PortableGitDir = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Out = Join-Path $Root $OutputDir

if (Test-Path $Out) {
    Remove-Item $Out -Recurse -Force
}

New-Item $Out -ItemType Directory | Out-Null
New-Item (Join-Path $Out "src") -ItemType Directory | Out-Null
New-Item (Join-Path $Out "docs") -ItemType Directory | Out-Null
New-Item (Join-Path $Out "scripts") -ItemType Directory | Out-Null

Copy-Item (Join-Path $Root "src\inventorymgmt.py") (Join-Path $Out "src\inventorymgmt.py")
Copy-Item (Join-Path $Root "src\app.ico") (Join-Path $Out "src\app.ico") -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Root "docs\*") (Join-Path $Out "docs") -Recurse
Copy-Item (Join-Path $Root "scripts\*") (Join-Path $Out "scripts") -Recurse
Copy-Item (Join-Path $Root "requirements.txt") (Join-Path $Out "requirements.txt")
Copy-Item (Join-Path $Root "run_inventory.bat") (Join-Path $Out "run_inventory.bat")

if (Test-Path (Join-Path $Root ".git")) {
    Copy-Item (Join-Path $Root ".git") (Join-Path $Out ".git") -Recurse
}

if ($PythonDir -ne "") {
    if (!(Test-Path $PythonDir)) {
        throw "PythonDir does not exist: $PythonDir"
    }
    Copy-Item $PythonDir (Join-Path $Out "python") -Recurse
}

if ($PortableGitDir -ne "") {
    if (!(Test-Path $PortableGitDir)) {
        throw "PortableGitDir does not exist: $PortableGitDir"
    }
    Copy-Item $PortableGitDir (Join-Path $Out "PortableGit") -Recurse
}

Write-Host "Portable bundle created at: $Out"
Write-Host "Run with: $(Join-Path $Out 'run_inventory.bat')"
