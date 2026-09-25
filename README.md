# SHADER7 AI — Portable AI Pendrive (Edition 1.5.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20x64%20(10%2F11)-brightgreen.svg)]()
[![Backend](https://img.shields.io/badge/Backend-NVIDIA%20CUDA%2012%20%7C%20CPU-orange.svg)]()
[![Models](https://img.shields.io/badge/Local%20Models-6%20Models%20%2B%20Web%20Designer-purple.svg)]()

Turn any standard USB flash drive into a 100% offline, plug-and-play AI workstation for 64-bit Windows. Carry your private local LLMs, coding assistant, and web designer in your pocket—zero cloud dependencies, zero data leakage, and zero driver installation required on host PCs.

---

## ⚡ Key Highlights

- **Dual Hardware Execution Modes:**
  - **NVIDIA GPU Mode (CUDA 12):** 100% full model VRAM placement. Optimized and benchmarked for 4 GB GPUs (like the GTX 1050 Ti) and higher.
  - **Pure CPU Mode:** 100% system RAM execution with enforced 0% GPU allocation. Runs on any modern Windows 64-bit PC.
- **7 Built-in Local AI Models (8.38 GiB total):**
  - General chat, code generation, mathematical reasoning, compact models, and a dedicated offline website builder.
- **Native Windows Desktop Window:**
  - Automatically runs inside Microsoft Edge App Mode (or Chrome) without address bars, tabs, or SmartScreen interruptions.
- **Live Hardware Telemetry:**
  - High-performance, zero-flicker native Win32 hardware monitors: CPU usage, RAM utilization, GPU temperature, VRAM allocation, and disk space.
- **Offline Responsive Web Designer (`qwen-designer`):**
  - 8192-token context with worked-in UI architecture templates. Generates single-file responsive HTML/CSS/JS websites with a sandboxed in-memory live preview.
- **Zero USB Host Data Leakage:**
  - Chat histories, sessions, and encrypted API keys remain exclusively on the host PC inside `~/LocalAI_Workspace`. Your USB drive never stores private conversation logs.
- **1-Click PC Installation & Clean Removal:**
  - Move everything to SSD (`~/LocalAI`) with one click, or safely uninstall at any time without touching shared models or chats.

---

## 📦 What's on the Pendrive

When deployed on a USB drive, the filesystem is structured as follows:

```text
USB_ROOT (e.g. D:\)
├── Install.lnk                   # 1-Click installer to copy app & models to PC SSD
├── Launch Now in CPU.lnk         # Launches AI in CPU-only mode (uses system RAM)
├── Launch Now in GPU.lnk         # Launches AI with NVIDIA CUDA 12 GPU acceleration
├── autorun.inf                   # Pendrive label and icon
└── SHADER7_AI/
    ├── Launch_SHADER7_AI.vbs     # Silent background desktop window launcher
    ├── Launch_SHADER7_AI.bat     # Fallback batch launcher
    ├── Launch_GPU_Mode.bat       # Direct GPU launcher
    ├── Launch_CPU_Mode.bat       # Direct CPU launcher
    ├── Check_USB_Models.bat      # SHA-256 integrity validator for all model blobs
    ├── Install_To_PC.bat         # Host SSD installer
    ├── Uninstall_From_PC.bat     # Host SSD uninstaller
    ├── Uninstall_SHADER7_AI.ps1  # Safe PowerShell uninstaller
    ├── Fix_Shortcuts.bat         # Re-links root shortcuts if drive letter changes
    ├── Modelfile_webdev          # Modelfile for offline website designer
    ├── README.md                 # Full user and architecture documentation
    ├── app/
    │   ├── server.py             # Pure Python 3.12 HTTP server & Ollama orchestrator
    │   ├── app.js                # Web application logic, telemetry & streaming client
    │   ├── index.html            # App interface & desktop layout
    │   ├── style.css             # Dark-themed responsive styles
    │   ├── verify_models.py      # Automated cryptographic checksum verifier
    │   ├── designer_prompt.txt   # Designer system prompt
    │   ├── designer_reference.html        # Clean studio UI template
    │   ├── designer_editor_reference.html # Interactive resume builder template
    │   ├── python/               # Embedded portable Python 3.12 (standard library)
    │   └── ollama/               # Portable Ollama engine & CUDA 12 runners
    └── models/
        ├── blobs/                # SHA-256 model weights (GGUF layers)
        ├── manifests/            # Model manifests & layer definitions
        └── metadata/             # Ollama model metadata
```

---

## 🚀 How to Build Your Own AI Pendrive

You can turn any 16 GB, 32 GB, or 64 GB USB 3.0 flash drive into your own portable AI drive in a few minutes.

### Method 1: Automated 1-Click Builder (Recommended)

1. **Clone this repository** to your PC:
   ```cmd
   git clone https://github.com/shaderindia/SHADER7-AI-Pendrive.git
   cd SHADER7-AI-Pendrive
   ```
2. **Plug in your USB flash drive** (formatted as exFAT or NTFS).
3. **Double-click `Build_AI_Pendrive.bat`**:
   - The interactive installer will detect your USB drive.
   - It deploys all app code, launchers, and assets.
   - Automatically downloads official **Portable Python 3.12** and **Portable Ollama**.
   - Pulls your chosen models directly into the pendrive's repository.
   - Builds the custom `qwen-designer` model.
   - Generates working root shortcuts tailored to your USB drive letter.
   - Runs a full SHA-256 integrity check.
4. **Done!** Unplug your drive and plug it into any Windows PC to run local AI anywhere!

---

### Method 2: Manual Setup

If you prefer to configure components manually:

#### 1. Copy Files
Copy all files from this repository into a folder named `SHADER7_AI` on your USB drive.

#### 2. Install Portable Python
Download the official Windows 64-bit embeddable Python package:
- [Python 3.12.9 Windows embeddable package (64-bit)](https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip)
- Extract the zip into `SHADER7_AI\app\python`.
- Open `python312._pth` in a text editor and uncomment `import site`.

#### 3. Install Portable Ollama
Download the official Ollama Windows binary release:
- [Ollama Windows AMD64 Zip](https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip)
- Extract the zip contents into `SHADER7_AI\app\ollama`.

#### 4. Pull Local Models
Open PowerShell in the `SHADER7_AI` directory and set the models directory to the USB drive:
```powershell
$env:OLLAMA_MODELS = "$PWD\models"
.\app\ollama\ollama.exe pull qwen2.5:3b
.\app\ollama\ollama.exe pull deepseek-r1:1.5b
.\app\ollama\ollama.exe pull qwen2.5-coder:1.5b
.\app\ollama\ollama.exe pull llama3.2:3b
.\app\ollama\ollama.exe pull llama3.2:1b
.\app\ollama\ollama.exe pull gemma2:2b
.\app\ollama\ollama.exe create qwen-designer -f Modelfile_webdev
```

#### 5. Generate Root Shortcuts
Run `SHADER7_AI\Fix_Shortcuts.bat` to create `Install.lnk`, `Launch Now in CPU.lnk`, and `Launch Now in GPU.lnk` at the root of your USB drive.

---

## 🧠 Included Local AI Models

All 7 models fit within an 8.38 GiB footprint and are specifically selected to balance memory constraints and task versatility:

| Model | Size | Context | Best Used For | Example Prompt |
| :--- | :--- | :--- | :--- | :--- |
| **qwen2.5:3b** *(Default)* | ~2.0 GB | 4096 | Everyday knowledge, explanations, multilingual writing, and structured summaries. | *"Rewrite this email to sound professional yet warm."* |
| **deepseek-r1:1.5b** | ~1.1 GB | 4096 | Mathematical step-by-step reasoning, logic puzzles, and deep analytical queries. | *"Solve 3x + 7 = 22 and explain each step in detail."* |
| **qwen2.5-coder:1.5b** | ~986 MB | 4096 | Writing, debugging, explaining, and refactoring scripts (Python, JS, C++, Go). | *"Write a Python script to monitor folder changes and log them."* |
| **llama3.2:3b** | ~1.9 GB | 4096 | Creative prose, conversational dialogue, brainstorming, and balanced reasoning. | *"Give me 5 distinct concepts for an indie game set in space."* |
| **llama3.2:1b** | ~1.3 GB | 4096 | Rapid answers, instant text rewrites, bullet points. Fastest measured model (~50 tok/s). | *"Convert these raw notes into a 5-point action plan."* |
| **gemma2:2b** | ~1.6 GB | 4096 | General English conversation, creative ideation, and clear drafting. | *"Draft a polite reminder message for project deliverables."* |
| **qwen-designer:latest** | ~986 MB | 8192 | Automated offline website coding: builds responsive, single-file HTML/CSS/JS applications. | *"Build an offline landing page for an artisan coffee roaster."* |

---

## 💻 Hardware Requirements

| Component | Minimum (CPU Mode) | Recommended (GPU Mode) |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 or 11 (64-bit) | Windows 10 or 11 (64-bit) |
| **Processor** | Intel Core i3 / AMD Ryzen 3 or higher | Intel Core i5 / AMD Ryzen 5 or higher |
| **System RAM** | 8 GB RAM | 8 GB - 16 GB RAM |
| **Graphics Card** | Any integrated or dedicated graphics | NVIDIA GTX 1050 Ti (4 GB VRAM) or higher |
| **CUDA Driver** | Not required | NVIDIA Driver with CUDA 12 support |
| **USB Storage** | USB 3.0+ flash drive with at least 16 GB free space | USB 3.0+ or SSD-based flash drive (32 GB - 64 GB) |

---

## 🔒 Privacy & Security

1. **Host-Isolated Data Storage:**
   - Conversations, settings, and application states are saved **only** on the local PC at:
     `%USERPROFILE%\LocalAI_Workspace`
   - Unplugging the USB drive leaves zero chat logs, personal notes, or user files on the USB.
2. **Windows DPAPI Encryption:**
   - Optional API keys (e.g. NVIDIA NIM or OpenRouter) are encrypted with Windows Data Protection API (`CryptProtectData`), bound to that specific Windows user account.
3. **Loopback Protection & Sandboxing:**
   - The application server binds exclusively to `127.0.0.1`.
   - Prevents CSRF and DNS-rebinding attacks with unique session tokens.
   - Built-in website previews run inside a restricted, sandboxed `<iframe>` with network access disabled.

---

## 🛠️ Verification & Troubleshooting

- **Check Model Integrity:**
  Double-click `Check_USB_Models.bat` inside `SHADER7_AI`. It computes SHA-256 checksums for every model blob and verifies them against the official manifests.
- **Drive Letter Changes:**
  If you plug the drive into a different PC and the root `.lnk` shortcuts point to the wrong drive letter, simply double-click `SHADER7_AI\Fix_Shortcuts.bat` or run `Launch_SHADER7_AI.vbs` directly.
- **Diagnostics:**
  Inspect `%USERPROFILE%\LocalAI_Workspace\engine.log` (GPU mode) or `engine-cpu.log` (CPU mode) if an engine fails to start.

---

## 📄 License & Credits

- Licensed under the [MIT License](LICENSE).
- Built with [Ollama](https://github.com/ollama/ollama) and [Python](https://www.python.org).
- Original concept & architecture by **Nishikant Xalxo** ([SHADER7](https://shader7.com)).
