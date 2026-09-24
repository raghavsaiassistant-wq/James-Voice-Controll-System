"""Laya on real weights (slow, skipped when models/laya is missing)."""
import os
from pathlib import Path

import pytest

from voicemode.config import MODELS_DIR, Settings
from voicemode.setup_models import laya_ready

LAYA = Path(os.environ.get("VOICEMODE_LAYA_DIR", MODELS_DIR / "laya"))
pytestmark = pytest.mark.skipif(not laya_ready(LAYA), reason="Laya model not downloaded")


@pytest.fixture(scope="module")
def brain():
    from voicemode.brain import Brain
    b = Brain(str(LAYA))
    b._load()
    assert b.agent is not None, b.error
    return b


@pytest.mark.parametrize("text,intent", [
    ("please make the sound louder", "volume"),
    ("get rid of this tab", "close_tab"),
])
def test_fallback_understands_unlisted_phrasing(brain, text, intent):
    cmd = brain.classify(text)
    assert cmd is not None and cmd.intent == intent, cmd and cmd.describe()
    assert cmd.source == "laya"


def test_fallback_ignores_chatter(brain):
    assert brain.classify("so anyway I think we should get lunch") is None
    assert brain.classify("mummy khana bana rahi hai") is None


def test_semantic_element_pick_in_browser(brain, tmp_path):
    pytest.importorskip("playwright")
    from voicemode.actions.browser import Browser
    from voicemode.actions.system import DryRunSystem
    from voicemode.controller import Controller
    from voicemode.executor import Executor
    s = Settings()
    s.browser_profile = str(tmp_path / "p")
    s.extra.update(headless=True)
    if Path("/opt/pw-browsers/chromium").exists():
        s.extra["browser_executable"] = "/opt/pw-browsers/chromium"
    b = Browser(s, DryRunSystem(), brain)
    try:
        b.open((Path(__file__).parent / "fixtures" / "shop.html").resolve().as_uri())
        ctl = Controller(Executor(s, b.system, b, brain), brain, settings=s)
        ctl.begin()
        ctl.final("cart me daal do pe click karo")
        assert b.page().evaluate("window.clicks") == ["cart"]
    finally:
        b.shutdown()
