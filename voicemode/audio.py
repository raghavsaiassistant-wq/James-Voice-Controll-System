"""Microphone capture and the push-to-talk listening loop."""
from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from .stt import SR, find_pause, trailing_silence, voiced_seconds

log = logging.getLogger("voicemode")


class Recorder:
    """Opens the mic only while the key is held (the Windows mic indicator stays off otherwise)."""

    def __init__(self, device=None):
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._rate = SR
        self.level = 0.0            # loudness of the latest block, 0..~1 (drives the waveform icon)

    def _cb(self, indata, frames, t, status):
        block = indata[:, 0].copy()
        self.level = float(np.sqrt((block ** 2).mean() + 1e-12))
        with self._lock:
            self._chunks.append(block)

    def start(self):
        import sounddevice as sd
        with self._lock:
            self._chunks = []
        try:
            self._rate = SR
            self._stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=800,
                                          callback=self._cb, device=self.device)
        except Exception:
            # some drivers refuse 16 kHz: record at the device rate and resample
            info = sd.query_devices(self.device, "input")
            self._rate = int(info["default_samplerate"])
            self._stream = sd.InputStream(samplerate=self._rate, channels=1, dtype="float32",
                                          callback=self._cb, device=self.device)
        self._stream.start()

    def snapshot(self) -> np.ndarray:
        with self._lock:
            a = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        if self._rate != SR and a.size:
            n = int(a.size * SR / self._rate)
            a = np.interp(np.linspace(0, a.size - 1, n), np.arange(a.size), a).astype(np.float32)
        return a

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        self.level = 0.0
        return self.snapshot()


def join_text(a: str, b: str) -> str:
    a, b = a.strip(), b.strip()
    return f"{a} {b}".strip()


class Listener:
    """Key down -> record; while held, re-transcribe every ~0.4 s (partials); key up -> final.

    Whisper sees at most 30 s at a time, and long clips decode slowly, so a hold is streamed in
    pieces: once the not-yet-committed audio is longer than COMMIT_AFTER, it is cut at the last
    pause, that part is transcribed once and frozen ("committed"), and only the rest is
    re-transcribed on each tick. The user can talk for minutes in one hold.

    Partials carry the length of the current silence, so the controller can act on a command
    the moment the user pauses after it (endpointing), not only when the key is released.
    """

    COMMIT_AFTER = 5.0          # s of live audio before we look for a pause to commit at
    HARD_COMMIT = 18.0          # no pause at all for this long: cut anyway
    PAUSE_MARKS = (0.7, 1.2)    # emit a partial again when the silence crosses these

    def __init__(self, stt, recorder, settings, on_begin, on_partial, on_final, on_error=None, beep=None,
                 on_release=None):
        self.stt = stt
        self.rec = recorder
        self.settings = settings
        self.on_begin, self.on_partial, self.on_final = on_begin, on_partial, on_final
        self.on_release = on_release or (lambda: None)
        self.on_error = on_error or (lambda msg: log.error(msg))
        self.beep = beep or (lambda kind: None)
        self.events: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="listener", daemon=True)

    def start(self):
        self._thread.start()

    def press(self):
        self.events.put("down")

    def release(self):
        self.events.put("up")

    def _run(self):
        while True:
            if self.events.get() != "down":
                continue
            try:
                self._session()
            except Exception as e:
                log.exception("listening failed")
                self.on_error(f"Mic/speech error: {e}")

    def _emit(self, text: str, pause: float):
        self.on_partial(text, pause)

    def _session(self):
        try:
            self.rec.start()
        except Exception as e:
            self.on_error(f"Microphone nahi khula: {e}")
            self._drain_until_up()
            return
        self.beep("start")
        self.on_begin()
        interval = self.settings.partial_interval
        min_speech = self.settings.min_speech_seconds
        committed, offset = "", 0            # frozen text, and how many samples it covers
        last_len, last_text, mark = 0, "", 0
        t0 = time.time()
        while True:
            try:
                ev = self.events.get(timeout=interval)
            except queue.Empty:
                ev = None
            if ev == "up":
                break
            if ev == "down":
                continue                     # auto-repeat of the held key
            if time.time() - t0 > 600:
                break                        # safety: stuck key
            audio = self.rec.snapshot()
            live = audio[offset:]
            if voiced_seconds(live) < min_speech:
                continue
            if live.size > self.COMMIT_AFTER * SR:
                cut = find_pause(live, earliest=2.0, latest=live.size / SR - 1.0)
                if cut is None and live.size > self.HARD_COMMIT * SR:
                    cut = live.size - 2 * SR
                if cut:
                    committed = join_text(committed, self.stt.transcribe(live[:cut]))
                    offset += cut
                    live = audio[offset:]
                    last_len = 0
            silence = trailing_silence(live)
            new_mark = sum(silence >= m for m in self.PAUSE_MARKS)
            if audio.size - last_len < int(0.25 * SR):
                if new_mark > mark and last_text:
                    mark = new_mark          # only silence was added: same words, now a pause
                    self._emit(last_text, silence)
                continue
            tail = self.stt.transcribe(live) if voiced_seconds(live) >= min_speech else ""
            text = join_text(committed, tail)
            last_len = audio.size
            if text and (text != last_text or new_mark != mark):
                last_text, mark = text, new_mark
                self._emit(text, silence)
        audio = self.rec.stop()
        self.beep("stop")
        self.on_release()
        live = audio[offset:]
        if audio.size - last_len < int(0.15 * SR) and last_text:
            final = last_text
        else:
            tail = self.stt.transcribe(live) if voiced_seconds(live) >= min_speech else ""
            final = join_text(committed, tail)
        self.on_final(final)

    def _drain_until_up(self):
        while self.events.get() != "up":
            pass
