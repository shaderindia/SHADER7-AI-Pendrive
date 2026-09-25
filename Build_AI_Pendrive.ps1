<#
.SYNOPSIS
    SHADER7 AI — 1-Click AI Pendrive Creator & Setup Tool
.DESCRIPTION
    Sets up a complete portable AI environment on any USB flash drive or folder.
    Configures portable Python 3.12, portable Ollama, models, and root launchers.
#>

param(
    [string]$TargetDrive,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "               SHADER7 AI — PORTABLE AI PENDRIVE CREATOR               " -ForegroundColor Cyan
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host " This tool turns any USB flash drive into a plug-and-play offline AI"
Write-Host " workstation for 64-bit Windows, complete with CPU & NVIDIA GPU modes."
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------------------
# 1. TARGET DRIVE SELECTION
# -----------------------------------------------------------------------------
$removableDrives = @(Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 2 })

if (-not $TargetDrive) {
    Write-Host "[1/6] Select Destination Drive:" -ForegroundColor Yellow
    if ($removableDrives.Count -gt 0) {
        Write-Host "Detected Removable Drives (USB):" -ForegroundColor Green
        for ($i = 0; $i -lt $removableDrives.Count; $i++) {
            $d = $removableDrives[$i]
            $freeGB = [math]::Round($d.FreeSpace / 1GB, 1)
            $totalGB = [math]::Round($d.Size / 1GB, 1)
            Write-Host "  [$($i+1)] $($d.DeviceID) ($($d.VolumeName)) - Free: $freeGB GB / Total: $totalGB GB"
        }
        Write-Host "  [C] Custom Path or Drive Letter"
        Write-Host ""
        $choice = Read-Host "Select drive number [1-$($removableDrives.Count)] or C"
        if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $removableDrives.Count) {
            $TargetDrive = $removableDrives[[int]$choice - 1].DeviceID
        } else {
            $TargetDrive = Read-Host "Enter target drive letter or folder path (e.g. E: or D:\)"
        }
    } else {
        Write-Host "No removable USB drives detected." -ForegroundColor DarkYellow
        $TargetDrive = Read-Host "Enter target drive letter or folder path (e.g. E: or D:\)"
    }
}

