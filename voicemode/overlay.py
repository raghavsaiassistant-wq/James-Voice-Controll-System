"""Feedback: the floating transcript bar at the top of the screen, console lines and beeps.

The bar looks like the one in the Jev demo: a dark rounded pill at the top centre with a live
waveform on the left and the words appearing as you speak; when a line is too long the oldest
words slide out on the left. Under it a small chip shows what was just done ("✓ Notepad khola").
It fades in when Right Alt goes down and fades out ~1.5 s after the last action finished.

The window never takes focus, lets clicks through and has no taskbar button
(WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW), so "type hello" still types into
the app you were using.
"""
from __future__ import annotations

import logging
import math
import queue
import sys
import threading
import time

log = logging.getLogger("voicemode")

KEY = "#010203"                      # colour keyed out as transparent (Windows)
PILL, PILL_EDGE = "#2c2c2e", "#3a3a3c"
TEXT, HINT, DIM = "#f5f5f7", "#8e8e93", "#636366"
CHIP = "#1c1c1e"
OK, ERR, ASK = "#34c759", "#ff453a", "#bf5af2"
PLACEHOLDER = "Boliye, sun raha hoon…"


# ---------------------------------------------------------------- pure helpers (tested)

def fit_tail(text: str, measure, max_width: float) -> str:
    """Longest ending of `text` that fits in `max_width` (px), with a leading "…" when cut.
    `measure(s)` returns the pixel width of s."""
    text = " ".join(text.split())
    if measure(text) <= max_width:
        return text
    lo, hi = 1, len(text)
    while lo < hi:                   # smallest start index that fits
        mid = (lo + hi) // 2
        if measure("…" + text[mid:]) <= max_width:
            hi = mid
        else:
            lo = mid + 1
    return "…" + text[lo:].lstrip()


WEIGHTS = (0.55, 0.85, 1.0, 0.8, 0.5)


def bar_heights(level: float, t: float, lo: float, hi: float, active: bool = True) -> list[float]:
    """Heights of the five waveform bars for mic loudness `level` (RMS) at time `t`."""
    loud = min(1.0, max(0.0, (level - 0.004) * 9.0)) if active else 0.0
    out = []
    for i, w in enumerate(WEIGHTS):
        wobble = 0.65 + 0.35 * math.sin(t * (7.0 + i * 1.7) + i * 1.3)
        idle = 0.12 + 0.06 * math.sin(t * 2.2 + i) if active else 0.1
        out.append(lo + (hi - lo) * max(idle, loud * w * wobble))
    return out


def beep(kind: str):
    if sys.platform != "win32":
        return
    import winsound
    tone = {"start": [(880, 50)], "stop": [(560, 50)], "error": [(260, 140)], "confirm": [(660, 70), (880, 70)]}
    threading.Thread(target=lambda: [winsound.Beep(f, d) for f, d in tone.get(kind, [])], daemon=True).start()


class Feedback:
    """The controller/listener side of the UI; every method is thread-safe."""

    def __init__(self, overlay: "Overlay | None" = None, beeps: bool = True, console: bool = True):
        self.overlay = overlay
        self.beeps = beeps
        self.console = console
        self._last_final = None

    def _ov(self, *msg):
        if self.overlay is not None:
            self.overlay.q.put(msg)

    def status(self, state: str, text: str = ""):
        if state == "listening":
            self._ov("listen")
        elif state == "confirm":
            self._ov("action", text, "ask")
            if self.beeps:
                beep("confirm")
            if self.console and text:
                print(f"  ? {text}", flush=True)
        elif state == "loading" and self.console and text:
            print(f"  … {text}", flush=True)

    def transcript(self, text: str, final: bool):
        self._ov("final" if final else "partial", text)
        if self.console and final and text and text != self._last_final:
            self._last_final = text
            print(f"🎤 {text}", flush=True)

    def released(self):
        self._ov("release")

    def action(self, message: str, ok: bool = True):
        self._ov("action", message, "ok" if ok else "err")
        if self.console:
            print(f"  {'✓' if ok else '✗'} {message}", flush=True)
        if not ok and self.beeps:
            beep("error")

    def finished(self):
        self._ov("finished")

    def beep(self, kind: str):
        if self.beeps:
            beep(kind)


