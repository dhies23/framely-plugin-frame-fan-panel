# preview.ps1 - build the plugin page preview and screenshot it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\preview.ps1
#
# Chrome is launched through cmd.exe: Node cannot spawn it directly under the
# DSH sandbox (exit 2147483651), while cmd inherits stdio without a pipe.
param(
    [string]$Out = "docs\preview.png",
    [int]$Width = 560,
    [int]$Height = 1240,
    [int]$Scale = 2
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $env:Path = "B:\depjob\tools\node\node-v24.21.0-win-x64;$env:Path"
    $html = & node scripts\preview.mjs
    if ($LASTEXITCODE -ne 0) { throw "preview.mjs failed" }
    $html = (Resolve-Path -LiteralPath $html).Path

    $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    if (-not (Test-Path $chrome)) { $chrome = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" }
    if (-not (Test-Path $chrome)) { throw "chrome.exe not found" }

    $outPath = [System.IO.Path]::GetFullPath((Join-Path $root $Out))
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outPath) | Out-Null
    if (Test-Path $outPath) { Remove-Item -LiteralPath $outPath -Force }

    $url = "file:///" + ($html -replace '\\', '/')
    $profile = Join-Path $env:TEMP ("chrome-shot-" + [guid]::NewGuid().ToString('N'))
    $args = '--headless=new --disable-gpu --hide-scrollbars --no-first-run ' +
            '--no-default-browser-check --force-device-scale-factor=' + $Scale +
            ' --user-data-dir="' + $profile + '" --window-size=' + $Width + ',' + $Height +
            ' --virtual-time-budget=6000 --screenshot="' + $outPath + '" "' + $url + '"'
    # Chrome writes its "N bytes written" note to stderr; keep PowerShell from
    # turning that into a terminating error under $ErrorActionPreference='Stop'.
    $log = Join-Path $env:TEMP ("chrome-shot-" + [guid]::NewGuid().ToString('N') + ".log")
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    cmd /c "`"$chrome`" $args" 2>$log | Out-Null
    $ErrorActionPreference = $previous
    Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path $outPath)) { throw "screenshot failed" }
    "OK $((Get-Item $outPath).Length) bytes -> $outPath"
}
finally {
    Pop-Location
}
