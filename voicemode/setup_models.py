"""Download the two offline models into ./models (run by setup; safe to re-run).

  models/stt   Oriserve/Whisper-Hindi2Hinglish-Swift   ~290 MB  speech -> text
  models/laya  convaiinnovations/laya (multilingual)   ~650 MB  decisions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import LAYA_REPO, LAYA_SUBFOLDER, MODELS_DIR, STT_REPO

STT_FILES = ["config.json", "model.safetensors", "preprocessor_config.json", "tokenizer.json",
             "generation_config.json"]
LAYA_FILES = [f"{LAYA_SUBFOLDER}/model.safetensors", f"{LAYA_SUBFOLDER}/rl_agent_config.json"]


def stt_ready(d: Path = MODELS_DIR / "stt") -> bool:
    return all((d / f).is_file() for f in STT_FILES)


def laya_ready(d: Path = MODELS_DIR / "laya") -> bool:
    return all((d / f).is_file() for f in LAYA_FILES) and (d / LAYA_SUBFOLDER / "encoder").is_dir() \
        and (d / LAYA_SUBFOLDER / "tokenizer").is_dir()


def size_mb(d: Path) -> int:
    return int(sum(p.stat().st_size for p in d.rglob("*") if p.is_file() and ".cache" not in p.parts) / 1e6)


def download(skip_laya: bool = False) -> bool:
    from huggingface_hub import snapshot_download
    ok = True
    stt = MODELS_DIR / "stt"
    if stt_ready(stt):
        print(f"  [OK] speech model already here ({size_mb(stt)} MB)")
    else:
        print(f"  ... downloading speech model {STT_REPO} (~290 MB)")
        snapshot_download(STT_REPO, local_dir=str(stt),
                          ignore_patterns=["audios/*", "*.md", "convert_hf2openai.json", ".gitattributes"])
        ok &= stt_ready(stt)
        print(f"  [{'OK' if stt_ready(stt) else 'X'}] speech model ({size_mb(stt)} MB)")
    if skip_laya:
        return ok
    laya = MODELS_DIR / "laya"
    if laya_ready(laya):
        print(f"  [OK] Laya model already here ({size_mb(laya)} MB)")
    else:
        print(f"  ... downloading Laya {LAYA_REPO}/{LAYA_SUBFOLDER} (~650 MB)")
        snapshot_download(LAYA_REPO, local_dir=str(laya), allow_patterns=[f"{LAYA_SUBFOLDER}/*"])
        ok &= laya_ready(laya)
        print(f"  [{'OK' if laya_ready(laya) else 'X'}] Laya model ({size_mb(laya)} MB)")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-laya", action="store_true", help="skip the Laya model (rules-only mode)")
    a = ap.parse_args(argv)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return 0 if download(skip_laya=a.no_laya) else 1
    except Exception as e:
        print(f"  [X] download failed: {e}\n      Internet check karo aur setup dobara chalao (resume ho jayega).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