class Overlay:
    """The bar itself (Tk). `run()` blocks and must be called from the main thread."""

    FADE_AFTER = 1.5          # s after release + last action
    CONFIRM_HOLD = 9.0        # keep a pending question on screen this long

    def __init__(self, level_fn=None, width: int = 540):
        self.q: queue.Queue = queue.Queue()
        self.level_fn = level_fn or (lambda: 0.0)
        self.base_width = width
        self.root = None

    # -------------------------------------------------------------- drawing helpers
    @staticmethod
    def _round_rect(cv, x1, y1, x2, y2, r, **kw):
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)

    def run(self, stop: threading.Event, script=None):
        import tkinter as tk
        import tkinter.font as tkfont

        root = tk.Tk()
        self.root = root
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        S = lambda v: int(round(v * scale))                       # noqa: E731
        W, PH, GAP, CH = S(self.base_width), S(44), S(8), S(28)
        H = PH + GAP + CH + S(4)
        sw = root.winfo_screenwidth()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{S(14)}")
        win = sys.platform == "win32"
        bg = KEY if win else "#1b1b1f"
        root.configure(bg=bg)
        if win:
            root.attributes("-transparentcolor", KEY)
        cv = tk.Canvas(root, width=W, height=H, bg=bg, highlightthickness=0, bd=0)
        cv.pack()
        family = "Segoe UI" if win else "DejaVu Sans"
        font = tkfont.Font(family=family, size=12)
        chip_font = tkfont.Font(family=family, size=10, weight="bold")

        self._round_rect(cv, 1, 1, W - 1, PH - 1, S(13), fill=PILL, outline=PILL_EDGE, width=1)
        bx0, bw, bgap, blo, bhi = S(17), S(3), S(4), S(4), S(20)
        cy = PH / 2
        bars = [cv.create_line(bx0 + i * (bw + bgap), cy - 2, bx0 + i * (bw + bgap), cy + 2, width=bw,
                               fill=TEXT, capstyle="round") for i in range(5)]
        tx = bx0 + 5 * (bw + bgap) + S(10)
        text_max = W - tx - S(64)
        label = cv.create_text(tx, cy, text=PLACEHOLDER, fill=HINT, font=font, anchor="w")
        sq = S(11)
        sqx = W - S(46)
        self._round_rect(cv, sqx, cy - sq / 2, sqx + sq, cy + sq / 2, S(3), fill="#e5e5ea", outline="")
        cv.create_text(W - S(20), cy - S(1), text="⋯", fill=HINT, font=font)
        chip_bg = self._round_rect(cv, 0, 0, 1, 1, S(14), fill=CHIP, outline="", state="hidden")
        chip_tx = cv.create_text(W / 2, PH + GAP + CH / 2, text="", fill=OK, font=chip_font, state="hidden")

        st = {"visible": False, "alpha": 0.0, "target": 0.0, "listening": False, "released": True,
              "busy": False, "hide_at": 0.0, "text": "", "levels": [0.0] * 5, "hold_until": 0.0,
              "chip_bg": chip_bg}
        root.attributes("-alpha", 0.0)
        root.deiconify()
        root.update_idletasks()
        if win:
            self._no_activate(root)

        def set_text(t):
            st["text"] = t
            if t:
                cv.itemconfig(label, text=fit_tail(t, font.measure, text_max), fill=TEXT)
            else:
                cv.itemconfig(label, text=PLACEHOLDER if st["listening"] else "", fill=HINT)

        def set_chip(msg, kind):
            if not msg:
                cv.itemconfig(st["chip_bg"], state="hidden")
                cv.itemconfig(chip_tx, state="hidden")
                return
            icon = {"ok": "✓", "err": "✗", "ask": "?"}[kind]
            shown = fit_tail(f"{icon}  {msg}", chip_font.measure, W - S(40))
            if not shown.startswith(icon):
                shown = f"{icon}  " + fit_tail(msg, chip_font.measure, W - S(70))
            cv.itemconfig(chip_tx, text=shown, fill={"ok": OK, "err": ERR, "ask": ASK}[kind], state="normal")
            w = chip_font.measure(shown) + S(28)
            x1, y1 = (W - w) / 2, PH + GAP
            cv.delete(st["chip_bg"])
            st["chip_bg"] = self._round_rect(cv, x1, y1, x1 + w, y1 + CH, S(14), fill=CHIP, outline="")
            cv.tag_lower(st["chip_bg"], chip_tx)

        def show():
            # The window stays mapped the whole time (alpha 0 = invisible and click-through), so
            # showing it is only an alpha change: never a ShowWindow that could steal focus.
            if not st["visible"]:
                root.attributes("-topmost", True)
                st["visible"] = True
            st["target"] = 0.96

        def handle(kind, *a):
            now = time.time()
            if kind == "listen":
                st.update(listening=True, released=False, busy=True, hide_at=0.0)
                set_text("")
                set_chip("", "ok")
                show()
            elif kind == "partial":
                if a[0]:
                    set_text(a[0])
            elif kind == "final":
                if a[0]:
                    set_text(a[0])
            elif kind == "release":
                st.update(listening=False, released=True)
                if not st["text"]:
                    cv.itemconfig(label, text="", fill=HINT)
            elif kind == "action":
                msg, k = a
                set_chip(msg, k)
                show()
                if k == "ask":
                    st["hold_until"] = now + self.CONFIRM_HOLD
            elif kind == "finished":
                st["busy"] = False
            if st["released"] and not st["busy"]:
                st["hide_at"] = max(now + self.FADE_AFTER, st["hold_until"])

        t_start = time.time()

        def tick():
            if stop.is_set():
                root.destroy()
                return
            try:
                while True:
                    handle(*self.q.get_nowait())
            except queue.Empty:
                pass
            now = time.time()
            if st["visible"] and st["hide_at"] and now >= st["hide_at"]:
                st["target"] = 0.0
            # fade
            a, tgt = st["alpha"], st["target"]
            if a != tgt:
                step = 0.16 if tgt > a else 0.07
                a = min(tgt, a + step) if tgt > a else max(tgt, a - step)
                st["alpha"] = a
                try:
                    root.attributes("-alpha", a)
                except tk.TclError:
                    pass
                if a == 0.0 and tgt == 0.0:
                    st["visible"] = False
                    st["hide_at"] = 0.0
            # waveform
            if st["visible"]:
                lvl = self.level_fn() if st["listening"] else 0.0
                hs = bar_heights(lvl, now - t_start, blo, bhi, active=st["listening"])
                for i, (bar, h) in enumerate(zip(bars, hs)):
                    prev = st["levels"][i]
                    h = h if h > prev else prev * 0.75 + h * 0.25       # fast attack, slow decay
                    st["levels"][i] = h
                    x = bx0 + i * (bw + bgap)
                    cv.coords(bar, x, cy - h / 2, x, cy + h / 2)
                    cv.itemconfig(bar, fill=TEXT if st["listening"] else DIM)
            root.after(33, tick)

        if script is not None:                # used by the preview renderer / tests
            script(self, root)
        root.after(33, tick)
        root.mainloop()

    @staticmethod
    def _no_activate(root):
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x08000000 | 0x80 | 0x20 | 0x80000 | 0x8   # NOACTIVATE|TOOLWINDOW|TRANSPARENT|LAYERED|TOPMOST
        style &= ~0x40000                                   # no WS_EX_APPWINDOW: no taskbar button
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


