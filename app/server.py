#!/usr/bin/env python3
"""SHADER7 AI portable desktop app. Standard library only, Windows x64."""
import atexit
import base64
import ctypes
import hashlib
import html
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import winreg
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.5.0"
BACKEND_MODE = "cpu" if "--cpu" in sys.argv else "gpu"
ENGINE_LABEL = BACKEND_MODE.upper()
APP_ID = "shader7-ai"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USB_ROOT = os.path.dirname(SCRIPT_DIR)
MODEL_DIR = os.path.join(USB_ROOT, "models")
OLLAMA_EXE = os.path.join(SCRIPT_DIR, "ollama", "ollama.exe")
HOST_DIR = os.path.abspath(os.environ.get("SHADER7_WORKSPACE", os.path.join(os.path.expanduser("~"), "LocalAI_Workspace")))
HOST_CHATS_FILE = os.path.join(HOST_DIR, "chats.json")
HOST_SETTINGS_FILE = os.path.join(HOST_DIR, "settings.json")
HOST_APP_PROFILE = os.path.join(HOST_DIR, "app_profile_cpu" if BACKEND_MODE == "cpu" else "app_profile")
SESSION_TOKEN = secrets.token_urlsafe(32)
PORT = 8080
OLLAMA_TARGET = ""
OLLAMA_PROCESS = None
BACKEND_ERROR = f"Starting {ENGINE_LABEL} engine..."
BACKEND_READY = False
BACKEND_RUNTIME = ""
GPU_STARTUP_TIMEOUT = 110
GPU_CONTEXT = 4096
GPU_KEEP_ALIVE = "30m"
GPU_OPTIONS = {"num_ctx": GPU_CONTEXT, "num_gpu": 999, "num_batch": 512}
CPU_OPTIONS = {"num_ctx": GPU_CONTEXT, "num_gpu": 0, "num_batch": 128}

DESIGNER_MODELS = {"qwen-designer:latest", "qwen-designer:1.5b", "qwen-designer"}
DESIGNER_CONTEXT = 8192
PREVIEWS = {}
PREVIEW_LOCK = threading.Lock()
PREVIEW_TTL = 15 * 60

def engine_options(model=""):
    options = dict(CPU_OPTIONS if BACKEND_MODE == "cpu" else GPU_OPTIONS)
    if model in DESIGNER_MODELS:
        options["num_ctx"] = DESIGNER_CONTEXT
    return options

def designer_payload(data):
    if data.get("model") not in DESIGNER_MODELS:
        return data
    prompt = Path(SCRIPT_DIR, "designer_prompt.txt").read_text(encoding="utf-8")
    messages = data.get("messages", [])
    if not isinstance(messages, list) or any(not isinstance(m, dict) or not isinstance(m.get("content"), str) for m in messages):
        raise ValueError("Designer messages must contain text.")
    context = [m["content"] for m in messages if m.get("role") == "system"]
    conversation = [m for m in messages if m.get("role") in ("user", "assistant")]
    # Keep the original brief and latest two exchanges; old full HTML versions
    # otherwise consume the context before the model can write the next version.
    if len(conversation) > 5:
        conversation = [conversation[0], *conversation[-4:]]
    if context:
        prompt += "\n\nAdditional reference context (not output-format instructions):\n" + "\n".join(context)
    options = {"temperature": 0.35, "top_p": 0.9, "repeat_penalty": 1.05, **data.get("options", {})}
    options["num_predict"] = min(3072, max(1, int(options.get("num_predict", 3072))))
    latest = next((m["content"] for m in reversed(conversation) if m["role"] == "user"), "")
    examples = []
    if re.search(r"\b(build|design|create|website|landing|page|app|repair)\b", latest, re.I):
        editor = bool(re.search(r"\b(resume|résumé|cv|editor)\b|live preview", latest, re.I))
        filename = "designer_editor_reference.html" if editor else "designer_reference.html"
        reference = Path(SCRIPT_DIR, filename).read_text(encoding="utf-8")
        example_request = ("Build a responsive resume editor with live preview, add/remove experience and print." if editor else
                           "Build a small editorial-style studio website with working service category filters. Use offline HTML, CSS and JavaScript.")
        examples = [{"role": "user", "content": example_request},
                    {"role": "assistant", "content": "```html\n" + reference + "\n```"}]
    return {**data, "messages": [{"role": "system", "content": prompt}, *examples, *conversation], "options": options}

def save_preview(code):
    if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > 512 * 1024:
        raise ValueError("Preview must contain HTML smaller than 512 KB.")
    with PREVIEW_LOCK:
        now = time.monotonic()
        for key in list(PREVIEWS):
            if PREVIEWS[key][0] <= now:
                del PREVIEWS[key]
        while len(PREVIEWS) >= 8:
            del PREVIEWS[next(iter(PREVIEWS))]
        key = secrets.token_urlsafe(24)
        PREVIEWS[key] = (now + PREVIEW_TTL, code)
    return "/preview/" + key

def read_preview(key):
    with PREVIEW_LOCK:
        entry = PREVIEWS.get(key)
        if not entry or entry[0] <= time.monotonic():
            PREVIEWS.pop(key, None)
            return None
        return entry[1]


def instance_id():
    return hashlib.sha256((os.path.normcase(USB_ROOT) + HOST_DIR + BACKEND_MODE).encode()).hexdigest()
GPU_REQUEST_LOCK = threading.Lock()
GPU_MODEL = ""
LOAD_STATE_LOCK = threading.RLock()
LOAD_STATE = {"phase": "idle", "model": "", "started": None, "event_id": 0,
              "estimate_seconds": None, "estimate_source": "initial", "elapsed_seconds": 0, "error": ""}
