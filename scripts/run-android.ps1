param(
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$androidRoot = Join-Path $projectRoot "android-app"

$javaHome = $env:JAVA_HOME
if ($javaHome -and $javaHome.EndsWith("\bin")) {
    $javaHome = $javaHome.Substring(0, $javaHome.Length - 4)
    $env:JAVA_HOME = $javaHome
}

if (-not (Test-Path (Join-Path $androidRoot "settings.gradle.kts"))) {
    throw "Android project was not found at $androidRoot"
}

$javaPath = $null
if ($env:JAVA_HOME) {
    $configuredJava = Join-Path $javaHome "bin\java.exe"
    if (Test-Path $configuredJava) {
        $javaPath = $configuredJava
    }
}
if (-not $javaPath) {
    $java = Get-Command java -ErrorAction SilentlyContinue
    if ($java) {
        $javaPath = $java.Source
    }
}
if (-not $javaPath) {
    throw "Java was not found. Install JDK 17 and set JAVA_HOME to its root directory."
}

$javaVersionOutput = & $env:ComSpec /c "`"$javaPath`" -version 2>&1"
$javaVersion = ($javaVersionOutput | Select-String 'version "([^"]+)"').Matches.Groups[1].Value
if (-not $javaVersion.StartsWith("17.")) {
    throw "ClipBridge requires JDK 17. The active Java version is '$javaVersion'. Set JAVA_HOME and PATH to JDK 17, then retry."
}

$sdkRoot = $env:ANDROID_HOME
if (-not $sdkRoot) {
    $sdkRoot = $env:ANDROID_SDK_ROOT
}
if (-not $sdkRoot) {
    $adb = Get-Command adb -ErrorAction SilentlyContinue
    if ($adb) {
        $adbRoot = Split-Path (Split-Path $adb.Source -Parent) -Parent
        if (Test-Path (Join-Path $adbRoot "platforms\android-34")) {
            $sdkRoot = $adbRoot
        }
    }
}
if (-not $sdkRoot -or -not (Test-Path (Join-Path $sdkRoot "platforms\android-34"))) {
    throw "Android SDK Platform 34 was not found. Set ANDROID_HOME to your SDK folder, for example D:\locals."
}
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot

$gradleCommand = $null
$gradleWrapper = Join-Path $androidRoot "gradlew.bat"
if (Test-Path $gradleWrapper) {
    $gradleCommand = $gradleWrapper
} else {
    $gradle = Get-Command gradle -ErrorAction SilentlyContinue
    if ($gradle) {
        $gradleCommand = $gradle.Source
    }
}
if (-not $gradleCommand) {
    throw "Gradle was not found. Install Gradle or generate android-app\gradlew.bat with 'gradle wrapper'."
}

Push-Location $androidRoot
try {
    & $gradleCommand "assembleDebug"
    if ($LASTEXITCODE -ne 0) {
        throw "Android build failed."
    }

    if ($BuildOnly) {
        Write-Output "APK created at android-app\app\build\outputs\apk\debug\app-debug.apk"
        exit 0
    }

    $adb = Get-Command adb -ErrorAction SilentlyContinue
    if (-not $adb) {
        throw "adb was not found. Use -BuildOnly to build an APK without a USB-connected phone."
    }

    & adb start-server
    $devices = @(adb devices | Select-String "`tdevice$")
    if ($devices.Count -eq 0) {
        throw "No authorized Android phone found. Enable USB debugging, connect the phone, and accept the RSA prompt."
    }

    & adb install -r "app\build\outputs\apk\debug\app-debug.apk"
    if ($LASTEXITCODE -ne 0) {
        throw "APK installation failed."
    }

    & adb shell am force-stop com.clipbridge
    & adb shell monkey -p com.clipbridge 1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not launch ClipBridge on the phone."
    }
} finally {
    Pop-Location
}
