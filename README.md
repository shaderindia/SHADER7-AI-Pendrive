# SHADER7 AI Pendrive

Run local AI models from a USB drive on a 64-bit Windows 10/11 PC. The builder downloads Python, Ollama, and your chosen models once; afterward the local models work without an internet connection. Optional cloud providers and web search need internet.

## Quick start (no Git required)

1. Download the [repository ZIP](https://github.com/shaderindia/SHADER7-AI-Pendrive/archive/refs/heads/main.zip) and extract it on your PC. Do **not** run the builder inside the ZIP viewer.
2. Connect a USB drive with at least **8 GB free** for the minimal set or **16 GB free** for all models. Use exFAT or NTFS. Existing files on the drive are left in place; the builder creates `SHADER7_AI`, three portable launchers, and optional shortcuts at its root.
3. In the extracted folder, double-click **`Build_AI_Pendrive.bat`**. Choose the USB drive and **Minimal** for the simplest setup. The first build needs internet and can take a while as it downloads model weights.
4. Wait for **“Ready”**. The builder checks every downloaded model file before showing this message. If it fails, read the error, check free space and internet, then run the same builder again.
5. Open the USB drive and double-click **`Launch CPU.cmd`**. On a compatible NVIDIA PC, use **`Launch GPU.cmd`** instead. Your browser opens the local app at `127.0.0.1`.

No administrator rights or system-wide Python/Ollama installation are required. Windows may ask whether to run downloaded scripts; inspect the files before allowing them. The `.cmd` launchers work when the USB drive letter changes. The optional `.lnk` shortcuts need repair after a drive-letter change: run `SHADER7_AI\Fix_Shortcuts.bat`.

## Model choices

| Choice | Models | Approximate model download |
| --- | --- | --- |
| Minimal | `qwen2.5:3b`, `llama3.2:1b` | 3–4 GB |
| All | Six standard models plus `qwen-designer` | 9–12 GB |
| Local | Copies your existing `%USERPROFILE%\.ollama\models` cache | No model download |

`qwen-designer` is created only with **All** or when it already exists in a copied local cache. The repository contains model manifest examples, **not** the large model weights. Cloning or downloading the repository alone is not a working offline installation.

## Install on this PC (optional)

From the built USB drive, double-click **`Install to PC.cmd`**. This copies the app, runtime, and models to `%USERPROFILE%\LocalAI` and creates a CPU-mode desktop shortcut. For GPU mode on the PC copy, run `%USERPROFILE%\LocalAI\Launch_GPU_Mode.bat`. Allow enough free space for the selected models plus 1 GB. You can also install from the app’s menu. To remove this PC copy, run `%USERPROFILE%\LocalAI\Uninstall_From_PC.bat`. The uninstaller keeps your chats and settings.

Chats, settings, and engine logs live in `%USERPROFILE%\LocalAI_Workspace` on each host PC. They are not saved to the USB drive. Do not use the PC install option on an untrusted or shared PC if you do not want that PC to retain those files.

## Requirements and help

- Windows 10 22H2 or newer, 64-bit; at least 8 GB RAM. A USB 3.0 drive or portable SSD is recommended.
- CPU mode works without an NVIDIA GPU. GPU mode needs a supported NVIDIA card and installed driver; if GPU mode reports a CUDA or VRAM error, use CPU mode.
- If launch says Python or Ollama is missing, rerun the builder. If models are missing or corrupt, run `SHADER7_AI\Check_USB_Models.bat`, then rerun the builder.
- For startup errors, inspect `%USERPROFILE%\LocalAI_Workspace\engine-cpu.log` or `engine.log`.
- To use an existing model cache, choose **Local**. A cache without its `blobs` and `manifests` folders will fail verification.

Advanced unattended build:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Build_AI_Pendrive.ps1 -TargetDrive E:\ -ModelOption Minimal -NonInteractive
```

Replace `E:\` with the correct USB drive. For a local cache, use `-ModelOption Local -LocalModelsPath 'C:\path\to\models'`. The builder does not format a drive or delete existing model files.

Licensed under [MIT](LICENSE). Runtime downloads come from [Python](https://www.python.org/downloads/) and [Ollama](https://github.com/ollama/ollama/releases).
