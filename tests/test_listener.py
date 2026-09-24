"""Push-to-talk loop with a fake mic and a fake recognizer: partials while held, one final."""
import threading
import time

import numpy as np

from voicemode.audio import Listener
from voicemode.config import Settings

SR = 16000


class FakeRecorder:
    def __init__(self):
        self.t0 = None

    def start(self):
        self.t0 = time.time()

    def snapshot(self):
        n = int((time.time() - self.t0) * SR)
        t = np.arange(n) / SR
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)     # "speech" all along

    def stop(self):
        return self.snapshot()


class FakeSTT:
    WORDS = ["youtube", "kholo", "aur", "lofi", "search", "karo"]

    def transcribe(self, audio):
        k = min(len(self.WORDS), int(len(audio) / SR / 0.25))
        return " ".join(self.WORDS[:k])


def test_partials_then_final():
    got = {"begin": 0, "partial": [], "final": None}
    done = threading.Event()
    s = Settings()
    s.partial_interval = 0.1
    lst = Listener(FakeSTT(), FakeRecorder(), s,
                   on_begin=lambda: got.__setitem__("begin", got["begin"] + 1),
                   on_partial=lambda t, pause: got["partial"].append(t),
                   on_final=lambda t: (got.__setitem__("final", t), done.set()))
    lst.start()
    lst.press()
    time.sleep(0.05)
    lst.press()                      # key auto-repeat must not restart the session
    time.sleep(1.6)
    lst.release()
    assert done.wait(3)
    assert got["begin"] == 1
    assert len(got["partial"]) >= 2
    assert got["partial"] == sorted(got["partial"], key=len)      # growing transcripts
    assert got["final"] == "youtube kholo aur lofi search karo"


def test_silence_gives_empty_final():
    class Silent(FakeRecorder):
        def snapshot(self):
            return np.zeros(int((time.time() - self.t0) * SR), np.float32)

    out = {}
    done = threading.Event()
    lst = Listener(FakeSTT(), Silent(), Settings(), on_begin=lambda: None,
                   on_partial=lambda t, pause: out.setdefault("p", t),
                   on_final=lambda t: (out.__setitem__("f", t), done.set()))
    lst.start()
    lst.press()
    time.sleep(0.6)
    lst.release()
    assert done.wait(3)
    assert out == {"f": ""}


def test_long_hold_is_committed_in_pieces():
    """A 25 s hold (Whisper sees max 30 s) is cut at pauses; the final text keeps every piece."""
    from voicemode.audio import Listener as L

    class Speech(FakeRecorder):
        # 1.6 s of "speech" then 0.4 s pause, repeated
        def snapshot(self):
            n = int((time.time() - self.t0) * SR * 10)          # 10x faster than real time
            t = np.arange(n) / SR
            on = (t % 2.0) < 1.6
            return (0.3 * np.sin(2 * np.pi * 220 * t) * on).astype(np.float32)

    class CountSTT:
        def __init__(self):
            self.calls = []

        def transcribe(self, audio):
            self.calls.append(len(audio) / SR)
            return f"[{round(len(audio) / SR)}s]"

    stt = CountSTT()
    got = {}
    done = threading.Event()
    s = Settings()
    s.partial_interval = 0.05
    lst = L(stt, Speech(), s, on_begin=lambda: None, on_partial=lambda t, p: None,
            on_final=lambda t: (got.__setitem__("f", t), done.set()))
    lst.start()
    lst.press()
    time.sleep(2.5)                       # ~25 s of audio
    lst.release()
    assert done.wait(3)
    assert max(stt.calls) < 12            # never hands Whisper a huge clip
    pieces = got["f"].split()
    assert len(pieces) >= 3               # committed several times
    total = sum(int(p.strip("[]s")) for p in pieces)
    assert 20 <= total <= 30              # and nothing was lost or doubled


def test_overlay_helpers():
    from voicemode.overlay import bar_heights, fit_tail
    measure = lambda s: 10 * len(s)                       # noqa: E731
    assert fit_tail("hello world", measure, 200) == "hello world"
    t = fit_tail("Notepad kholo nayi file me hello likho browser kholo", measure, 200)
    assert t.startswith("…") and len(t) <= 20 and t.endswith("browser kholo")
    quiet = bar_heights(0.0, 1.0, 4, 20)
    loud = bar_heights(0.2, 1.0, 4, 20)
    assert all(4 <= h <= 20 for h in quiet + loud)
    assert sum(loud) > sum(quiet) * 2
    assert bar_heights(0.5, 1.0, 4, 20, active=False) == bar_heights(0.0, 1.0, 4, 20, active=False)
