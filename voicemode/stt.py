"""Offline speech-to-text: Whisper-Hindi2Hinglish-Swift (whisper-base fine-tuned on Indian
accented Hindi). Decoding is forced to the English token set, so Hindi, Hinglish and English
all come out in Roman script: "youtube pe lofi songs chalao".
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

import numpy as np

log = logging.getLogger("voicemode")
SR = 16000

# Whisper tends to invent these on near-silent audio.
HALLUCINATIONS = re.compile(
    r"^\s*(thank you( so much)?( for watching)?|thanks( for watching)?|bye|you|okay|subscribe.*|"
    r"please subscribe.*|shukriya|dhanyavaad|\.+|music|\[music\]|\(music\))\s*[.!]*\s*$", re.I)


def default_threads() -> int:
    n = os.cpu_count() or 4
    return max(1, min(4, n // 2 if n >= 8 else n))


def voiced_seconds(audio: np.ndarray, sr: int = SR) -> float:
    """Rough amount of speech: 30 ms frames clearly above the noise floor."""
    if audio.size < sr // 10:
        return 0.0
    hop = int(sr * 0.03)
    n = audio.size // hop
    frames = audio[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    # noise floor from the quietest frames, capped: with non-stop speech there are no quiet frames
    floor = np.percentile(rms, 10)
    thresh = max(0.008, min(floor * 3.0, 0.03))
    return float((rms > thresh).sum()) * 0.03


class SpeechToText:
    def __init__(self, model_dir: str, threads: int = 0, quantize: bool = True):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
        self.torch = torch
        torch.set_num_threads(threads or default_threads())
        t = time.time()
        self.processor = WhisperProcessor.from_pretrained(model_dir)
        model = WhisperForConditionalGeneration.from_pretrained(model_dir, torch_dtype=torch.float32)
        model.eval()
        if quantize:
            try:
                model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
            except Exception as e:      # some torch builds lack quantized kernels
                log.warning("int8 quantization unavailable, using fp32: %s", e)
        self.model = model
        gc = self.model.generation_config
        gc.forced_decoder_ids = None
        self.gen = dict(language="en", task="transcribe", max_new_tokens=96, num_beams=1, do_sample=False)
        self._lock = threading.Lock()
        self.transcribe(np.zeros(SR // 2, dtype=np.float32))          # warm-up
        log.info("speech model ready in %.1fs", time.time() - t)

    def transcribe(self, audio: np.ndarray) -> str:
        audio = np.asarray(audio, dtype=np.float32)
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 0:
            audio = audio * min(1.0 / peak * 0.9, 20.0)            # quiet mics: normalise gain
        feats = self.processor(audio, sampling_rate=SR, return_tensors="pt").input_features
        with self._lock, self.torch.inference_mode():
            ids = self.model.generate(feats, **self.gen)
        text = self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        if HALLUCINATIONS.match(text):
            return ""
        return text