$TargetDrive = $TargetDrive.TrimEnd('\')
if ($TargetDrive.Length -eq 2 -and $TargetDrive[1] -eq ':') {
    $RootPath = $TargetDrive + "\"
} else {
    $RootPath = [IO.Path]::GetFullPath($TargetDrive)
}

if (-not (Test-Path -LiteralPath $RootPath)) {
    try {
        New-Item -ItemType Directory -Path $RootPath -Force | Out-Null
    } catch {
        Write-Error "Target path '$RootPath' does not exist and could not be created."
        exit 1
    }
}

$Shader7Folder = Join-Path $RootPath "SHADER7_AI"
Write-Host "Target Pendrive Root: $RootPath" -ForegroundColor Green
Write-Host "Installation Folder: $Shader7Folder" -ForegroundColor Green
Write-Host ""

# -----------------------------------------------------------------------------
# 2. COPY REPO ASSETS & LAUNCHERS
# -----------------------------------------------------------------------------
Write-Host "[2/6] Deploying application files and launchers..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $Shader7Folder -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Shader7Folder "app") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Shader7Folder "models\manifests") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Shader7Folder "models\metadata") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Shader7Folder "models\blobs") -Force | Out-Null

# Copy root launchers
$rootLaunchers = @(
    "Check_USB_Models.bat", "Install_To_PC.bat", "Launch_CPU_Mode.bat",
    "Launch_GPU_Mode.bat", "Launch_SHADER7_AI.bat", "Launch_SHADER7_AI.vbs",
    "Modelfile_webdev", "Uninstall_From_PC.bat", "Uninstall_SHADER7_AI.ps1",
    "autorun.inf", "app.ico", "Fix_Shortcuts.bat"
)
foreach ($f in $rootLaunchers) {
    $srcFile = Join-Path $ScriptDir $f
    if (Test-Path -LiteralPath $srcFile) {
        Copy-Item -LiteralPath $srcFile -Destination (Join-Path $Shader7Folder $f) -Force
    }
}

# Copy app files
$appFiles = @(
    "app.ico", "logo.png", "verify_models.py", "style.css",
    "app.js", "index.html", "server.py", "designer_prompt.txt",
    "designer_reference.html", "designer_editor_reference.html"
)
foreach ($f in $appFiles) {
    $srcFile = Join-Path $ScriptDir "app\$f"
    if (Test-Path -LiteralPath $srcFile) {
        Copy-Item -LiteralPath $srcFile -Destination (Join-Path $Shader7Folder "app\$f") -Force
    }
}

# Copy manifests and metadata if present
if (Test-Path -LiteralPath (Join-Path $ScriptDir "models\manifests")) {
    Copy-Item -Path (Join-Path $ScriptDir "models\manifests\*") -Destination (Join-Path $Shader7Folder "models\manifests") -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath (Join-Path $ScriptDir "models\metadata")) {
    Copy-Item -Path (Join-Path $ScriptDir "models\metadata\*") -Destination (Join-Path $Shader7Folder "models\metadata") -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Application code deployed." -ForegroundColor Green
Write-Host ""

# -----------------------------------------------------------------------------
# 3. CONFIGURE PORTABLE PYTHON
# -----------------------------------------------------------------------------
Write-Host "[3/6] Configuring Portable Python 3.12..." -ForegroundColor Yellow
$pyDest = Join-Path $Shader7Folder "app\python"
$pyExe = Join-Path $pyDest "python.exe"

if (-not (Test-Path -LiteralPath $pyExe)) {
    # Check if local source has portable python
    $localPy = Join-Path $ScriptDir "app\python"
    $dPy = "D:\SHADER7_AI\app\python"
    
    if (Test-Path -LiteralPath (Join-Path $localPy "python.exe")) {
        Write-Host "Copying portable Python from repo..."
        Copy-Item -Path $localPy -Destination (Join-Path $Shader7Folder "app") -Recurse -Force
    } elseif (Test-Path -LiteralPath (Join-Path $dPy "python.exe")) {
        Write-Host "Copying portable Python from existing USB installation..."
        Copy-Item -Path $dPy -Destination (Join-Path $Shader7Folder "app") -Recurse -Force
    } else {
        Write-Host "Downloading official Python 3.12 Windows embeddable package..." -ForegroundColor Cyan
        $pyUrl = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
        $pyZip = Join-Path $env:TEMP "python-3.12-embed-amd64.zip"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pyUrl -OutFile $pyZip -UseBasicParsing
        New-Item -ItemType Directory -Path $pyDest -Force | Out-Null
        Expand-Archive -Path $pyZip -DestinationPath $pyDest -Force
        Remove-Item -Path $pyZip -Force -ErrorAction SilentlyContinue
        
        # Ensure site-packages / import site is enabled
        $pthFile = Get-ChildItem -Path $pyDest -Filter "*._pth" | Select-Object -First 1
        if ($pthFile) {
            $lines = Get-Content $pthFile.FullName
            $lines = $lines | ForEach-Object { if ($_ -eq "#import site") { "import site" } else { $_ } }
            Set-Content -Path $pthFile.FullName -Value $lines
        }
    }
}
Write-Host "Portable Python ready." -ForegroundColor Green
Write-Host ""

# -----------------------------------------------------------------------------
# 4. CONFIGURE PORTABLE OLLAMA ENGINE
# -----------------------------------------------------------------------------
Write-Host "[4/6] Configuring Portable Ollama runtime..." -ForegroundColor Yellow
$ollamaDest = Join-Path $Shader7Folder "app\ollama"
$ollamaExe = Join-Path $ollamaDest "ollama.exe"

if (-not (Test-Path -LiteralPath $ollamaExe)) {
    $dOllama = "D:\SHADER7_AI\app\ollama"
    $localOllamaProg = Join-Path $env:LOCALAPPDATA "Programs\Ollama"

    if (Test-Path -LiteralPath (Join-Path $dOllama "ollama.exe")) {
        Write-Host "Copying Ollama runtime from existing USB..."
        Copy-Item -Path $dOllama -Destination (Join-Path $Shader7Folder "app") -Recurse -Force
    } elseif (Test-Path -LiteralPath (Join-Path $localOllamaProg "ollama.exe")) {
        Write-Host "Copying Ollama runtime from PC installation..."
        Copy-Item -Path $localOllamaProg -Destination $ollamaDest -Recurse -Force
    } else {
        Write-Host "Downloading official Ollama Windows binary zip..." -ForegroundColor Cyan
        $ollamaUrl = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
        $ollamaZip = Join-Path $env:TEMP "ollama-windows-amd64.zip"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $ollamaUrl -OutFile $ollamaZip -UseBasicParsing
        New-Item -ItemType Directory -Path $ollamaDest -Force | Out-Null
        Expand-Archive -Path $ollamaZip -DestinationPath $ollamaDest -Force
        Remove-Item -Path $ollamaZip -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Portable Ollama ready." -ForegroundColor Green
Write-Host ""

# -----------------------------------------------------------------------------
# 5. CONFIGURE MODELS
# -----------------------------------------------------------------------------
Write-Host "[5/6] Setting up AI models..." -ForegroundColor Yellow
$modelsDest = Join-Path $Shader7Folder "models"
$blobsDest = Join-Path $modelsDest "blobs"

# Check if models already exist on D: or PC
$existingUsbBlobs = "D:\SHADER7_AI\models\blobs"
$existingPcBlobs = Join-Path $env:USERPROFILE ".ollama\models\blobs"

Write-Host "Choose model setup method:"
Write-Host "  [1] Copy existing models from this PC / connected USB (Fastest, ~0 MB download)" -ForegroundColor Green
Write-Host "  [2] Pull all 6 standard models via Ollama CDN (~8.4 GB download)"
Write-Host "  [3] Pull minimal models only (Qwen 3B + Llama 1B, ~3.3 GB download)"
Write-Host "  [4] Skip model download (Configure later)"
$modelChoice = Read-Host "Select option [1-4] (Default: 1)"

if ($modelChoice -eq "2" -or $modelChoice -eq "3") {
    $modelsToPull = if ($modelChoice -eq "2") {
        @("qwen2.5:3b", "deepseek-r1:1.5b", "qwen2.5-coder:1.5b", "llama3.2:3b", "llama3.2:1b", "gemma2:2b")
    } else {
        @("qwen2.5:3b", "llama3.2:1b")
    }

    Write-Host "Pulling models directly to USB models repository..." -ForegroundColor Cyan
    $env:OLLAMA_MODELS = $modelsDest
    foreach ($m in $modelsToPull) {
        Write-Host "Pulling $m..." -ForegroundColor Yellow
        & $ollamaExe pull $m
    }

    # Build qwen-designer if qwen2.5-coder:1.5b was pulled
    if ("qwen2.5-coder:1.5b" -in $modelsToPull) {
        Write-Host "Creating qwen-designer from Modelfile_webdev..." -ForegroundColor Cyan
        $mfPath = Join-Path $Shader7Folder "Modelfile_webdev"
        & $ollamaExe create qwen-designer -f $mfPath
    }
} elseif ($modelChoice -ne "4") {
    # Default: Copy existing models
    if (Test-Path -LiteralPath $existingUsbBlobs -and (Get-ChildItem -Path $existingUsbBlobs).Count -gt 0 -and ($RootPath -ne "D:\")) {
        Write-Host "Copying models from D:\SHADER7_AI\models..." -ForegroundColor Cyan
        Copy-Item -Path "D:\SHADER7_AI\models\*" -Destination $modelsDest -Recurse -Force
    } elseif (Test-Path -LiteralPath $existingPcBlobs -and (Get-ChildItem -Path $existingPcBlobs).Count -gt 0) {
        Write-Host "Copying models from PC ~/.ollama/models..." -ForegroundColor Cyan
        Copy-Item -Path "$existingPcBlobs\*" -Destination $blobsDest -Recurse -Force
        Copy-Item -Path (Join-Path $env:USERPROFILE ".ollama\models\manifests\*") -Destination (Join-Path $modelsDest "manifests") -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "No local model cache found. Please run Option 2 to download models." -ForegroundColor DarkYellow
    }
}
Write-Host "Model setup step finished." -ForegroundColor Green
Write-Host ""

# -----------------------------------------------------------------------------
# 6. DYNAMIC ROOT SHORTCUTS & VERIFICATION
# -----------------------------------------------------------------------------
Write-Host "[6/6] Generating root shortcuts and checking integrity..." -ForegroundColor Yellow

$wsh = New-Object -ComObject WScript.Shell

# Install shortcut
$scInstall = $wsh.CreateShortcut((Join-Path $RootPath "Install.lnk"))
$scInstall.TargetPath = Join-Path $Shader7Folder "Install_To_PC.bat"
$scInstall.WorkingDirectory = $Shader7Folder
$scInstall.IconLocation = (Join-Path $Shader7Folder "app.ico") + ",0"
$scInstall.Save()

# CPU mode shortcut
$scCpu = $wsh.CreateShortcut((Join-Path $RootPath "Launch Now in CPU.lnk"))
$scCpu.TargetPath = Join-Path $Shader7Folder "Launch_SHADER7_AI.vbs"
$scCpu.Arguments = "cpu"
$scCpu.WorkingDirectory = $Shader7Folder
$scCpu.IconLocation = (Join-Path $Shader7Folder "app.ico") + ",0"
$scCpu.Save()

# GPU mode shortcut
$scGpu = $wsh.CreateShortcut((Join-Path $RootPath "Launch Now in GPU.lnk"))
$scGpu.TargetPath = Join-Path $Shader7Folder "Launch_SHADER7_AI.vbs"
$scGpu.Arguments = "gpu"
$scGpu.WorkingDirectory = $Shader7Folder
$scGpu.IconLocation = (Join-Path $Shader7Folder "app.ico") + ",0"
$scGpu.Save()

Write-Host "Root shortcuts created on: $RootPath" -ForegroundColor Green

# Run verify_models.py
$verifyScript = Join-Path $Shader7Folder "app\verify_models.py"
if (Test-Path -LiteralPath $pyExe -and (Test-Path -LiteralPath $verifyScript)) {
    Write-Host "Running model verification check..." -ForegroundColor Cyan
    & $pyExe -B $verifyScript
}

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Green
Write-Host "                    AI PENDRIVE CREATED SUCCESSFULLY!                  " -ForegroundColor Green
Write-Host "=======================================================================" -ForegroundColor Green
Write-Host " Location: $RootPath"
Write-Host " To start using your AI pendrive:"
Write-Host "   - Double-click 'Launch Now in GPU.lnk' for NVIDIA GPU acceleration"
Write-Host "   - Double-click 'Launch Now in CPU.lnk' for pure CPU / RAM mode"
Write-Host "   - Double-click 'Install.lnk' to install to local PC"
Write-Host "=======================================================================" -ForegroundColor Green
Write-Host ""