MODEL_SIZES = {}
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
DATA_LOCK = threading.RLock()
INSTALL_LOCK = threading.Lock()
BACKEND_LOCK = threading.RLock()
STARTUP_LOCK = threading.Lock()
STOP_EVENT = threading.Event()
KEY_FIELDS = ("nvidia_api_key", "openrouter_api_key")
DEFAULT_SETTINGS = {"web_search": False, **dict.fromkeys(KEY_FIELDS, "")}
install_state = {"status": "idle", "progress": 0, "step": "", "message": ""}
install_cancel_flag = False

def within(path, parent):
    path, parent = os.path.realpath(path), os.path.realpath(parent)
    try:
        return os.path.normcase(os.path.commonpath([path, parent])) == os.path.normcase(parent)
    except ValueError:
        return False

def assert_not_on_pendrive(filepath):
    if not within(filepath, os.path.expanduser("~")):
        raise PermissionError("Private storage must be inside your Windows user profile.")
    if within(filepath, USB_ROOT):
        raise PermissionError("Private storage must be separate from the application.")
    drive = os.path.splitdrive(os.path.realpath(filepath))[0] + os.sep
    if ctypes.windll.kernel32.GetDriveTypeW(drive) == 2:
        raise PermissionError("Private storage cannot be on a removable drive.")

def read_json(path, default):
    with DATA_LOCK:
        if not os.path.exists(path):
            return default.copy() if hasattr(default, "copy") else default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            backup = path + ".bak"
            if os.path.exists(backup):
                with open(backup, encoding="utf-8") as f:
                    return json.load(f)
            raise ValueError("Saved data could not be read. The original file has been preserved.")

def atomic_json(path, data, backup=True):
    assert_not_on_pendrive(path)
    with DATA_LOCK:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".shader7-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if backup and os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        json.load(f)
                except (ValueError, OSError):
                    pass  # Keep the last readable backup, not a corrupt file.
                else:
                    shutil.copy2(path, path + ".bak")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

def chat_revision(chats):
    payload = json.dumps(chats, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def chat_transaction():
    """Serialize revisions across threads and USB/installed app processes."""
    with DATA_LOCK:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        name = "Local\\SHADER7-Chats-" + hashlib.sha256(os.path.normcase(os.path.realpath(HOST_CHATS_FILE)).encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = False
        try:
            result = kernel.WaitForSingleObject(handle, 5000)
            if result not in (0, 0x80):  # An abandoned mutex is acquired safely too.
                raise OSError("Saved chats are busy in another copy of the app. Try saving again.")
            acquired = True
            yield
        finally:
            if acquired:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

def protect_secret(value, decrypt=False):
    """Windows DPAPI: bound to the current Windows account, no bundled master key."""
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(DATA_BLOB)]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows could not unlock the saved API key. Re-enter it in settings.")
    try:
        output = ctypes.string_at(result.data, result.size)
        return output.decode("utf-8") if decrypt else base64.b64encode(output).decode("ascii")
    finally:
        free = ctypes.WinDLL("kernel32").LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(result.data)

def load_host_settings():
    settings = {**DEFAULT_SETTINGS, **read_json(HOST_SETTINGS_FILE, DEFAULT_SETTINGS)}
    for field in KEY_FIELDS:
        value = settings.get(field, "")
        if value.startswith("dpapi:v1:"):
            settings[field] = protect_secret(value[9:], decrypt=True)
    return settings

def public_settings(settings):
    result = {"web_search": settings.get("web_search", False),
              "is_installed_on_host": read_json(os.path.join(install_dir(), "shader7-install.json"), {}).get("complete") is True}
    result.update({field + "_configured": bool(settings.get(field)) for field in KEY_FIELDS})
    return result

def save_host_settings(settings):
    stored = {"web_search": bool(settings.get("web_search", False))}
    for field in KEY_FIELDS:
        value = settings.get(field, "").strip()
        stored[field] = "dpapi:v1:" + protect_secret(value) if value else ""
    # Never create plaintext key backups.
    atomic_json(HOST_SETTINGS_FILE, stored, backup=False)
    return True

def init_host_workspace():
    assert_not_on_pendrive(HOST_DIR)
    os.makedirs(HOST_APP_PROFILE, exist_ok=True)
    with chat_transaction():
        if not os.path.exists(HOST_CHATS_FILE):
            atomic_json(HOST_CHATS_FILE, [])
    # Existing settings are migrated to DPAPI on startup; chats stay on this PC.
    save_host_settings(load_host_settings())

# Native Win32 Memory Structure (Zero subprocesses, 0ms, Zero flashing windows)
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

# Hardware Telemetry Cache
_last_stats_time = 0
_cached_stats = None

def get_system_hardware_stats():
    """Retrieves live PC hardware specs, memory, VRAM, and GPU temperature using 100% native Win32 APIs (ZERO PowerShell/console flashing)."""
    global _last_stats_time, _cached_stats
    now = time.time()
    if _cached_stats and (now - _last_stats_time < 3):
        return _cached_stats

    # 1. CPU Name via Windows Registry (0ms, 0 subprocess)
    cpu_name = platform.processor()
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        if val and val.strip():
            cpu_name = val.strip()
    except Exception:
        pass

    stats = {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu_name,
        "gpu": None,
        "ram": None,
        "disks": {}
    }

    # 2. RAM Info via Win32 Kernel32 API (0ms, 0 subprocess)
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_gb = round(stat.ullTotalPhys / (1024**3), 1)
            free_gb = round(stat.ullAvailPhys / (1024**3), 1)
            used_gb = round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3), 1)
            used_pct = stat.dwMemoryLoad
            stats["ram"] = {
                "total_gb": total_gb,
                "free_gb": free_gb,
                "used_gb": used_gb,
                "used_pct": used_pct
            }
    except Exception:
        pass

    # 3. GPU & Temperature via nvidia-smi with CREATE_NO_WINDOW (0x08000000)
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
            creationflags=0x08000000 # CREATE_NO_WINDOW
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 5:
                stats["gpu"] = {
                    "name": parts[0],
                    "temp_c": int(parts[1]),
                    "vram_total_mb": int(parts[2]),
                    "vram_used_mb": int(parts[3]),
                    "gpu_util_pct": int(parts[4])
                }
    except Exception:
        pass

    # 4. Disks usage via shutil (0ms, 0 subprocess)
    for drive in sorted({os.path.splitdrive(HOST_DIR)[0], os.path.splitdrive(SCRIPT_DIR)[0]}):
        try:
            u = shutil.disk_usage(drive + os.sep)
            stats["disks"][drive] = {
                "total_gb": round(u.total / (1024**3), 1),
                "free_gb": round(u.free / (1024**3), 1),
                "used_gb": round(u.used / (1024**3), 1)
            }
        except Exception:
            pass

    _cached_stats = stats
    _last_stats_time = now
    return stats

