Set-Location $PSScriptRoot\..\windows-agent
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Python environment not found. Run D:\ClipBridge\scripts\setup.ps1 first."
}

$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$pythonHome = (& $python -c "import sys; print(sys.base_prefix)").Trim()
$tclLibrary = Join-Path $pythonHome "tcl\tcl8.6"
$tkLibrary = Join-Path $pythonHome "tcl\tk8.6"
if ((Test-Path (Join-Path $tclLibrary "init.tcl")) -and (Test-Path (Join-Path $tkLibrary "tk.tcl"))) {
    $env:TCL_LIBRARY = $tclLibrary
    $env:TK_LIBRARY = $tkLibrary
}
& $python -m clipbridge