# ---------------------------------------------------------------- demo (no mic needed)

DEMO_TEXT = ("Notepad kholo, nayi file me hello likho, browser kholo, Google pe Norbert Wiener search karo, "
             "x.com kholo, Camera kholo, meri photo lo")


def demo_events():
    """The Hinglish test flow as overlay events: words stream in, actions land as they're heard."""
    words = DEMO_TEXT.split()
    out, t, shown = [(0.0, "listen")], 0.35, []
    acts = {1: "Notepad khol diya", 6: "Notepad me likh diya: “hello”", 8: "Browser khol diya",
            14: "Google pe search: “Norbert Wiener”", 16: "X khol diya", 18: "Camera khol diya",
            21: "Photo le li (Pictures › Camera Roll)"}
    for i, w in enumerate(words):
        shown.append(w)
        out.append((t, "partial", " ".join(shown)))
        if i in acts:
            out.append((t + 0.15, "action", acts[i], "ok"))
        t += 0.28
    out += [(t + 0.2, "release"), (t + 0.3, "final", " ".join(shown)), (t + 0.9, "finished")]
    return out


def run_demo(loop: bool = True, on_frame=None):
    """Show the bar with a scripted utterance (python -m voicemode --overlay-demo)."""
    stop = threading.Event()
    start = [time.time()]
    events = demo_events()
    speaking = {"on": False}

    def level():
        if not speaking["on"]:
            return 0.0
        t = time.time()
        return 0.02 + 0.03 * abs(math.sin(t * 5.3)) + 0.02 * abs(math.sin(t * 13.1))

    ov = Overlay(level_fn=level)

    def script(o, root):
        idx = [0]

        def pump():
            el = time.time() - start[0]
            while idx[0] < len(events) and events[idx[0]][0] <= el:
                ev = events[idx[0]]
                if ev[1] == "listen":
                    speaking["on"] = True
                elif ev[1] == "release":
                    speaking["on"] = False
                o.q.put(tuple(ev[1:]))
                idx[0] += 1
            if on_frame:
                on_frame(el, root)
            if idx[0] >= len(events) and el > events[-1][0] + 3.5:
                if not loop:
                    stop.set()
                    return
                start[0], idx[0] = time.time(), 0
            root.after(40, pump)

        root.after(300, pump)

    ov.run(stop, script=script)
