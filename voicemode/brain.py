"""Laya: the local decision model, used where rules are not enough.

Measured zero-shot on 33 spoken commands, `laya-multilingual` picked the right one of 12 intent
groups 25 times (76%), sometimes wrong with high confidence. So it is not the main parser:

  * classify(): fallback for final transcripts the rules could not read, two small questions
    (group, then the concrete action) with a confidence gate. Slots still come from code.
  * pick_element(): choose which of a few page elements a phrase means ("cart me daal do" ->
    "Add to cart"), where plain string matching fails. 7/9 right in our test.

It loads in the background (10-20 s on CPU); until then everything runs on rules alone.
"""
from __future__ import annotations

import logging
import threading

from .parser import (CLICK_POST, CLICK_PRE, OPEN_POST, OPEN_PRE, SEARCH_POST, SEARCH_PRE, TAIL,
                     TYPE_POST, TYPE_PRE, Command, _object, _open_command, resolve_target)
from .text import span_text, tokenize, words

log = logging.getLogger("voicemode")

GROUPS = {
    "open_website": "open or go to a website",
    "web_search": "search the internet for something",
    "click": "click a link or button on the page",
    "scroll": "scroll the page up or down",
    "navigate_history": "go back, go forward or reload the page",
    "tabs": "open, close or switch browser tabs",
    "type_text": "type or write some text",
    "open_app": "open a computer application",
    "volume_media": "change the volume or control music and video playback",
    "window": "minimize, maximize, close or switch windows",
    "power": "shut down, restart, sleep or lock the computer",
    "none": "not a command, just talking to someone",
}

FINE = {
    "scroll": {"scroll_down": "move the page down", "scroll_up": "move the page up",
               "scroll_top": "go to the very top of the page", "scroll_bottom": "go to the very end of the page"},
    "navigate_history": {"back": "go back to the previous page", "forward": "go forward to the next page",
                         "reload": "reload or refresh the page"},
    "tabs": {"new_tab": "open a new tab", "close_tab": "close the current tab",
             "next_tab": "switch to the next tab", "previous_tab": "switch to the previous tab"},
    "volume_media": {"volume_up": "make the sound louder", "volume_down": "make the sound quieter",
                     "mute": "turn the sound off", "play_pause": "play or pause the music or video",
                     "next_track": "skip to the next song", "previous_track": "go to the previous song"},
    "window": {"minimize": "minimize the window", "maximize": "maximize the window",
               "close_window": "close the window", "switch_window": "switch to another window",
               "show_desktop": "show the desktop"},
    "power": {"shutdown": "shut down the computer", "restart": "restart the computer",
              "sleep": "put the computer to sleep", "lock": "lock the screen"},
}

FINE_TO_CMD = {
    "scroll_down": ("scroll", {"direction": "down", "amount": "page"}),
    "scroll_up": ("scroll", {"direction": "up", "amount": "page"}),
    "scroll_top": ("scroll", {"direction": "up", "amount": "end"}),
    "scroll_bottom": ("scroll", {"direction": "down", "amount": "end"}),
    "back": ("back", {}), "forward": ("forward", {}), "reload": ("reload", {}),
    "new_tab": ("new_tab", {}), "close_tab": ("close_tab", {}), "next_tab": ("next_tab", {}),
    "previous_tab": ("prev_tab", {}),
    "volume_up": ("volume", {"change": 5}), "volume_down": ("volume", {"change": -5}),
    "mute": ("volume", {"mute": True}), "play_pause": ("media", {"action": "play_pause"}),
    "next_track": ("media", {"action": "next"}), "previous_track": ("media", {"action": "previous"}),
    "minimize": ("window", {"action": "minimize"}), "maximize": ("window", {"action": "maximize"}),
    "close_window": ("window", {"action": "close"}), "switch_window": ("window", {"action": "switch"}),
    "show_desktop": ("window", {"action": "show_desktop"}),
    "shutdown": ("power", {"action": "shutdown"}), "restart": ("power", {"action": "restart"}),
    "sleep": ("power", {"action": "sleep"}), "lock": ("power", {"action": "lock"}),
}

_VERBS = set()
for _ph in (OPEN_PRE | OPEN_POST | SEARCH_PRE | SEARCH_POST | CLICK_PRE | CLICK_POST | TYPE_PRE | TYPE_POST):
    _VERBS.update(_ph)
_DROP = _VERBS | TAIL | words("please", "zara", "jara", "bhai", "yaar", "button", "link", "website", "app")


class Brain:
    def __init__(self, model_dir: str, subfolder: str = "multilingual", min_confidence: float = 0.75):
        self.model_dir = model_dir
        self.subfolder = subfolder
        self.min_confidence = min_confidence
        self.agent = None
        self.error: str | None = None
        self.ready = threading.Event()
        self._lock = threading.Lock()

    def load_async(self) -> None:
        threading.Thread(target=self._load, name="laya-load", daemon=True).start()

    def _load(self) -> None:
        try:
            import laya
            self.agent = laya.load(self.model_dir, subfolder=self.subfolder)
            self.agent.predict({"command": "open notepad"},
                               {"w": {"type": "noul", "instructions": "warm up"}})
            log.info("Laya loaded (%s)", self.subfolder)
        except Exception as e:
            self.error = str(e)
            log.warning("Laya not available, running on rules only: %s", e)
        finally:
            self.ready.set()

    def _ask(self, state: dict, questions: dict) -> dict:
        with self._lock:
            return self.agent.predict(state, questions)["answers"]

    # ------------------------------------------------------------ intent fallback
    def classify(self, text: str) -> Command | None:
        if self.agent is None:
            return None
        state = {"command": text}
        a = self._ask(state, {"g": {"type": "choice", "instructions": "What does the user want the computer to do?",
                                    "criteria": GROUPS}})["g"]
        group, conf = a["choice"], a["confidence"]
        log.info("laya group %s %.2f for %r", group, conf, text)
        if group == "none" or conf < self.min_confidence:
            return None
        toks = tokenize(text)
        obj = _object([t for t in toks if t.c not in _DROP])
        if group in FINE:
            f = self._ask(state, {"f": {"type": "choice", "instructions": "Which exact action?",
                                        "criteria": FINE[group]}})["f"]
            if f["confidence"] < 0.5:
                return None
            intent, args = FINE_TO_CMD[f["choice"]]
            cmd = Command(intent, dict(args), text, source="laya")
            cmd.destructive = intent == "power" and args["action"] != "lock"
            return cmd
        if not obj:
            return None
        phrase = span_text(text, obj)
        if group in ("open_website", "open_app"):
            res = resolve_target(obj, text)
            cmd = _open_command(res, text, verb_final=False)
        elif group == "web_search":
            cmd = Command("search", {"query": phrase, "site": None}, text, free_text=True)
        elif group == "click":
            cmd = Command("click", {"name": phrase, "kind": None}, text)
        elif group == "type_text":
            cmd = Command("type_text", {"text": phrase}, text, free_text=True)
        else:
            return None
        cmd.source = "laya"
        return cmd

    # ------------------------------------------------------------ element choice
    def pick_element(self, phrase: str, candidates: list[tuple[str, str]]) -> tuple[str, float] | None:
        """candidates: [(id, "button: Add to cart"), ...] (keep it to <= 8). Returns (id, confidence)."""
        if self.agent is None or not candidates:
            return None
        crit = {cid: label[:80] for cid, label in candidates}
        a = self._ask({"command": phrase},
                      {"t": {"type": "choice", "instructions": "Which element on the page does the user mean?",
                             "criteria": crit}})["t"]
        return a["choice"], a["confidence"]
