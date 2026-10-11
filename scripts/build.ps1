Set-Location $PSScriptRoot\..\windows-agent
.\.venv\Scripts\pyinstaller --noconsole --onefile --name ClipBridge `
    --icon "$PSScriptRoot\..\branding\clipbridge.ico" `
    --add-data "$PSScriptRoot\..\branding;branding" `
    --hidden-import pystray._win32 --collect-submodules zeroconf clipbridge\__main__.py
