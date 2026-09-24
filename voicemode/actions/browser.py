"""The controlled browser: a Playwright Chromium window with its own profile.

All methods must be called from one thread (Playwright's sync API is single-threaded); the
app runs every action on its executor thread. The window is launched lazily on the first
browser command, so system-only use never opens a browser.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from rapidfuzz import fuzz

from .. import catalog
from ..text import canon_phrase

log = logging.getLogger("voicemode")
PAGE_JS = (Path(__file__).with_name("page.js")).read_text(encoding="utf-8")

RESULT_SELECTORS = {
    "google": ["#search a h3", "#rso a h3", "a h3"],
    "youtube": ["ytd-video-renderer a#video-title", "ytd-rich-item-renderer a#video-title-link",
                "a#video-title"],
    "duckduckgo": ["a[data-testid=result-title-a]", "article h2 a"],
    "bing": ["#b_results h2 a"],
    "wikipedia": [".mw-search-result-heading a"],
    "amazon": ["div[data-component-type=s-search-result] h2 a",
               "div[data-component-type=s-search-result] a h2"],
    "github": ["[data-testid=results-list] h3 a", ".search-title a"],
    "reddit": ["a[data-testid=post-title]", "a[slot=title]"],
    "hackernews": [".titleline > a"],
}
GENERIC_RESULTS = ["main h2 a", "main h3 a", "article h2 a", "article h3 a", "h2 a", "h3 a", "[role=main] a h3"]
DESTRUCTIVE = re.compile(r"\b(buy|pay|place (your )?order|order now|checkout|check out|purchase|delete|remove|"
                         r"send|submit|confirm (order|payment)|unsubscribe|kharido|khareedo|bhejo|delete karo)\b", re.I)


@dataclass
class El:
    id: str
    role: str
    name: str
    placeholder: str = ""
    href: str = ""
    inView: bool = False
    top: int = 0
    chrome: bool = False
    search: bool = False

    def label(self) -> str:
        return f"{self.role}: {self.name or self.placeholder}"


def fold(s: str) -> str:
    return " ".join(canon_phrase(s))


def score(query: str, el: El, kind: str | None = None) -> float:
    q = fold(query)
    n = fold(el.name or el.placeholder)
    if not q or not n:
        return 0.0
    s = max(fuzz.token_set_ratio(q, n), fuzz.ratio(q.replace(" ", ""), n.replace(" ", "")))
    if len(q) >= 4:
        s = max(s, fuzz.partial_ratio(q, n) - 8)
    if len(n) > 4 * len(q) + 20:
        s -= 8                     # a long paragraph link that happens to contain the word
    if kind in ("button",) and el.role == "button":
        s += 5
    if kind in ("link", "result") and el.role == "link":
        s += 5
    if kind == "video" and "watch" in el.href:
        s += 8
    if el.inView:
        s += 3
    return s


class Browser:
    def __init__(self, settings, system=None, brain=None):
        self.settings = settings
        self.system = system
        self.brain = brain
        self._pw = None
        self.context = None
        self._active = None
        self.candidates: list[str] = []      # ids shown as numbered badges

    # ------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self.context is not None

    def ensure(self):
        if self.context is not None:
            return                      # a manual close of the window resets this via _on_close
        from playwright.sync_api import sync_playwright
        if self._pw is None:
            self._pw = sync_playwright().start()
        kw = dict(headless=bool(self.settings.extra.get("headless", False)), no_viewport=True,
                  args=["--start-maximized", "--disable-features=Translate"],
                  ignore_default_args=["--enable-automation"])
        if self.settings.browser_channel:
            kw["channel"] = self.settings.browser_channel
        exe = self.settings.extra.get("browser_executable")
        if exe:
            kw["executable_path"] = exe
        Path(self.settings.browser_profile).mkdir(parents=True, exist_ok=True)
        self.context = self._pw.chromium.launch_persistent_context(self.settings.browser_profile, **kw)
        self.context.on("page", self._on_page)
        self.context.on("close", lambda *_: self._on_close())
        self._active = self.context.pages[0] if self.context.pages else self.context.new_page()

    def _on_page(self, page):
        self._active = page

    def _on_close(self):
        self.context = None
        self._active = None

    def close(self):
        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass
        self.context = None
        self._active = None

    def shutdown(self):
        self.close()
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def page(self):
        self.ensure()
        pages = self.context.pages
        if not pages:
            self._active = self.context.new_page()
        elif self._active not in pages:
            self._active = pages[-1]
        return self._active

    def front(self):
        p = self.page()
        try:
            p.bring_to_front()
        except Exception:
            pass
        if self.system is not None:
            try:
                self.system.focus_title(p.title())
            except Exception:
                pass
        return p

    def is_foreground(self) -> bool:
        if not self.running:
            return False
        if self.system is None or not getattr(self.system, "real", False):
            return True
        try:
            fg = self.system.foreground()
            if fg is None or fg.exe not in ("chrome.exe", "msedge.exe", "chromium.exe"):
                return False
            t = self._active.title() if self._active else ""
            return not t or t[:40] in fg.title
        except Exception:
            return False

    def site(self):
        try:
            return catalog.site_for_url(self.page().url)
        except Exception:
            return None

    # ------------------------------------------------------------ navigation
    def open(self, url: str) -> str:
        p = self.front()
        self.candidates = []
        try:
            p.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            if "ERR_INTERNET_DISCONNECTED" in str(e) or "ERR_NAME_NOT_RESOLVED" in str(e):
                raise RuntimeError("Internet connection nahi mila — website nahi khul payi") from e
            raise
        return p.title() or url

    def search(self, query: str, site_key: str | None) -> str:
        site = catalog.SITE_BY_KEY.get(site_key) if site_key else None
        if site is None or not site.search:
            cur = self.site() if self.running else None
            if cur is not None and cur.search and cur.key not in ("google", "bing", "duckduckgo"):
                site = cur                          # "search for lofi" while on YouTube
        if site is None or not site.search:
            site = catalog.SITE_BY_KEY.get(self.settings.search_engine) or catalog.SITE_BY_KEY["google"]
        self.open(site.search.format(q=quote_plus(query)))
        return site.key

    def play_youtube(self, query: str) -> str:
        self.open(catalog.SITE_BY_KEY["youtube"].search.format(q=quote_plus(query)))
        p = self.page()
        sel = "ytd-video-renderer a#video-title"
        p.wait_for_selector(sel, timeout=12000)
        first = p.locator(sel).first
        title = (first.get_attribute("title") or first.inner_text() or "").strip()
        first.click(timeout=8000)
        return title

    def back(self):
        self.front().go_back(wait_until="domcontentloaded", timeout=15000)

    def forward(self):
        self.front().go_forward(wait_until="domcontentloaded", timeout=15000)

    def reload(self):
        self.front().reload(wait_until="domcontentloaded", timeout=20000)

    # ------------------------------------------------------------ tabs
    def new_tab(self, url: str | None = None):
        self.ensure()
        self._active = self.context.new_page()
        if url:
            self._active.goto(url, wait_until="domcontentloaded", timeout=25000)
        self.front()

    def close_tab(self, site_key: str | None = None) -> bool:
        if not self.running:
            return False
        pages = self.context.pages
        target = self._active
        if site_key:
            match = [p for p in pages if (catalog.site_for_url(p.url) or catalog.Site("", [], "")).key == site_key]
            if not match:
                return False
            target = match[-1]
        if target is None:
            return False
        idx = pages.index(target) if target in pages else len(pages) - 1
        if len(pages) == 1:
            target.goto("about:blank")          # keep the window; closing the last tab quits it
        else:
            target.close()
            rest = self.context.pages
            self._active = rest[min(idx, len(rest) - 1)]
        self.front()
        return True

    def switch_tab(self, delta: int = 0, n: int | None = None) -> int:
        self.ensure()
        pages = self.context.pages
        if not pages:
            return 0
        cur = pages.index(self._active) if self._active in pages else 0
        if n is not None:
            idx = (len(pages) - 1) if n == -1 else max(0, min(n - 1, len(pages) - 1))
        else:
            idx = (cur + delta) % len(pages)
        self._active = pages[idx]
        self.front()
        return idx + 1

    # ------------------------------------------------------------ page content
    def _js(self):
        p = self.page()
        try:
            p.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        p.evaluate(PAGE_JS)
        return p

    def snapshot(self, limit: int = 400) -> list[El]:
        p = self._js()
        raw = p.evaluate("(n) => window.__vm.snapshot(n)", limit)
        return [El(**r) for r in raw]

    def _result_ids(self, kind: str | None) -> list[str]:
        p = self.page()
        site = self.site()
        sels = []
        if kind == "video" or (site and site.key == "youtube"):
            sels += RESULT_SELECTORS["youtube"]
        if site and site.key in RESULT_SELECTORS:
            sels += RESULT_SELECTORS[site.key]
        sels += GENERIC_RESULTS
        return p.evaluate("(s) => window.__vm.results(s)", sels)

    def highlight(self, el_id: str):
        try:
            self.page().evaluate("(i) => window.__vm.highlight(i)", el_id)
        except Exception:
            pass

    def clear_badges(self):
        self.candidates = []
        try:
            self.page().evaluate("() => window.__vm && window.__vm.clear()")
        except Exception:
            pass

    def _click_id(self, el_id: str, double: bool = False):
        p = self.page()
        self.highlight(el_id)
        loc = p.locator(f'[data-vm-id="{el_id}"]').first
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
            if double:
                loc.dblclick(timeout=5000)
            else:
                loc.click(timeout=5000)
        except Exception:
            loc.evaluate("(e) => e.click()")          # covered by an overlay etc.

    def resolve(self, name: str | None, ordinal: int | None, kind: str | None):
        """-> ("click", El) | ("choose", [El...]) | ("none", None)"""
        els = self.snapshot()
        by_id = {e.id: e for e in els}
        if ordinal is not None:
            ids = [i for i in self._result_ids(kind) if i in by_id]
            if not ids:
                ids = [e.id for e in els if e.role == "link" and len(e.name) >= 12 and not e.chrome]
            ids = list(dict.fromkeys(ids))
            if not ids:
                return "none", None
            if ordinal == -1:
                return "click", by_id[ids[-1]]
            if 1 <= ordinal <= len(ids):
                return "click", by_id[ids[ordinal - 1]]
            return "none", None
        if not name:
            return "none", None
        ranked = sorted(((score(name, e, kind), e) for e in els), key=lambda x: -x[0])
        ranked = [r for r in ranked if r[0] > 0]
        if not ranked:
            return "none", None
        top, second = ranked[0][0], (ranked[1][0] if len(ranked) > 1 else 0)
        same = len(ranked) > 1 and fold(ranked[0][1].name) == fold(ranked[1][1].name)
        if top >= 88 and (top - second >= 6 or same):
            return "click", ranked[0][1]
        if self.brain is not None and self.brain.ready.is_set() and self.brain.agent is not None:
            short = [e for s, e in ranked[:8] if s >= 35] or [e for _, e in ranked[:8]]
            got = self.brain.pick_element(name, [(e.id, e.label()) for e in short])
            if got and got[1] >= 0.6:
                return "click", by_id[got[0]]
        if top >= 75 and top - second >= 10:
            return "click", ranked[0][1]
        choices = [e for s, e in ranked[:4] if s >= 50]
        if not choices:
            return "none", None
        if len(choices) == 1 and top >= 70:
            return "click", choices[0]
        return "choose", choices

    def click(self, name=None, ordinal=None, kind=None, double=False, confirmed=False, el_id=None):
        """-> (status, El|list) where status is clicked / choose / confirm / none."""
        self.front()
        if el_id:
            els = {e.id: e for e in self.snapshot()}
            el = els.get(el_id)
            if el is None:
                return "none", None
            self._click_id(el.id, double)
            return "clicked", el
        status, found = self.resolve(name, ordinal, kind)
        if status == "choose":
            self.candidates = [e.id for e in found]
            self.page().evaluate("(ids) => window.__vm.badges(ids)", self.candidates)
            return "choose", found
        if status == "none":
            return "none", None
        el = found
        if not confirmed and DESTRUCTIVE.search(el.name or ""):
            return "confirm", el
        self.clear_badges()
        self._click_id(el.id, double)
        return "clicked", el

    def pick(self, n: int):
        if not self.candidates or not (1 <= n <= len(self.candidates) or n == -1):
            return "none", None
        el_id = self.candidates[-1 if n == -1 else n - 1]
        els = {e.id: e for e in self.snapshot()}
        self.clear_badges()
        el = els.get(el_id)
        if el is None:
            return "none", None
        if DESTRUCTIVE.search(el.name or ""):
            return "confirm", el
        self._click_id(el_id)
        return "clicked", el

    def fill(self, field: str, text: str):
        self.front()
        els = [e for e in self.snapshot() if e.role in ("textbox", "searchbox", "combobox")]
        if not els:
            return None
        if "search" in fold(field) or fold(field) in ("box", "input", "field", "khana"):
            pref = [e for e in els if e.search] or els
            el = sorted(pref, key=lambda e: (not e.inView, e.top))[0]
        else:
            ranked = sorted(els, key=lambda e: -score(field, e))
            el = ranked[0]
        self.highlight(el.id)
        loc = self.page().locator(f'[data-vm-id="{el.id}"]').first
        loc.click(timeout=4000)
        loc.fill(text, timeout=4000)
        return el

    def type_here(self, text: str):
        self.front().keyboard.type(text, delay=5)

    def press(self, key: str):
        self.front().keyboard.press(key)

    def scroll(self, direction: str, amount: str):
        p = self._js()
        p.evaluate("([d, a]) => window.__vm.scroll(d, a)", [direction, amount])
