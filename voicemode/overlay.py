"""Feedback: a small always-on-top bar at the bottom of the screen, console lines and beeps.

The bar never takes focus and lets clicks through (WS_EX_NOACTIVATE | WS_EX_TRANSPARENT), so
"type hello" still types into the app you were using.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time

log = logging.getLogger("voicemode")

COLORS = {"listening": "#ef4444", "working": "#f59e0b", "confirm": "#a855f7", "done": "#22c55e",
          "error": "#ef4444", "idle": "#6b7280", "loading": "#3b82f6"}
LABELS = {"listening": "Sun raha hoon…", "working": "Kar raha hoon…", "confirm": "Confirm karo",
          "done": "Ho gaya", "error": "Nahi hua", "idle": "Ready", "loading": "Load ho raha hai…"}


def beep(kind: str):
    if sys.platform != "win32":
        return
    import winsound
    tone = {"start": [(880, 60)], "stop": [(520, 60)], "error": [(260, 160)], "confirm": [(660, 80), (880, 80)]}
    threading.Thread(target=lambda: [winsound.Beep(f, d) for f, d in tone.get(kind, [])], daemon=True).start()


class Feedback:
    """Implements the controller's feedback interface; thread-safe."""

    def __init__(self, overlay: "Overlay | None" = None, beeps: bool = True, console: bool = True):
        self.overlay = overlay
        self.beeps = beeps
        self.console = console

    def _ov(self, *msg):
        if self.overlay is not None:
            self.overlay.q.put(msg)

    def status(self, state: str, text: str = ""):
        self._ov("status", state, text)
        if state == "confirm" and self.beeps:
            beep("confirm")
        if self.console and text and state in ("confirm", "loading"):
            print(f"  ? {text}", flush=True)

    def transcript(self, text: str, final: bool):
        self._ov("transcript", text, final)
        if self.console and final and text:
            print(f"🎤 {text}", flush=True)

    def action(self, message: str, ok: bool = True):
        self._ov("action", message, ok)
        if self.console:
            print(f"  {'✓' if ok else '✗'} {message}", flush=True)
        if not ok and self.beeps:
            beep("error")

    def beep(self, kind: str):
        if self.beeps:
            beep(kind)


class Overlay:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.root = None
        self._hide_at = 0.0

    def run(self, stop: threading.Event):
        """Blocks; call from the main thread."""
        import tkinter as tk
        root = tk.Tk()
        self.root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        bg = "#111827"
        root.configure(bg=bg)
        w, h = 620, 92
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 70}")
        top = tk.Frame(root, bg=bg)
        top.pack(fill="x", padx=14, pady=(10, 0))
        dot = tk.Canvas(top, width=14, height=14, bg=bg, highlightthickness=0)
        dot.pack(side="left")
        oval = dot.create_oval(2, 2, 13, 13, fill=COLORS["idle"], outline="")
        status = tk.Label(top, text="Voice Mode", fg="#e5e7eb", bg=bg, font=("Segoe UI", 11, "bold"))
        status.pack(side="left", padx=8)
        said = tk.Label(root, text="", fg="#f9fafb", bg=bg, font=("Segoe UI", 13), anchor="w",
                        wraplength=w - 28, justify="left")
        said.pack(fill="x", padx=14)
        act = tk.Label(root, text="", fg="#9ca3af", bg=bg, font=("Segoe UI", 10), anchor="w")
        act.pack(fill="x", padx=14)
        root.update_idletasks()
        self._no_activate(root)
        visible = {"on": False}

        def show():
            if not visible["on"]:
                root.attributes("-alpha", 0.94)
                visible["on"] = True

        def hide():
            root.attributes("-alpha", 0.0)
            visible["on"] = False

        hide()

        def poll():
            if stop.is_set():
                root.destroy()
                return
            try:
                while True:
                    kind, *a = self.q.get_nowait()
                    show()
                    if kind == "status":
                        state, text = a
                        dot.itemconfig(oval, fill=COLORS.get(state, COLORS["idle"]))
                        status.config(text=LABELS.get(state, state))
                        if state == "listening":
                            said.config(text="")
                            act.config(text="")
                        if state == "confirm":
                            act.config(text=text, fg="#d8b4fe")
                        self._hide_at = time.time() + (25 if state == "confirm" else 60 if state in (
                            "listening", "working", "loading") else 4)
                    elif kind == "transcript":
                        text, final = a
                        said.config(text=f"“{text}”" if text else "")
                        if final:
                            self._hide_at = time.time() + 4
                    elif kind == "action":
                        msg, ok = a
                        act.config(text=("✓ " if ok else "✗ ") + msg, fg="#86efac" if ok else "#fca5a5")
                        dot.itemconfig(oval, fill=COLORS["done" if ok else "error"])
                        status.config(text=LABELS["done" if ok else "error"])
                        self._hide_at = time.time() + (6 if "Number bolo" in msg else 4)
            except queue.Empty:
                pass
            if visible["on"] and time.time() > self._hide_at:
                hide()
            root.after(50, poll)

        root.after(50, poll)
        root.mainloop()

    @staticmethod
    def _no_activate(root):
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x08000000 | 0x80 | 0x20 | 0x80000 | 0x8   # NOACTIVATE|TOOLWINDOW|TRANSPARENT|LAYERED|TOPMOST
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
