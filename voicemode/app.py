"""Wires everything together.

Threads:
  main       overlay window (Tk) — or just waits in --no-overlay / --text mode
  hook       pynput low-level keyboard hook (push-to-talk key)
  listener   mic + speech-to-text, emits partial/final transcripts
  worker     controller + all actions (Playwright must stay on one thread)
  laya-load  loads Laya in the background at start
"""
from __future__ import annotations

import argparse
import collections
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import config


class Worker:
    """Single thread that runs submitted calls in order. Partials coalesce: a queued partial
    that has not started yet is replaced by the newer one."""

    def __init__(self):
        self._q: collections.deque = collections.deque()
        self._cv = threading.Condition()
        self._t = threading.Thread(target=self._run, name="worker", daemon=True)
        self._t.start()

    def submit(self, fn, *args, tag=None, drop=None):
        """`drop`: first remove queued (not yet started) calls carrying this tag."""
        done = threading.Event()
        with self._cv:
            if drop is not None:
                self._q = collections.deque(x for x in self._q if x[2] != drop)
            self._q.append((fn, args, tag, done))
            self._cv.notify()
        return done

    def call(self, fn, *args):
        """Run on the worker and wait for it."""
        box = {}

        def wrap():
            box["r"] = fn(*args)
        self.submit(wrap).wait()
        return box.get("r")

    def _run(self):
        log = logging.getLogger("voicemode")
        while True:
            with self._cv:
                while not self._q:
                    self._cv.wait()
                fn, args, tag, done = self._q.popleft()
            try:
                fn(*args)
            except Exception:
                log.exception("worker task failed")
            finally:
                done.set()


def setup_logging(debug: bool):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = RotatingFileHandler(config.LOG_DIR / "voicemode.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    root.addHandler(fh)
    if debug:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        root.addHandler(ch)
    for noisy in ("urllib3", "httpx", "huggingface_hub", "transformers", "comtypes", "PIL", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def build(settings, dry_run=False, with_laya=True):
    from .actions.browser import Browser
    from .actions.system import make_system
    from .brain import Brain
    from .controller import Controller
    from .executor import Executor
    from .overlay import Feedback, Overlay
    from .setup_models import laya_ready

    system = make_system(dry_run=dry_run)
    system.warm()
    brain = None
    if with_laya and settings.use_laya and laya_ready(Path(settings.laya_dir)):
        brain = Brain(settings.laya_dir, config.LAYA_SUBFOLDER, settings.laya_min_confidence)
        brain.load_async()
    browser = Browser(settings, system, brain)
    executor = Executor(settings, system, browser, brain)
    overlay = Overlay() if settings.overlay else None
    feedback = Feedback(overlay, beeps=settings.beeps)
    ulog = config.LOG_DIR / "utterances.jsonl" if settings.log_utterances else None
    controller = Controller(executor, brain, feedback, settings, ulog)
    return dict(system=system, brain=brain, browser=browser, executor=executor, overlay=overlay,
                feedback=feedback, controller=controller)


def text_mode(parts, worker):
    ctl = parts["controller"]
    print("Text mode: command likho aur Enter dabao (exit = quit).\n")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line.lower() in ("exit", "quit"):
            break
        if not line:
            continue
        worker.call(ctl.begin)
        worker.call(ctl.final, line)


def mic_test(settings) -> int:
    import time

    from .audio import Recorder
    from .parser import parse
    from .stt import SpeechToText, voiced_seconds
    print("Speech model load ho raha hai…", flush=True)
    stt = SpeechToText(settings.stt_model_dir, settings.stt_threads, settings.stt_quantize)
    rec = Recorder(settings.extra.get("mic_device"))
    print("\nEnter dabao, phir 5 second tak koi command bolo (English / Hindi / Hinglish). "
          "Ctrl+C = exit.\n")
    while True:
        try:
            input("[Enter] ")
        except (EOFError, KeyboardInterrupt):
            return 0
        rec.start()
        print("  🎤 bolo…", flush=True)
        time.sleep(5)
        audio = rec.stop()
        v = voiced_seconds(audio)
        t = time.time()
        text = stt.transcribe(audio) if v >= settings.min_speech_seconds else ""
        dt = time.time() - t
        print(f"  suna ({v:.1f}s speech, {dt:.2f}s me): “{text}”")
        for c in parse(text) if text else []:
            print(f"    -> {c.describe()}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="voicemode", description="Offline voice control for Windows")
    ap.add_argument("--check", action="store_true", help="verify install and models, then exit")
    ap.add_argument("--quick-check", action="store_true", help="like --check without loading models")
    ap.add_argument("--text", action="store_true", help="type commands instead of speaking")
    ap.add_argument("--dry-run", action="store_true", help="log system actions instead of doing them")
    ap.add_argument("--no-laya", action="store_true", help="rules only (less RAM, faster start)")
    ap.add_argument("--mic-test", action="store_true",
                    help="record a few seconds, show what was heard and how it parses (runs nothing)")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if sys.platform == "win32":
        try:                                   # crisp overlay text and real pixel coordinates
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    config.force_offline()
    if a.check or a.quick_check:
        from .checks import run
        return run(deep=a.check)
    settings = config.load()
    setup_logging(a.debug)
    log = logging.getLogger("voicemode")
    if a.mic_test:
        return mic_test(settings)
    if a.text:
        settings.overlay = False
    parts = build(settings, dry_run=a.dry_run, with_laya=not a.no_laya)
    worker = Worker()
    stop = threading.Event()

    if a.text:
        try:
            text_mode(parts, worker)
        finally:
            worker.call(parts["browser"].shutdown)
        return 0

    from .audio import Listener, Recorder
    from .hotkey import PushToTalk
    from .setup_models import stt_ready
    from .stt import SpeechToText
    if not stt_ready(Path(settings.stt_model_dir)):
        print("Speech model nahi mila. Pehle setup.bat chalao.")
        return 1
    print("Speech model load ho raha hai…", flush=True)
    stt = SpeechToText(settings.stt_model_dir, settings.stt_threads, settings.stt_quantize)
    ctl, fb = parts["controller"], parts["feedback"]
    listener = Listener(
        stt, Recorder(settings.extra.get("mic_device")), settings,
        on_begin=lambda: worker.submit(ctl.begin),
        on_partial=lambda t: worker.submit(ctl.partial, t, tag="partial", drop="partial"),
        on_final=lambda t: worker.submit(ctl.final, t, drop="partial"),
        on_error=lambda m: fb.action(m, ok=False),
        beep=fb.beep,
    )
    listener.start()
    hk = PushToTalk(settings.hotkey, listener.press, listener.release)
    try:
        hk.start()
    except Exception as e:
        print(f"Hotkey start nahi hua: {e}")
        return 1
    key = settings.hotkey.replace("_", " ").title()
    brain = parts["brain"]
    print(f"\n✅ Voice Mode ready.  {key} dabake rakho aur bolo — chhodte hi final command chalega.")
    print(f"   Laya: {'load ho raha hai (background)' if brain else 'off (rules only)'}   ·   band karne ke liye: Ctrl+C\n",
          flush=True)
    log.info("ready")
    try:
        ran = False
        if parts["overlay"] is not None:
            try:
                parts["overlay"].run(stop)
                ran = True
            except KeyboardInterrupt:
                raise
            except Exception as e:           # e.g. Python without tkinter
                log.warning("overlay unavailable (%s); console only", e)
                parts["feedback"].overlay = None
        if not ran:
            while not stop.wait(0.5):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        hk.stop()
        worker.call(parts["browser"].shutdown)
    return 0
