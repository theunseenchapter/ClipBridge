param(
    [switch]$SkipAndroid,
    [switch]$SkipWindows,
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$release = Join-Path $root "release"
New-Item -ItemType Directory -Force $release | Out-Null

$javaHome = $env:JAVA_HOME
if ($javaHome -and $javaHome.EndsWith("\bin")) {
    $javaHome = $javaHome.Substring(0, $javaHome.Length - 4)
    $env:JAVA_HOME = $javaHome
}

if ($SkipWindows -and $SkipAndroid) {
    throw "Choose at least one platform to build."
}

if (-not $SkipWindows) {
    Push-Location $root
    try {
        $venvPython = Join-Path $root "windows-agent\.venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if (-not $python) {
                throw "Python 3.11 or newer was not found. Install Python, then run this script again."
            }
            & $python.Source -m venv (Join-Path $root "windows-agent\.venv")
            if ($LASTEXITCODE -ne 0) { throw "Could not create the Windows build environment." }
            & $venvPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the Windows build environment." }
            & $venvPython -m pip install -r (Join-Path $root "windows-agent\requirements.txt")
            if ($LASTEXITCODE -ne 0) { throw "Could not install Windows build dependencies." }
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\build.ps1"
        if ($LASTEXITCODE -ne 0) { throw "Windows executable build failed." }
        $windowsOutput = Join-Path $release "ClipBridge-Windows.exe"
        try {
            Copy-Item "$root\windows-agent\dist\ClipBridge.exe" $windowsOutput -Force
        } catch {
            throw "Could not replace $windowsOutput. Close the currently running ClipBridge-Windows.exe and retry."
        }
    } finally {
        Pop-Location
    }
}

if (-not $SkipAndroid) {
    $android = Join-Path $root "android-app"
    $wrapper = Join-Path $android "gradlew.bat"
    if (-not (Test-Path $wrapper)) {
        throw "Android Gradle wrapper is missing. Run 'gradle wrapper' inside android-app once."
    }

    if (-not $env:JAVA_HOME -or -not (Test-Path (Join-Path $env:JAVA_HOME "bin\java.exe"))) {
        throw "JDK 17 was not found. Set JAVA_HOME to the JDK folder, not its bin folder."
    }

    $sdkRoot = $env:ANDROID_HOME
    if (-not $sdkRoot) {
        $sdkRoot = $env:ANDROID_SDK_ROOT
    }
    if (-not $sdkRoot -or -not (Test-Path (Join-Path $sdkRoot "platforms\android-34"))) {
        throw "Android SDK Platform 34 was not found. Set ANDROID_HOME to your SDK folder."
    }
    $env:ANDROID_HOME = $sdkRoot
    $env:ANDROID_SDK_ROOT = $sdkRoot

    Push-Location $android
    try {
        # Debug APKs are signed by Gradle's local debug key and can be
        # installed directly by users without Android Studio or ADB.
        & $wrapper "assembleDebug" "--no-daemon"
        if ($LASTEXITCODE -ne 0) { throw "Android APK build failed." }
        Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "$release\ClipBridge-Android.apk" -Force
    } finally {
        Pop-Location
    }
}

@"
ClipBridge release
==================

Windows:
  Run ClipBridge-Windows.exe. It is portable and does not require Python.
  The web dashboard opens automatically at
  http://127.0.0.1:48501/dashboard. The tray menu also keeps the native
  pairing and history windows available.
  Allow ClipBridge through Windows Firewall when prompted. Both devices must
  be connected to the same private Wi-Fi network.

Android:
  Copy ClipBridge-Android.apk to the phone, open it, and allow installation
  from this source when Android asks. Open ClipBridge and pair it by scanning
  the QR code from the Windows tray menu.

This APK is signed with Gradle's debug signing key so it can be installed
directly for private/open-source distribution. Keep using the same signing
key for updates distributed to existing users.
"@ | Set-Content (Join-Path $release "INSTALL.txt") -Encoding UTF8

if ($CreateZip) {
    $zip = Join-Path $release "ClipBridge-release.zip"
    $files = Get-ChildItem $release -File | Where-Object { $_.Name -ne (Split-Path $zip -Leaf) }
    Compress-Archive -Path $files.FullName -DestinationPath $zip -Force
}

Write-Output "Release files are in $release"
