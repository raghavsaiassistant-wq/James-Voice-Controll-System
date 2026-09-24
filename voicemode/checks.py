"""`python -m voicemode --check`: verify everything voice mode needs, offline."""
from __future__ import annotations

import importlib
import platform
import sys
import time
from pathlib import Path

from . import config
from .setup_models import laya_ready, stt_ready

GREEN, RED, YELLOW, END = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def _line(ok, name, detail=""):
    tag = f"{GREEN}[OK]{END}" if ok is True else f"{YELLOW}[!] {END}" if ok is None else f"{RED}[X] {END}"
    print(f"  {tag} {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def run(deep: bool = True) -> int:
    if sys.platform == "win32":
        import os
        os.system("")          # enable ANSI colours in the Windows console
    s = config.load()
    config.force_offline()
    bad = 0
    print("\nVoice Mode self-check\n")
    v = sys.version_info
    bad += not _line((3, 10) <= v[:2] <= (3, 13), "Python", f"{platform.python_version()} ({platform.architecture()[0]})")
    mods = ["numpy", "torch", "transformers", "huggingface_hub", "sounddevice", "pynput", "rapidfuzz", "playwright"]
    if s.use_laya:
        mods.append("laya")
    if sys.platform == "win32":
        mods += ["comtypes", "pycaw"]
    for m in mods:
        try:
            mod = importlib.import_module(m)
            _line(True, f"package {m}", getattr(mod, "__version__", ""))
        except Exception as e:
            bad += 1
            _line(False, f"package {m}", (str(e).splitlines() or [""])[0][:120])
    bad += not _line(stt_ready(Path(s.stt_model_dir)), "speech model", s.stt_model_dir)
    if s.use_laya:
        bad += not _line(laya_ready(Path(s.laya_dir)), "Laya model", s.laya_dir)
    else:
        _line(None, "Laya model", "use_laya=false in settings.json (rules only)")
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        _line(True, "microphone", dev["name"])
    except Exception as e:
        _line(None, "microphone", f"none found ({str(e)[:80]}) — mic lagao, phir chalao")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            if s.browser_channel:
                _line(True, "browser", f"channel {s.browser_channel}")
            else:
                exe = Path(pw.chromium.executable_path)
                bad += not _line(exe.exists(), "browser (Chromium)", str(exe) if exe.exists() else
                                 "missing — run: .venv\\Scripts\\python -m playwright install chromium")
    except Exception as e:
        bad += 1
        _line(False, "browser", str(e)[:120])
    if sys.platform == "win32":
        try:
            from .hotkey import KEYS
            _line(s.hotkey in KEYS, "push-to-talk key", s.hotkey.replace("_", " ").title())
        except Exception as e:
            _line(False, "push-to-talk key", str(e))
    else:
        _line(None, "push-to-talk key", "Windows only (use --text here)")
    if deep and stt_ready(Path(s.stt_model_dir)):
        try:
            import numpy as np
            from .stt import SpeechToText
            t = time.time()
            stt = SpeechToText(s.stt_model_dir, s.stt_threads, s.stt_quantize)
            t1 = time.time()
            stt.transcribe(np.zeros(16000 * 3, dtype=np.float32))
            _line(True, "speech model loads offline", f"load {t1 - t:.1f}s, 3s audio in {time.time() - t1:.2f}s")
        except Exception as e:
            bad += 1
            _line(False, "speech model loads offline", str(e)[:160])
    if deep and s.use_laya and laya_ready(Path(s.laya_dir)):
        try:
            from .brain import Brain
            t = time.time()
            b = Brain(s.laya_dir)
            b._load()
            if b.agent is None:
                raise RuntimeError(b.error)
            t1 = time.time()
            cmd = b.classify("please make the sound louder")
            _line(True, "Laya loads offline", f"load {t1 - t:.1f}s, decision {time.time() - t1:.2f}s"
                  + (f" ({cmd.describe()})" if cmd else ""))
        except Exception as e:
            bad += 1
            _line(False, "Laya loads offline", str(e)[:160])
    print()
    if bad:
        print(f"{RED}{bad} problem(s). setup.bat dobara chalao.{END}\n")
    else:
        print(f"{GREEN}Sab ready hai. run.bat se Voice Mode start karo.{END}\n")
    return 1 if bad else 0
