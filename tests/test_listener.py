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
                   on_partial=lambda t: got["partial"].append(t),
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
                   on_partial=lambda t: out.setdefault("p", t),
                   on_final=lambda t: (out.__setitem__("f", t), done.set()))
    lst.start()
    lst.press()
    time.sleep(0.6)
    lst.release()
    assert done.wait(3)
    assert out == {"f": ""}
