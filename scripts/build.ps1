Set-Location $PSScriptRoot\..\windows-agent
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$pythonHome = (& $python -c "import sys; print(sys.base_prefix)").Trim()
$env:TCL_LIBRARY = Join-Path $pythonHome "tcl\tcl8.6"
$env:TK_LIBRARY = Join-Path $pythonHome "tcl\tk8.6"
.\.venv\Scripts\pyinstaller --clean --noconsole --onefile --name ClipBridge `
    --icon "$PSScriptRoot\..\branding\clipbridge.ico" `
    --add-data "$PSScriptRoot\..\branding;branding" `
    --add-data "$PSScriptRoot\..\windows-agent\clipbridge\web;clipbridge\web" `
    --hidden-import tkinter --hidden-import _tkinter `
    --hidden-import pystray._win32 --collect-submodules zeroconf launcher.py
