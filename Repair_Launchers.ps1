param([string]$AppDir = $PSScriptRoot)

$ErrorActionPreference = 'Stop'
$AppDir = [IO.Path]::GetFullPath($AppDir).TrimEnd('\')
if ((Split-Path -Leaf $AppDir) -ne 'SHADER7_AI') { throw 'Run this from a SHADER7_AI folder.' }
$root = Split-Path -Parent $AppDir
$shell = New-Object -ComObject WScript.Shell
foreach ($entry in @(
    @{ Cmd = 'Launch CPU.cmd'; Bat = 'Launch_CPU_Mode.bat'; Link = 'Launch Now in CPU.lnk'; Args = 'cpu'; Target = 'Launch_SHADER7_AI.vbs' },
    @{ Cmd = 'Launch GPU.cmd'; Bat = 'Launch_GPU_Mode.bat'; Link = 'Launch Now in GPU.lnk'; Args = 'gpu'; Target = 'Launch_SHADER7_AI.vbs' },
    @{ Cmd = 'Install to PC.cmd'; Bat = 'Install_To_PC.bat'; Link = 'Install.lnk'; Args = ''; Target = 'Install_To_PC.bat' }
)) {
    $target = Join-Path $AppDir $entry.Target
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing launcher: $target" }
    $cmdPath = Join-Path $root $entry.Cmd
    if ((Test-Path -LiteralPath $cmdPath) -and
        -not ((Get-Content -LiteralPath $cmdPath -TotalCount 2) -contains 'rem SHADER7 AI portable launcher')) {
        throw "An unrelated file already uses $cmdPath"
    }
    $linkPath = Join-Path $root $entry.Link
    if (Test-Path -LiteralPath $linkPath) {
        $previous = $shell.CreateShortcut($linkPath)
        if (-not $previous.TargetPath.EndsWith("\SHADER7_AI\$($entry.Target)", [StringComparison]::OrdinalIgnoreCase)) {
            throw "An unrelated shortcut already uses $linkPath"
        }
    }
    "@echo off`r`nrem SHADER7 AI portable launcher`r`ncall `"%~dp0SHADER7_AI\$($entry.Bat)`"`r`n" |
        Set-Content -LiteralPath $cmdPath -Encoding Ascii
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = $target
    $shortcut.Arguments = $entry.Args
    $shortcut.WorkingDirectory = $AppDir
    $shortcut.IconLocation = (Join-Path $AppDir 'app.ico') + ',0'
    $shortcut.Save()
}
Write-Host "Launchers updated at $root"
