[CmdletBinding(SupportsShouldProcess=$true)]
param([switch]$Confirmed)

$ErrorActionPreference = 'Stop'
$taskUserProfile = [Environment]::GetFolderPath('UserProfile')
$expectedTarget = [IO.Path]::GetFullPath((Join-Path $taskUserProfile 'LocalAI'))
$taskLog = Join-Path $taskUserProfile 'LocalAI_Workspace\uninstall.log'

try {
    if (-not (Test-Path -LiteralPath $expectedTarget)) {
        Write-Host 'No PC installation was found.'
        exit 0
    }
    $resolvedTarget = (Resolve-Path -LiteralPath $expectedTarget).ProviderPath.TrimEnd('\')
    if ($resolvedTarget -ne $expectedTarget.TrimEnd('\')) {
        throw 'The installation path did not resolve to the expected LocalAI folder.'
    }
    $rootItem = Get-Item -LiteralPath $resolvedTarget -Force
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The installation is a link or junction. Nothing was removed.'
    }
    $markerPath = Join-Path $resolvedTarget 'shader7-install.json'
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw 'This folder has no SHADER7 ownership marker. Older installations and shared models were preserved.'
    }
    $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    if ($marker.app -ne 'shader7-ai') { throw 'The installation ownership marker is invalid.' }
    $links = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force | Where-Object {
        $_.Attributes -band [IO.FileAttributes]::ReparsePoint
    })
    if ($links.Count -gt 0) { throw 'The installation contains links or junctions. Nothing was removed.' }

    Write-Host "Remove only: $resolvedTarget"
    Write-Host 'Your chats, API keys, USB drive, and shared .ollama models will be kept.'
    if (-not $Confirmed -and -not $WhatIfPreference) {
        $answer = Read-Host 'Type Y to remove this PC installation'
        if ($answer -ne 'Y') { Write-Host 'Cancelled.'; exit 0 }
    }
    if ($PSCmdlet.ShouldProcess($resolvedTarget, 'Remove SHADER7 installation and its own models')) {
        Start-Sleep -Seconds 2
        $targetPrefix = $resolvedTarget + '\'
        $processSnapshot = @(Get-CimInstance Win32_Process)
        $ownedProcesses = @($processSnapshot | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)
        })
        # A dedicated GPU engine may use binaries from the PC Ollama installation.
        # Include only engine descendants of this app; shared Ollama is unrelated.
        $descendantIds = [Collections.Generic.HashSet[uint32]]::new()
        foreach ($ownedProcess in $ownedProcesses) { [void]$descendantIds.Add($ownedProcess.ProcessId) }
        do {
            $addedDescendant = $false
            foreach ($candidateProcess in $processSnapshot) {
                if ($descendantIds.Contains($candidateProcess.ParentProcessId) -and $descendantIds.Add($candidateProcess.ProcessId)) {
                    $addedDescendant = $true
                }
            }
        } while ($addedDescendant)
        foreach ($engineProcess in $processSnapshot) {
            if ($descendantIds.Contains($engineProcess.ProcessId) -and $engineProcess.Name -in @('ollama.exe', 'llama-server.exe')) {
                Stop-Process -Id $engineProcess.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
        foreach ($process in $ownedProcesses) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'SHADER7 AI.lnk'
        if (Test-Path -LiteralPath $shortcutPath) {
            $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
            if ($shortcut.TargetPath.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $shortcutPath -Force
            }
        }
        # The resolved path was checked against the exact user-profile LocalAI directory.
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
        $message = 'SHADER7 PC application removed. Chats, keys, and shared models were kept.'
        Write-Host $message
        if (Test-Path -LiteralPath (Split-Path $taskLog)) { Set-Content -LiteralPath $taskLog -Value $message }
    }
} catch {
    $message = 'Uninstall failed: ' + $_.Exception.Message
    Write-Host $message
    if (Test-Path -LiteralPath (Split-Path $taskLog)) { Set-Content -LiteralPath $taskLog -Value $message }
    exit 1
}
