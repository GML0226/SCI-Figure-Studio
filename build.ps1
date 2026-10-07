$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.buildenv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    python -m venv .buildenv
}
& $buildPython -m pip install -r requirements.txt pyinstaller==6.13.0
& $buildPython -m PyInstaller --noconfirm --distpath portable --workpath .build ScientificFigureStudio.spec
if ($LASTEXITCODE -ne 0) { throw 'Portable build failed.' }
