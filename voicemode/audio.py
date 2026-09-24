"""Microphone capture and the push-to-talk listening loop."""
from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from .stt import SR, voiced_seconds

log = logging.getLogger("voicemode")


class Recorder:
    """Opens the mic only while the key is held (the Windows mic indicator stays off otherwise)."""

    def __init__(self, device=None):
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._rate = SR

    def _cb(self, indata, frames, t, status):
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

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
        return self.snapshot()


class Listener:
    """Key down -> record; while held, re-transcribe every ~0.45 s (partials); key up -> final."""

    def __init__(self, stt, recorder, settings, on_begin, on_partial, on_final, on_error=None, beep=None):
        self.stt = stt
        self.rec = recorder
        self.settings = settings
        self.on_begin, self.on_partial, self.on_final = on_begin, on_partial, on_final
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
        last_len, last_text = 0, ""
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
            if time.time() - t0 > 60:
                break                        # safety: stuck key
            audio = self.rec.snapshot()
            if audio.size - last_len < int(0.3 * SR) or voiced_seconds(audio) < min_speech:
                continue
            text = self.stt.transcribe(audio)
            last_len = audio.size
            if text and text != last_text:
                last_text = text
                self.on_partial(text)
        audio = self.rec.stop()
        self.beep("stop")
        final = ""
        if voiced_seconds(audio) >= min_speech:
            final = last_text if audio.size - last_len < int(0.15 * SR) and last_text else self.stt.transcribe(audio)
        self.on_final(final)

    def _drain_until_up(self):
        while self.events.get() != "up":
            pass
