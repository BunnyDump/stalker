param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [int]$StartupSeconds = 30,
    [int]$StressSeconds = 120
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $PackageRoot).Path
$bin = Join-Path $root 'bin'
$exe = Join-Path $bin 'XR_3DA.exe'
$vk = Join-Path $bin 'xrRender_VK.dll'
$gamedata = Join-Path $root 'gamedata'

foreach ($required in @($exe, $vk, $gamedata, (Join-Path $gamedata 'config'), (Join-Path $gamedata 'textures'))) {
    if (-not (Test-Path $required)) { throw "Runtime smoke missing required path: $required" }
}

function Get-NewestXRayLog {
    param([string]$Base)
    Get-ChildItem $Base -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)(xray.*\.log|.*\.log)$' } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

$before = Get-Date
$args = '-vulkan -renderer_vk -nointro -noprefetch'
Write-Host "[runtime-smoke] launching $exe $args"
$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $bin -PassThru

$startupDeadline = (Get-Date).AddSeconds($StartupSeconds)
while ((Get-Date) -lt $startupDeadline) {
    Start-Sleep -Seconds 1
    $p.Refresh()
    if ($p.HasExited) {
        $code = $p.ExitCode
        $log = Get-NewestXRayLog $root
        if ($log) { Get-Content $log.FullName -Tail 200 | Write-Host }
        throw "XR_3DA exited during Vulkan startup smoke with code $code"
    }
}

$log = Get-NewestXRayLog $root
if (-not $log) { throw 'XR_3DA remained alive but produced no log file.' }
$text = Get-Content $log.FullName -Raw -ErrorAction Stop
if ($text -notmatch 'Loading DLL:\s*xrRender_VK\.dll') {
    throw "Runtime log does not prove xrRender_VK.dll was selected: $($log.FullName)"
}
if ($text -match '(?i)(fatal error|stack trace|unhandled exception|access violation)') {
    throw "Runtime log contains an early fatal/crash marker: $($log.FullName)"
}
Write-Host "[runtime-smoke] Vulkan loader selection confirmed in $($log.FullName)"

$stressDeadline = (Get-Date).AddSeconds([Math]::Max(0,$StressSeconds))
while ((Get-Date) -lt $stressDeadline) {
    Start-Sleep -Seconds 2
    $p.Refresh()
    if ($p.HasExited) {
        $code = $p.ExitCode
        $log = Get-NewestXRayLog $root
        if ($log) { Get-Content $log.FullName -Tail 300 | Write-Host }
        throw "XR_3DA exited during Vulkan stress window with code $code"
    }
}

$p.Refresh()
if (-not $p.HasExited) {
    Stop-Process -Id $p.Id -Force
    $p.WaitForExit()
}
$log = Get-NewestXRayLog $root
if ($log) {
    $final = Get-Content $log.FullName -Raw -ErrorAction SilentlyContinue
    if ($final -match '(?i)(fatal error|stack trace|unhandled exception|access violation)') {
        throw "Runtime log contains a fatal/crash marker after stress window: $($log.FullName)"
    }
}
Write-Host "[runtime-smoke] PASS: native Vulkan renderer stayed alive for startup + stress windows"
