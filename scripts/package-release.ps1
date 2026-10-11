param(
    [switch]$SkipAndroid,
    [switch]$SkipWindows
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

if (-not $SkipWindows) {
    Push-Location $root
    try {
        & "$PSScriptRoot\setup.ps1"
        & "$PSScriptRoot\build.ps1"
        Copy-Item "$root\windows-agent\dist\ClipBridge.exe" "$release\ClipBridge-Windows.exe" -Force
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
    Push-Location $android
    try {
        & $wrapper "assembleDebug"
        if ($LASTEXITCODE -ne 0) { throw "Android APK build failed." }
        Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "$release\ClipBridge-Android.apk" -Force
    } finally {
        Pop-Location
    }
}

Write-Output "Release files are in $release"
