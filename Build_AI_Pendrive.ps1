<# Build a portable Windows copy of SHADER7 AI. Run from an extracted release folder. #>
param(
    [string]$TargetDrive,
    [ValidateSet('Minimal', 'All', 'Local')][string]$ModelOption,
    [string]$LocalModelsPath,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$buildServer = $null
$oldHost = $env:OLLAMA_HOST
$oldModels = $env:OLLAMA_MODELS
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Is-Inside([string]$path, [string]$parent) {
    $path = [IO.Path]::GetFullPath($path).TrimEnd('\') + '\'
    $parent = [IO.Path]::GetFullPath($parent).TrimEnd('\') + '\'
    return $path.StartsWith($parent, [StringComparison]::OrdinalIgnoreCase)
}

function Copy-Required([string]$name, [string]$destination) {
    $from = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Repository file missing: $name" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $destination $name) -Force
}

function Download-Zip([string]$url, [string]$destination) {
    $archive = Join-Path $env:TEMP ("shader7-" + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        Write-Host "Downloading $url"
        Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
    } finally {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows 64-bit is required.' }
    if (-not $TargetDrive) {
        if ($NonInteractive) { throw '-TargetDrive is required with -NonInteractive.' }
        $drives = @(Get-CimInstance Win32_LogicalDisk | Where-Object DriveType -eq 2)
        Write-Host 'Choose the USB drive or enter a folder path:'
        for ($i = 0; $i -lt $drives.Count; $i++) {
            Write-Host "  $($i + 1). $($drives[$i].DeviceID) $($drives[$i].VolumeName) ($([math]::Round($drives[$i].FreeSpace / 1GB, 1)) GB free)"
        }
        $answer = Read-Host 'Drive number or full path'
        if ($answer -match '^\d+$' -and [int]$answer -ge 1 -and [int]$answer -le $drives.Count) {
            $TargetDrive = $drives[[int]$answer - 1].DeviceID
        } else { $TargetDrive = $answer }
    }
    if ([string]::IsNullOrWhiteSpace($TargetDrive)) { throw 'Select a destination.' }
    if ($TargetDrive -match '^[A-Za-z]:$') { $TargetDrive += '\' }
    $root = [IO.Path]::GetFullPath($TargetDrive)
    $app = Join-Path $root 'SHADER7_AI'
    if (Is-Inside $root $source -or Is-Inside $source $root) { throw 'Choose a destination outside the downloaded source folder.' }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Destination does not exist: $root" }
    if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Destination cannot be a link or junction.' }
    if (-not $ModelOption) {
        if ($NonInteractive) { throw '-ModelOption is required with -NonInteractive.' }
        Write-Host 'Models: [1] Minimal (~3.3 GB, recommended)  [2] All (~9 GB)  [3] Copy existing Ollama models'
        $choice = Read-Host 'Choose 1, 2, or 3 [default: 1]'
        $ModelOption = switch ($choice) { '2' { 'All' } '3' { 'Local' } default { 'Minimal' } }
    }
    $minimumBytes = if ($ModelOption -eq 'All') { 16GB } elseif ($ModelOption -eq 'Minimal') { 8GB } else { 1GB }
    $freeBytes = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))).AvailableFreeSpace
    if ($freeBytes -lt $minimumBytes) {
        throw "Not enough free space. $ModelOption setup needs at least $([math]::Round($minimumBytes / 1GB, 1)) GB free."
    }
    $marker = Join-Path $app '.shader7-build.json'
    if (Test-Path -LiteralPath $app) {
        $item = Get-Item -LiteralPath $app -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'SHADER7_AI cannot be a link or junction.' }
        if ((Get-ChildItem -LiteralPath $app -Force | Select-Object -First 1) -and
            (-not (Test-Path -LiteralPath $marker) -or (Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).app -ne 'shader7-ai')) {
            throw "SHADER7_AI already contains files not owned by this builder: $app"
        }
    }
    New-Item -ItemType Directory -Path $app -Force | Out-Null
    @{ app = 'shader7-ai'; complete = $false } | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    $appDir = Join-Path $app 'app'
    $modelsDir = Join-Path $app 'models'
    New-Item -ItemType Directory -Path $appDir, $modelsDir -Force | Out-Null

    Write-Host '[1/4] Copying application files...'
    foreach ($name in @('README.md', 'LICENSE', 'app.ico', 'autorun.inf', 'Modelfile_webdev',
                       'Install_To_PC.bat', 'Uninstall_From_PC.bat', 'Uninstall_SHADER7_AI.ps1',
                       'Launch_SHADER7_AI.vbs', 'Launch_SHADER7_AI.bat', 'Launch_CPU_Mode.bat',
                       'Launch_GPU_Mode.bat', 'Check_USB_Models.bat', 'Fix_Shortcuts.bat',
                       'Repair_Launchers.ps1')) {
        Copy-Required $name $app
    }
    foreach ($name in @('server.py', 'verify_models.py', 'app.js', 'index.html', 'style.css',
                       'logo.png', 'app.ico', 'designer_prompt.txt', 'designer_reference.html',
                       'designer_editor_reference.html')) {
        Copy-Required (Join-Path 'app' $name) $app
    }

    Write-Host '[2/4] Preparing portable Python and Ollama...'
    $pythonDir = Join-Path $appDir 'python'
    $pythonExe = Join-Path $pythonDir 'python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $localPython = Join-Path $source 'app\python'
        if (Test-Path -LiteralPath (Join-Path $localPython 'python.exe')) {
            Copy-Item -LiteralPath $localPython -Destination $appDir -Recurse -Force
        } else {
            Download-Zip 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip' $pythonDir
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $pythonDir 'pythonw.exe'))) { throw 'Portable Python is incomplete.' }
    $ollamaDir = Join-Path $appDir 'ollama'
    $ollamaExe = Join-Path $ollamaDir 'ollama.exe'
    if (-not (Test-Path -LiteralPath $ollamaExe)) {
        $localOllama = Join-Path $source 'app\ollama'
        if (Test-Path -LiteralPath (Join-Path $localOllama 'ollama.exe')) {
            Copy-Item -LiteralPath $localOllama -Destination $appDir -Recurse -Force
        } else {
            Download-Zip 'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip' $ollamaDir
        }
    }
    if (-not (Test-Path -LiteralPath $ollamaExe)) { throw 'Portable Ollama is incomplete.' }

    Write-Host "[3/4] Installing $ModelOption models..."
    if ($ModelOption -eq 'Local') {
        if (-not $LocalModelsPath) { $LocalModelsPath = Join-Path $env:USERPROFILE '.ollama\models' }
        $localModels = [IO.Path]::GetFullPath($LocalModelsPath)
        if (Is-Inside $localModels $modelsDir -or Is-Inside $modelsDir $localModels) { throw 'Model source and destination overlap.' }
        if (-not (Test-Path -LiteralPath (Join-Path $localModels 'manifests') -PathType Container)) { throw "No Ollama manifests found at $localModels" }
        $localBytes = (Get-ChildItem -LiteralPath $localModels -Recurse -File | Measure-Object -Property Length -Sum).Sum
        $freeBytes = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))).AvailableFreeSpace
        if ($freeBytes -lt $localBytes + 1GB) { throw 'Not enough free space to copy the local model cache.' }
        foreach ($item in Get-ChildItem -LiteralPath $localModels -Force) {
            Copy-Item -LiteralPath $item.FullName -Destination $modelsDir -Recurse -Force
        }
    } else {
        $portProbe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        $portProbe.Start()
        $port = $portProbe.LocalEndpoint.Port
        $portProbe.Stop()
        $env:OLLAMA_HOST = "127.0.0.1:$port"
        $env:OLLAMA_MODELS = $modelsDir
        $buildServer = Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $ollamaDir -PassThru -WindowStyle Hidden
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            if ($buildServer.HasExited) { throw 'Ollama server exited during setup.' }
            try {
                Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/tags" -UseBasicParsing -TimeoutSec 1 | Out-Null
                $ready = $true
                break
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw 'Ollama server did not start within 30 seconds.' }
        $wanted = if ($ModelOption -eq 'All') {
            @('qwen2.5:3b', 'deepseek-r1:1.5b', 'qwen2.5-coder:1.5b', 'llama3.2:3b', 'llama3.2:1b', 'gemma2:2b')
        } else { @('qwen2.5:3b', 'llama3.2:1b') }
        foreach ($model in $wanted) {
            Write-Host "Downloading $model..."
            & $ollamaExe pull $model
            if ($LASTEXITCODE -ne 0) { throw "Model download failed: $model" }
        }
        if ($ModelOption -eq 'All') {
            & $ollamaExe create qwen-designer -f (Join-Path $app 'Modelfile_webdev')
            if ($LASTEXITCODE -ne 0) { throw 'Could not create qwen-designer.' }
        }
    }

    Write-Host '[4/4] Verifying models and creating portable launchers...'
    & $pythonExe -B (Join-Path $appDir 'verify_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Model verification failed. Rerun the builder after checking available space and downloads.' }
    & (Join-Path $app 'Repair_Launchers.ps1') -AppDir $app
    @{ app = 'shader7-ai'; complete = $true; models = $ModelOption } |
        ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    Write-Host "Ready at $root. Open 'Launch CPU.cmd' or 'Launch GPU.cmd'." -ForegroundColor Green
} catch {
    Write-Error $_.Exception.Message
    exit 1
} finally {
    if ($buildServer -and -not $buildServer.HasExited) {
        & taskkill.exe /PID $buildServer.Id /T /F | Out-Null
    }
    $env:OLLAMA_HOST = $oldHost
    $env:OLLAMA_MODELS = $oldModels
}