def search_wikipedia(query, max_results=3):
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "SHADER7-AI/1.0 (https://shader7.com)"})
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8"))
            results = []
            for item in data.get("query", {}).get("search", [])[:max_results]:
                snippet = html.unescape(re.sub(r'<[^>]+>', '', item.get("snippet", "")))
                title = item.get("title", "")
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append({"title": title, "url": page_url, "snippet": snippet})
            return results
    except Exception:
        return []

def search_news(query, max_results=4):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            xml_data = res.read().decode("utf-8", errors="ignore")
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")
            results = []
            for item in items[:max_results]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pubDate = item.findtext("pubDate", "")
                results.append({"title": title, "url": link, "snippet": f"News Report ({pubDate})"})
            return results
    except Exception:
        return []

def search_ddg_instant(query):
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8"))
            results = []
            if data.get("Abstract"):
                results.append({"title": data.get("Heading", "Overview"), "url": data.get("AbstractURL", ""), "snippet": data.get("Abstract")})
            for topic in data.get("RelatedTopics", [])[:3]:
                if "Text" in topic:
                    results.append({"title": topic.get("Text", "")[:60], "url": topic.get("FirstURL", ""), "snippet": topic.get("Text", "")})
            return results
    except Exception:
        return []

def perform_combined_search(query):
    sources = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_wiki = executor.submit(search_wikipedia, query)
        f_news = executor.submit(search_news, query)
        f_ddg = executor.submit(search_ddg_instant, query)

        for res in [f_wiki.result(), f_news.result(), f_ddg.result()]:
            if res:
                sources.extend(res)

    seen = set()
    deduped = []
    for s in sources:
        key = s.get("title", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(s)
            if len(deduped) >= 5:
                break
    return deduped


def install_dir():
    return os.path.join(os.path.expanduser("~"), "LocalAI")


def validate_model_store():
    """Fail before copying when a checkout has manifests but no model weights."""
    manifests = list(Path(MODEL_DIR, "manifests").rglob("*"))
    manifests = [path for path in manifests if path.is_file()]
    if not manifests:
        raise ValueError("No local models found. Run Build_AI_Pendrive.bat first.")
    for manifest in manifests:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        for layer in [document["config"], *document["layers"]]:
            digest = layer["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError(f"Invalid model manifest: {manifest.name}")
            blob = Path(MODEL_DIR, "blobs", digest.replace(":", "-"))
            if not blob.is_file() or blob.stat().st_size != layer["size"]:
                raise ValueError("Model files are missing or incomplete. Run Check_USB_Models.bat before installing.")

def create_shortcut(target):
    env = os.environ.copy()
    env["SHADER7_INSTALL_TARGET"] = target
    command = r"""$ErrorActionPreference='Stop'
$target=$env:SHADER7_INSTALL_TARGET
$desktop=[Environment]::GetFolderPath('Desktop')
$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'SHADER7 AI.lnk'))
$s.TargetPath=Join-Path $target 'Launch_SHADER7_AI.vbs'
$s.Arguments='cpu'
$s.WorkingDirectory=$target
$s.IconLocation=(Join-Path $target 'app.ico')+',0'
$s.Description='SHADER7 AI - Local AI'
$s.Save()
"""
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                   env=env, capture_output=True, check=True, creationflags=0x08000000)

def run_installation_worker():
    global install_cancel_flag
    if not INSTALL_LOCK.acquire(blocking=False):
        return
    install_cancel_flag = False
    try:
        install_state.update(status="installing", progress=1, step="Scanning", message="Checking files and free space...")
        target = install_dir()
        if within(SCRIPT_DIR, target):
            raise ValueError("This copy is already installed on the PC.")
        if not os.path.isfile(os.path.join(SCRIPT_DIR, "python", "python.exe")) or not os.path.isfile(OLLAMA_EXE):
            raise ValueError("Portable Python or Ollama is missing. Run Build_AI_Pendrive.bat first.")
        validate_model_store()
        if os.path.islink(target) or os.path.realpath(target) != os.path.abspath(target):
            raise ValueError("The install directory must not be a link or junction.")
        marker = os.path.join(target, "shader7-install.json")
        if os.path.isdir(target) and os.listdir(target) and not os.path.isfile(marker):
            raise ValueError("LocalAI already contains an older installation or other files. Preserve or rename it before installing this version.")
        if os.path.isfile(marker) and read_json(marker, {}).get("app") != APP_ID:
            raise ValueError("The destination belongs to another application.")
        copy_tasks = []
        for name in ("app", "models"):
            source = os.path.join(USB_ROOT, name)
            if not os.path.isdir(source):
                raise ValueError(f"Missing portable folder: {name}")
            for folder, dirs, files in os.walk(source):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for filename in files:
                    src = os.path.join(folder, filename)
                    if os.path.islink(src):
                        raise ValueError("Source contains a linked file. Build a fresh USB copy before installing.")
                    dst = os.path.join(target, os.path.relpath(src, USB_ROOT))
                    if not within(dst, target):
                        raise ValueError("A destination link points outside the installation.")
                    copy_tasks.append((src, dst, os.path.getsize(src)))
        for name in ("Launch_SHADER7_AI.vbs", "Launch_SHADER7_AI.bat", "Launch_GPU_Mode.bat", "Launch_CPU_Mode.bat", "Check_USB_Models.bat", "Install_To_PC.bat", "Uninstall_From_PC.bat", "Uninstall_SHADER7_AI.ps1", "README.md", "LICENSE", "app.ico"):
            source = os.path.join(USB_ROOT, name)
            copy_tasks.append((source, os.path.join(target, name), os.path.getsize(source)))
        total = sum(size for _, _, size in copy_tasks)
        if shutil.disk_usage(os.path.expanduser("~")).free < total + 512 * 1024**2:
            raise ValueError(f"Installation needs {total / 1024**3 + 0.5:.1f} GB free, including a safety margin.")
        os.makedirs(target, exist_ok=True)
        atomic_json(marker, {"app": APP_ID, "version": VERSION, "complete": False}, backup=False)
        completed = 0
        for source, dest, size in copy_tasks:
            if install_cancel_flag:
                raise InterruptedError()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            temporary = dest + ".shader7-part"
            try:
                with open(source, "rb") as src, open(temporary, "wb") as dst:
                    while True:
                        if install_cancel_flag:
                            raise InterruptedError()
                        chunk = src.read(4 * 1024**2)
                        if not chunk:
                            break
                        dst.write(chunk)
                        completed += len(chunk)
                        install_state.update(progress=max(1, int(completed * 98 / max(total, 1))),
                                             step="Copying " + os.path.basename(source),
                                             message=f"{completed / 1024**3:.2f} / {total / 1024**3:.2f} GB")
                    dst.flush()
                    os.fsync(dst.fileno())
                if os.path.getsize(temporary) != size:
                    raise OSError("Copied file has an unexpected size.")
                blob_name = os.path.basename(source)
                if re.fullmatch(r"sha256-[0-9a-f]{64}", blob_name):
                    install_state["step"] = "Verifying model checksum"
                    with open(temporary, "rb") as copied:
                        if hashlib.file_digest(copied, "sha256").hexdigest() != blob_name[7:]:
                            raise OSError("A model failed its checksum. Run Check_USB_Models.bat before installing.")
                os.replace(temporary, dest)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        if install_cancel_flag:
            raise InterruptedError()
        create_shortcut(target)
        atomic_json(marker, {"app": APP_ID, "version": VERSION, "complete": True}, backup=False)
        install_state.update(status="completed", progress=100, step="Done", message="Installed with its own models folder and Desktop shortcut.")
    except InterruptedError:
        install_state.update(status="cancelled", message="Copying stopped. Run Install again to finish, or use the uninstaller to remove this partial copy.")
    except Exception as exc:
        install_state.update(status="error", message=str(exc))
    finally:
        INSTALL_LOCK.release()

def launch_installed_app():
    launcher = os.path.join(install_dir(), "Launch_SHADER7_AI.vbs")
    if not os.path.isfile(launcher) or not read_json(os.path.join(install_dir(), "shader7-install.json"), {}).get("complete"):
        return {"success": False, "error": "The PC installation is incomplete. Run Install again."}
    subprocess.Popen(["wscript.exe", launcher, BACKEND_MODE], cwd=install_dir(), creationflags=0x08000000)
    return {"success": True}

def perform_host_uninstall():
    marker = os.path.join(install_dir(), "shader7-install.json")
    if not os.path.isfile(marker):
        return {"success": False, "error": "No installation owned by this version was found. Older shared models and chats have been preserved."}
    script = os.path.join(USB_ROOT, "Uninstall_SHADER7_AI.ps1")
    # An external helper can remove a running installed copy after the response is sent.
    subprocess.Popen(["powershell.exe", "-NoProfile", "-File", script, "-Confirmed"], creationflags=0x08000000)
    return {"success": True, "message": "Uninstaller started. Chat history and shared Ollama models are kept."}


class LocalAIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Do not put search queries or chat URLs in logs.

    def end_headers(self):
        self.send_header("X-Shader7-Engine", BACKEND_MODE)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if getattr(self, "is_preview", False):
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-modals")
        else:
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def allowed(self, api=True):
        host = self.headers.get("Host", "")
        valid_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in valid_hosts:
            self.send_json_response({"error": "Invalid local host."}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            self.send_json_response({"error": "Cross-site requests are blocked."}, 403)
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Shader7-Token", ""), SESSION_TOKEN):
            self.send_json_response({"error": "Open SHADER7 AI again to refresh this session."}, 403)
            return False
        return True

    def do_OPTIONS(self):
        self.send_json_response({"error": "Cross-site API access is disabled."}, 403)

    def do_HEAD(self):
        self.send_error(405)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not self.allowed(api=parsed.path.startswith("/api/") and parsed.path != "/api/health"):
            return
        try:
            if parsed.path == "/api/health":
                refresh_backend_health()
                self.send_json_response({"app": APP_ID, "version": VERSION, "instance": instance_id(),
                                         "ready": BACKEND_READY, "error": BACKEND_ERROR, "engine_mode": BACKEND_MODE,
                                         "gpu_only": BACKEND_MODE == "gpu", "gpu_model": GPU_MODEL if BACKEND_MODE == "gpu" else "", "loaded_model": GPU_MODEL, "context_length": engine_options(GPU_MODEL)["num_ctx"],
                                         "engine_runtime": BACKEND_RUNTIME, "starting": STARTUP_LOCK.locked(), "loading": load_status_snapshot()})
            elif parsed.path == "/api/system_stats":
                self.send_json_response(get_system_hardware_stats())
            elif parsed.path == "/api/settings":
                self.send_json_response(public_settings(load_host_settings()))
            elif parsed.path == "/api/host_chats":
                with chat_transaction():
                    chats = read_json(HOST_CHATS_FILE, [])
                    revision = chat_revision(chats)
                self.send_json_response({"chats": chats, "revision": revision, "host_dir": HOST_DIR})
            elif parsed.path == "/api/install_status":
                self.send_json_response(install_state)
            elif parsed.path == "/api/websearch":
                if not load_host_settings().get("web_search", False):
                    self.send_json_response({"sources": [], "error": "Web search is switched off."}, 403)
                    return
                query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()[:2000]
                sources = perform_combined_search(query) if query else []
                self.send_json_response({"sources": sources, "online": bool(sources)})
            elif parsed.path in ("/api/tags", "/api/ps"):
                refresh_backend_health()
                if not BACKEND_READY:
                    self.send_json_response({"models": [], "error": BACKEND_ERROR}, 503)
                    return
                self.proxy_local("GET", parsed.path)
            elif parsed.path.startswith("/preview/"):
                code = read_preview(parsed.path[len("/preview/"):])
                if code is None:
                    self.send_error(404, "Preview expired. Open Preview Website again.")
                    return
                self.is_preview = True
                self.send_bytes(code.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path in ("/", "/index.html"):
                body = Path(SCRIPT_DIR, "index.html").read_text(encoding="utf-8")
                body = body.replace("</head>", f'<meta name="shader7-session" content="{SESSION_TOKEN}"></head>')
                self.send_bytes(body.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path in ("/app.js", "/style.css", "/app.ico", "/logo.png"):
                super().do_GET()
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json_response({"error": str(exc)}, 500)

    def do_POST(self):
        if not self.allowed():
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer encoding is unsupported.")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 32 * 1024**2:
                self.send_json_response({"error": "Request is too large (maximum 32 MB)."}, 413)
                return
            if length and self.headers.get_content_type() != "application/json":
                self.send_json_response({"error": "Expected application/json."}, 415)
                return
            self.connection.settimeout(30)
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/settings":
                with DATA_LOCK:
                    current = load_host_settings()
                    for field in KEY_FIELDS:
                        if field in data:
                            if not isinstance(data[field], str) or len(data[field]) > 4096:
                                raise ValueError("Invalid API key.")
                            current[field] = data[field]
                    if "web_search" in data:
                        if not isinstance(data["web_search"], bool):
                            raise ValueError("Invalid web search preference.")
                        current["web_search"] = data["web_search"]
                    save_host_settings(current)
                self.send_json_response({"success": True, "settings": public_settings(current)})
            elif path == "/api/preview":
                self.send_json_response({"url": save_preview(data.get("html"))})
            elif path == "/api/host_chats":
                chats = data.get("chats")
                if not isinstance(chats, list) or any(not isinstance(c, dict) or not isinstance(c.get("messages"), list) for c in chats):
                    raise ValueError("Invalid conversation format.")
                with chat_transaction():
                    current = read_json(HOST_CHATS_FILE, [])
                    if data.get("revision") != chat_revision(current):
                        self.send_json_response({"error": "Another window changed the saved chats. Export this window's chats, then reload before saving again."}, 409)
                        return
                    atomic_json(HOST_CHATS_FILE, chats)
                    self.send_json_response({"success": True, "revision": chat_revision(chats)})
            elif path == "/api/install_to_host":
                if INSTALL_LOCK.locked():
                    self.send_json_response({"status": "already_installing"})
                else:
                    threading.Thread(target=run_installation_worker, daemon=True).start()
                    self.send_json_response({"status": "started"})
            elif path == "/api/cancel_install":
                global install_cancel_flag
                install_cancel_flag = True
                self.send_json_response({"status": "cancelling"})
            elif path == "/api/launch_installed":
                self.send_json_response(launch_installed_app())
            elif path == "/api/uninstall_from_host":
                if INSTALL_LOCK.locked():
                    raise ValueError("Wait for installation to finish first.")
                self.send_json_response(perform_host_uninstall())
            elif path == "/api/shutdown":
                if INSTALL_LOCK.locked():
                    raise ValueError("Finish or cancel installation before exiting.")
                self.send_json_response({"success": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif path == "/api/restart_engine":
                if not GPU_REQUEST_LOCK.acquire(blocking=False):
                    self.send_json_response({"error": "Wait for the current model load or response to finish before restarting."}, 409)
                    return
                try:
                    if not start_backend(restart=True):
                        self.send_json_response({"error": f"The {ENGINE_LABEL} engine is already starting. Follow the loading countdown."}, 409)
                    else:
                        self.send_json_response({"success": True})
                finally:
                    GPU_REQUEST_LOCK.release()
            elif path == "/api/chat":
                refresh_backend_health()
                if not BACKEND_READY:
                    self.send_json_response({"error": BACKEND_ERROR}, 503)
                    return
                if not GPU_REQUEST_LOCK.acquire(blocking=False):
                    self.send_json_response({"error": f"The {ENGINE_LABEL} is busy. Wait for the current reply to finish."}, 409)
                    return
                try:
                    data = gpu_chat_payload(data)
                    ensure_gpu_model(data["model"])
                    self.proxy_local("POST", path, data)
                except GPUOnlyError as exc:
                    self.send_json_response({"error": str(exc)}, 503)
                finally:
                    GPU_REQUEST_LOCK.release()
            elif path in ("/api/nvidia/chat", "/api/openrouter/chat"):
                self.proxy_cloud(path, data)
            else:
                self.send_error(404)
        except (ValueError, UnicodeError) as exc:
            self.send_json_response({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception as exc:
            self.send_json_response({"error": str(exc)}, 500)

    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_response(self, data, status=200):
        self.send_bytes(json.dumps(data).encode("utf-8"), "application/json; charset=utf-8", status)

    def stream_request(self, request, opener, stream=True):
        started = False
        try:
            with opener.open(request, timeout=300) as response:
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.end_headers()
                started = True
                while True:
                    chunk = response.readline() if stream else response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    if stream and stream_record_done(chunk):
                        break
        except (BrokenPipeError, ConnectionResetError):
            pass
        except urllib.error.HTTPError as exc:
            if not started:
                self.send_bytes(exc.read(), "application/json", exc.code)
        except Exception as exc:
            if not started:
                self.send_json_response({"error": "AI engine request failed: " + str(exc)}, 502)

    def proxy_local(self, method, path, data=None):
        payload = None
        if data is not None:
            data = dict(data)
            data.setdefault("keep_alive", GPU_KEEP_ALIVE)
            data.setdefault("options", dict(GPU_OPTIONS))
            payload = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(OLLAMA_TARGET + path, data=payload,
                                         headers={"Content-Type": "application/json"}, method=method)
        self.stream_request(request, LOCAL_HTTP, stream=bool(data and data.get("stream", True)))

    def proxy_cloud(self, path, data):
        settings = load_host_settings()
        nvidia = path == "/api/nvidia/chat"
        key = settings["nvidia_api_key" if nvidia else "openrouter_api_key"]
        if not key:
            self.send_json_response({"error": "Configure this provider's API key in settings first."}, 400)
            return
        url = "https://integrate.api.nvidia.com/v1/chat/completions" if nvidia else "https://openrouter.ai/api/v1/chat/completions"
        payload = {"model": data.get("model"), "messages": data.get("messages", []), "stream": True, "max_tokens": 4096}
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}, method="POST")
        self.stream_request(request, urllib.request.build_opener())

def launch_desktop_app_window():
    """Launches SHADER7 AI in dedicated Microsoft Edge App Mode (Zero SmartScreen blocks, clean app window)."""
    url = f"http://127.0.0.1:{PORT}"
    
    app_runners = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
    ]

    for exe in app_runners:
        if os.path.exists(exe):
            try:
                subprocess.Popen([
                    exe,
                    f"--app={url}",
                    f"--user-data-dir={HOST_APP_PROFILE}",
                    "--window-size=1280,820",
                    "--app-auto-launched",
                    "--hide-scrollbars=false"
                ])
                return
            except Exception as e:
                print(f"App runner launch error: {e}")

    try:
        webbrowser.open(url)
    except Exception:
        pass


def stream_record_done(chunk):
    record = chunk.strip()
    if record.startswith(b"data:"):
        record = record[5:].strip()
    if record == b"[DONE]":
        return True
    try:
        item = json.loads(record)
        if not isinstance(item, dict):
            return False
        choices = item.get("choices") or []
        return bool(item.get("done") or item.get("error") or
                    (choices and isinstance(choices[0], dict) and choices[0].get("finish_reason")))
    except (ValueError, TypeError, IndexError):
        return False


class GPUOnlyError(RuntimeError):
    pass


def gpu_chat_payload(data):
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Choose a local model first.")
    options = data.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("Invalid model options.")
    # Memory and offload settings are enforced even if a client requests CPU.
    # Sampling options remain available, but runner options cannot change after
    # the model's GPU placement has been checked.
    runner_options = {"num_ctx", "num_batch", "num_gpu", "main_gpu", "low_vram", "f16_kv",
                      "logits_all", "vocab_only", "use_mmap", "use_mlock", "num_thread"}
    options = {key: value for key, value in options.items() if key not in runner_options}
    data = designer_payload({**data, "model": model.strip()})
    options = {key: value for key, value in data.get("options", {}).items() if key not in runner_options}
    options.update(engine_options(model.strip()))
    return {**data, "model": model.strip(), "options": options, "keep_alive": GPU_KEEP_ALIVE}


def engine_json(path, data=None, timeout=180):
    if STOP_EVENT.is_set():
        raise GPUOnlyError(f"The {ENGINE_LABEL} engine is shutting down.")
    request = urllib.request.Request(OLLAMA_TARGET + path,
                                    data=json.dumps(data).encode("utf-8") if data is not None else None,
                                    headers={"Content-Type": "application/json"})
    with LOCAL_HTTP.open(request, timeout=timeout) as response:
        result = json.load(response)
    if result.get("error"):
        raise GPUOnlyError(str(result["error"]))
    return result


def load_timing_key(phase, model=""):
    identity = f"{os.path.normcase(os.path.abspath(MODEL_DIR))}|{BACKEND_RUNTIME}|{BACKEND_MODE}|{engine_options(model)['num_ctx']}|{phase}|{model}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def read_load_timings():
    try:
        data = read_json(os.path.join(HOST_DIR, "model-load-times.json"), {})
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # A damaged timing cache must never prevent GPU startup.


def load_time_estimate(phase, model=""):
    values = read_load_timings().get(load_timing_key(phase, model), [])
    if isinstance(values, list):
        values = [float(n) for n in values if isinstance(n, (int, float)) and math.isfinite(n) and 0.5 <= n <= 600][-5:]
        if values:
            # Recent observations matter most because the OS may cache USB reads.
            average = sum(n * (i + 1) for i, n in enumerate(values)) / sum(range(1, len(values) + 1))
            return max(1.0, average), "measured"
    if phase == "engine_starting":
        return (35.0 if BACKEND_RUNTIME == "pc" else 90.0), "initial"
    size = MODEL_SIZES.get(model, 0)
    return (max(5.0, size / (24 * 1024**2) + 5) if size else 60.0), "initial"


def begin_load_status(phase, model=""):
    estimate, source = load_time_estimate(phase, model)
    with LOAD_STATE_LOCK:
        LOAD_STATE.update(phase=phase, model=model, started=time.monotonic(),
                          event_id=LOAD_STATE["event_id"] + 1, estimate_seconds=estimate,
                          estimate_source=source, elapsed_seconds=0, error="")


def finish_load_status(error="", record=True):
    with LOAD_STATE_LOCK:
        phase, model = LOAD_STATE["phase"], LOAD_STATE["model"]
        elapsed = max(0.0, time.monotonic() - LOAD_STATE["started"]) if LOAD_STATE["started"] is not None else LOAD_STATE["elapsed_seconds"]
        LOAD_STATE.update(phase="error" if error else "ready", started=None,
                          elapsed_seconds=elapsed, error=error)
    # Loaded-model keep-alive refreshes take milliseconds; do not let them skew
    # estimates for an actual load. Failed/cancelled loads are not timing samples.
    if not error and record and elapsed >= 0.5 and phase in ("engine_starting", "model_loading"):
        try:
            with DATA_LOCK:
                timings = read_load_timings()
                key = load_timing_key(phase, model)
                previous = timings.get(key, [])
                values = previous if isinstance(previous, list) else []
                timings[key] = (values + [round(elapsed, 3)])[-5:]
                atomic_json(os.path.join(HOST_DIR, "model-load-times.json"), timings, backup=False)
        except (OSError, ValueError):
            pass  # Timing history is optional; inference remains available.


def load_status_snapshot():
    with LOAD_STATE_LOCK:
        status = dict(LOAD_STATE)
    started = status.pop("started")
    active = status["phase"] in ("engine_starting", "model_loading")
    elapsed = max(0.0, time.monotonic() - started) if active and started is not None else status["elapsed_seconds"]
    estimate = status["estimate_seconds"]
    overdue = bool(active and estimate is not None and elapsed >= estimate)
    status.update(engine_mode=BACKEND_MODE, active=active, elapsed_seconds=round(elapsed, 1), overdue=overdue,
                  remaining_seconds=max(0.1, round(estimate - elapsed, 1)) if active and estimate is not None and not overdue else None)
    return status


def ensure_gpu_model(model):
    """Load without a prompt and verify the mode explicitly selected at launch."""
    global GPU_MODEL
    begin_load_status("model_loading", model)
    try:
        # Empty generation loads/refreshes the runner without generating text.
        engine_json("/api/generate", {"model": model, "stream": False,
                    "keep_alive": GPU_KEEP_ALIVE, "options": engine_options(model)})
        loaded = engine_json("/api/ps", timeout=5).get("models", [])
        names = {model, model + ":latest"} if ":" not in model.rsplit("/", 1)[-1] else {model}
        entry = next((item for item in loaded if item.get("name") in names or item.get("model") in names), None)
        size = int(entry.get("size", 0)) if entry else 0
        vram = int(entry.get("size_vram", 0)) if entry else 0
        if size <= 0 or (vram != 0 if BACKEND_MODE == "cpu" else vram < size):
            try:
                engine_json("/api/generate", {"model": model, "keep_alive": 0, "stream": False}, timeout=15)
            except Exception:
                pass
            GPU_MODEL = ""
            if BACKEND_MODE == "cpu":
                raise GPUOnlyError("CPU mode could not verify CPU-only placement. The model was unloaded.")
            raise GPUOnlyError("GPU-only mode: this model did not fit entirely in GPU memory. "
                               "Close other GPU apps or choose a smaller model. CPU fallback is disabled.")
        GPU_MODEL = entry.get("name", model)
        finish_load_status(record=not STOP_EVENT.is_set())
        return entry
    except GPUOnlyError as exc:
        finish_load_status(error=str(exc))
        raise
    except Exception as exc:
        GPU_MODEL = ""
        error = ("CPU mode could not load this model. Check available RAM and engine-cpu.log." if BACKEND_MODE == "cpu" else
                 "GPU-only mode could not load this model. Close other GPU apps or choose a smaller model. Check engine.log for details. CPU fallback is disabled.")
        finish_load_status(error=error)
        raise GPUOnlyError(error) from exc


def select_gpu_runtime():
    if BACKEND_MODE == "cpu":
        if not os.path.isfile(OLLAMA_EXE):
            raise GPUOnlyError("The bundled CPU runtime is missing. Restore app/ollama.")
        return OLLAMA_EXE
    # Ollama chooses its supported CUDA library; the model-load check rejects CPU offload.
    if os.path.isfile(OLLAMA_EXE):
        return OLLAMA_EXE
    raise GPUOnlyError("The bundled Ollama runtime is missing. Rerun the USB builder.")


def stop_backend():
    global OLLAMA_PROCESS, BACKEND_READY, GPU_MODEL
    process = OLLAMA_PROCESS
    if process is not None and process.poll() is None:
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, creationflags=0x08000000)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    OLLAMA_PROCESS = None
    BACKEND_READY = False
    GPU_MODEL = ""

def refresh_backend_health():
    global BACKEND_READY, BACKEND_ERROR, GPU_MODEL
    with BACKEND_LOCK:
        if BACKEND_READY and (OLLAMA_PROCESS is None or OLLAMA_PROCESS.poll() is not None):
            BACKEND_READY = False
            GPU_MODEL = ""
            BACKEND_ERROR = f"The {ENGINE_LABEL} engine stopped. Use Restart {ENGINE_LABEL} engine to reconnect."
            finish_load_status(error=BACKEND_ERROR)


def start_backend(restart=False):
    """Reserve startup before starting the thread so duplicate retries cannot race."""
    global BACKEND_READY, BACKEND_ERROR
    if not STARTUP_LOCK.acquire(blocking=False):
        return False
    try:
        with BACKEND_LOCK:
            if STOP_EVENT.is_set():
                STARTUP_LOCK.release()
                return False
            if restart:
                stop_backend()
            BACKEND_READY = False
            BACKEND_ERROR = "Starting CPU engine..." if BACKEND_MODE == "cpu" else "Starting NVIDIA GPU engine..."
        def worker():
            try:
                ensure_ollama_running()
            finally:
                STARTUP_LOCK.release()
        threading.Thread(target=worker, daemon=True).start()
        return True
    except Exception:
        STARTUP_LOCK.release()
        raise


def ensure_ollama_running():
    global OLLAMA_PROCESS, OLLAMA_TARGET, BACKEND_READY, BACKEND_ERROR, BACKEND_RUNTIME
    try:
        executable = select_gpu_runtime()
        BACKEND_RUNTIME = "pc" if os.path.normcase(executable) != os.path.normcase(OLLAMA_EXE) else "bundled"
        begin_load_status("engine_starting")
        if not os.path.isdir(os.path.join(MODEL_DIR, "manifests")):
            raise FileNotFoundError("The models folder was not found beside the app folder.")
        env = os.environ.copy()
        env.update(OLLAMA_MODELS=MODEL_DIR, OLLAMA_KEEP_ALIVE=GPU_KEEP_ALIVE,
                   OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_CONTEXT_LENGTH=str(GPU_CONTEXT),
                   OLLAMA_VULKAN="false", OLLAMA_KV_CACHE_TYPE="f16",
                   OLLAMA_FLASH_ATTENTION="false", OLLAMA_LOAD_TIMEOUT="2m",
                   OLLAMA_NO_CLOUD="1", OLLAMA_NOPRUNE="1", OLLAMA_DEBUG="0", OLLAMA_DEBUG_LOG_REQUESTS="false")
        for key in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "GPU_DEVICE_ORDINAL",
                    "GGML_VK_VISIBLE_DEVICES", "OLLAMA_LIBRARY_PATH", "OLLAMA_LLM_LIBRARY"):
            env.pop(key, None)
        if BACKEND_MODE == "cpu":
            env.update(OLLAMA_LLM_LIBRARY="cpu", CUDA_VISIBLE_DEVICES="-1", HIP_VISIBLE_DEVICES="-1",
                       ROCR_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1", OLLAMA_VULKAN="false")
        else:
            env.update(HIP_VISIBLE_DEVICES="-1", ROCR_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1")
        log_path = os.path.join(HOST_DIR, "engine-cpu.log" if BACKEND_MODE == "cpu" else "engine.log")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            backend_port = sock.getsockname()[1]
        OLLAMA_TARGET = f"http://127.0.0.1:{backend_port}"
        env["OLLAMA_HOST"] = OLLAMA_TARGET
        BACKEND_ERROR = "Starting CPU engine..." if BACKEND_MODE == "cpu" else "Starting NVIDIA GPU engine..."
        with open(log_path, "w", encoding="utf-8") as log:
            with BACKEND_LOCK:
                if STOP_EVENT.is_set():
                    return
                OLLAMA_PROCESS = subprocess.Popen([executable, "serve"], cwd=os.path.dirname(executable), env=env,
                                                  stdout=log, stderr=log, creationflags=0x08000000)
        deadline = time.monotonic() + GPU_STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if STOP_EVENT.is_set():
                return
            if OLLAMA_PROCESS is None or OLLAMA_PROCESS.poll() is not None:
                raise GPUOnlyError("The CPU engine exited. Check engine-cpu.log." if BACKEND_MODE == "cpu" else
                                   "The GPU engine exited. Check engine.log. CPU fallback is disabled.")
            try:
                tags = engine_json("/api/tags", timeout=1)
                break
            except (urllib.error.URLError, TimeoutError):
                STOP_EVENT.wait(0.25)
        else:
            raise GPUOnlyError("CPU startup timed out. Check engine-cpu.log." if BACKEND_MODE == "cpu" else
                               "GPU startup timed out. Run the engine from the PC drive and check engine.log. CPU fallback is disabled.")
        finish_load_status(record=not STOP_EVENT.is_set())
        MODEL_SIZES.update({item["name"]: item.get("size", 0) for item in tags.get("models", []) if item.get("name")})
        models = [item["name"] for item in tags.get("models", []) if item.get("name")]
        if not models:
            raise GPUOnlyError("No local models were found in the models folder.")
        initial_model = "qwen2.5:3b" if "qwen2.5:3b" in models else models[0]
        BACKEND_ERROR = "Loading " + initial_model + (" into system RAM..." if BACKEND_MODE == "cpu" else " into GPU memory...")
        with GPU_REQUEST_LOCK:
            ensure_gpu_model(initial_model)
        with BACKEND_LOCK:
            if STOP_EVENT.is_set():
                return
            atomic_json(os.path.join(HOST_DIR, "engine-mode-cpu.json" if BACKEND_MODE == "cpu" else "engine-mode.json"),
                        {"mode": BACKEND_MODE, "library": "cpu" if BACKEND_MODE == "cpu" else "cuda", "gpu_only": BACKEND_MODE == "gpu"}, backup=False)
            BACKEND_READY, BACKEND_ERROR = True, ""
    except Exception as exc:
        BACKEND_ERROR = str(exc)
        finish_load_status(error=BACKEND_ERROR)
        stop_backend()

class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

def main():
    global PORT
    init_host_workspace()
    if "--install" in sys.argv:
        worker = threading.Thread(target=run_installation_worker)
        worker.start()
        while worker.is_alive():
            print(f"{install_state['progress']}% {install_state['message']}", flush=True)
            worker.join(2)
        print(install_state["message"], flush=True)
        return 0 if install_state["status"] == "completed" else 1
    identity = instance_id()
    httpd = None
    for candidate in range(8080, 8100):
        PORT = candidate
        try:
            httpd = LocalServer(("127.0.0.1", PORT), LocalAIHandler)
            break
        except OSError:
            try:
                with LOCAL_HTTP.open(f"http://127.0.0.1:{PORT}/api/health", timeout=0.4) as response:
                    active = json.load(response)
                    if active.get("app") == APP_ID and active.get("instance") == identity and active.get("version") == VERSION:
                        if "--no-browser" not in sys.argv:
                            launch_desktop_app_window()
                        return 0
            except Exception:
                pass
    if httpd is None:
        raise OSError("No free app port between 8080 and 8099. Close an unused local server and retry.")
    atexit.register(stop_backend)
    start_backend()
    print(f"SHADER7 AI {VERSION}: http://127.0.0.1:{PORT}", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.3, launch_desktop_app_window).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        with BACKEND_LOCK:
            STOP_EVENT.set()
            stop_backend()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        if "--no-browser" not in sys.argv and "--install" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, str(exc), "SHADER7 AI - Startup error", 0x10)
        raise
