"""Settings. Defaults live here; `settings.json` in the repo root overrides any of them."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"

STT_REPO = "Oriserve/Whisper-Hindi2Hinglish-Swift"
LAYA_REPO = "convaiinnovations/laya"
LAYA_SUBFOLDER = "multilingual"


@dataclass
class Settings:
    # Push-to-talk key, held while speaking. One of hotkey.KEYS (right_alt, right_ctrl, f8, ...).
    hotkey: str = "right_alt"
    # Speech-to-text
    stt_model_dir: str = str(MODELS_DIR / "stt")
    stt_threads: int = 0                 # 0 = auto (physical cores, max 4)
    stt_quantize: bool = False           # int8 linear layers: ~35% faster on CPU, drops words on long Hindi
    partial_interval: float = 0.3        # seconds between live re-transcriptions while holding
    min_speech_seconds: float = 0.35
    # Laya (local decision model). Off -> rules only, less RAM.
    use_laya: bool = True
    laya_dir: str = str(MODELS_DIR / "laya")
    laya_min_confidence: float = 0.75
    # Browser
    browser_channel: str = ""            # "" = bundled Chromium, or "msedge" / "chrome"
    browser_profile: str = str(DATA_DIR / "browser-profile")
    search_engine: str = "google"        # site key from catalog.SITES with a search URL
    # Feedback
    overlay: bool = True
    beeps: bool = True
    # Act on partial transcripts (while the key is still held) when a command is unambiguous.
    act_while_speaking: bool = True
    pause_act_seconds: float = 0.7       # a pause this long after a command = it's complete
    pause_act_free_seconds: float = 1.2  # ... for search / typed text (a query may continue)
    camera_warmup: float = 2.5           # seconds for the Camera app to start before a photo
    confirm_timeout: float = 20.0
    log_utterances: bool = True
    extra: dict = field(default_factory=dict)


def load() -> Settings:
    s = Settings()
    path = ROOT / "settings.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {f.name for f in fields(Settings)}
        for k, v in data.items():
            if k in names:
                setattr(s, k, v)
            else:
                s.extra[k] = v
    return s


def dump(s: Settings) -> str:
    return json.dumps(asdict(s), indent=2)


def force_offline() -> None:
    """Never touch the network for models at runtime; everything was downloaded by setup."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
