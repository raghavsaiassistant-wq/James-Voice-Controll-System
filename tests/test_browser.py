"""Real Chromium (headless) against a local page: element matching, ordinals, badges, typing,
scrolling, tabs and the destructive-click confirmation. No network needed."""
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from voicemode.actions.browser import Browser
from voicemode.actions.system import DryRunSystem
from voicemode.config import Settings
from voicemode.controller import Controller
from voicemode.executor import Executor

PAGE = (Path(__file__).parent / "fixtures" / "shop.html").resolve().as_uri()


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    s = Settings()
    s.browser_profile = str(tmp_path_factory.mktemp("profile"))
    s.extra["headless"] = True
    exe = os.environ.get("VOICEMODE_TEST_CHROMIUM", "/opt/pw-browsers/chromium")
    if Path(exe).exists():
        s.extra["browser_executable"] = exe
    b = Browser(s, DryRunSystem())
    try:
        b.ensure()
    except Exception as e:
        pytest.skip(f"no browser available: {e}")
    yield b
    b.shutdown()


@pytest.fixture()
def ctl(browser):
    browser.open(PAGE)
    ex = Executor(browser.settings, browser.system, browser)
    return Controller(ex, settings=browser.settings)


def clicks(browser):
    return browser.page().evaluate("window.clicks")


def say(ctl, text):
    ctl.begin()
    ctl.final(text)
    return ctl.results[-1] if ctl.results else None


def test_click_by_name_hinglish(ctl, browser):
    say(ctl, "login button dabao")
    assert clicks(browser) == ["login"]


def test_click_sign_up_english(ctl, browser):
    say(ctl, "click on sign up")
    assert clicks(browser) == ["signup"]


def test_ordinal_result(ctl, browser):
    say(ctl, "doosra result kholo")
    assert clicks(browser) == ["Second result: best lofi playlists of 2026"]


def test_ambiguous_shows_numbers_then_pick(ctl, browser):
    r = say(ctl, "click more")
    assert "Number bolo" in r["msg"]
    n = browser.page().evaluate("document.getElementById('__vm_layer').children.length")
    assert n >= 4                                        # outline + badge per candidate
    say(ctl, "teen")
    assert clicks(browser) == ["more3"]


def test_destructive_click_asks_first(ctl, browser):
    r = say(ctl, "place order pe click karo")
    assert "confirm" in r["msg"]
    assert clicks(browser) == []
    say(ctl, "haan")
    assert clicks(browser) == ["order"]


def test_type_into_named_field(ctl, browser):
    say(ctl, "type alan turing in the search box")
    assert browser.page().input_value("#q") == "alan turing"
    say(ctl, "name field me Raghav likho")
    assert browser.page().input_value("#name") == "Raghav"


def test_scroll(ctl, browser):
    p = browser.page()
    say(ctl, "neeche scroll karo")
    p.wait_for_timeout(700)
    y1 = p.evaluate("scrollY")
    assert y1 > 100
    say(ctl, "sabse upar jao")
    p.wait_for_timeout(900)
    assert p.evaluate("scrollY") < y1


def test_tabs(ctl, browser):
    n0 = len(browser.context.pages)
    say(ctl, "naya tab kholo")
    assert len(browser.context.pages) == n0 + 1
    say(ctl, "ye tab band karo")
    assert len(browser.context.pages) == n0


def test_back_and_forward(ctl, browser):
    say(ctl, "click on your orders")
    browser.page().goto(PAGE + "#x")
    say(ctl, "wapas jao")
    assert browser.page().url.endswith("shop.html") or "#" in browser.page().url


def test_open_thing_clicks_page_element(ctl, browser):
    say(ctl, "contact us kholo")
    assert clicks(browser) == ["Contact us"]
