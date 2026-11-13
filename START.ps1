$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = 'C:\Users\DELL\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython launch.py
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 launch.py
} else {
    Write-Error 'Cần cài Python 3.11 trở lên để chạy ứng dụng.'
}
