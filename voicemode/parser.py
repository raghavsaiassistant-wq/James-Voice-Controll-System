"""Rule-based command parser for English, Hindi (Roman script) and Hinglish.

`parse(text)` splits a transcript into commands ("youtube kholo aur lofi search karo" -> two
commands) and turns each into a `Command(intent, args)`. It is deterministic and runs in
microseconds, so it can be re-run on every partial transcript while the user is still talking.

Word order: English is verb-first ("open youtube"), Hinglish is usually verb-last
("youtube kholo"). A command whose verb came last is `verb_final`: its object is already
complete, so the controller may act on it before the user finishes the sentence.

Anything this parser cannot read is left to the Laya fallback (brain.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import catalog
from .text import (S, Token, canon_phrase, is_ordinal, number_of, phrases, span_text, tokenize,
                   words)


@dataclass
class Command:
    intent: str
    args: dict = field(default_factory=dict)
    text: str = ""
    verb_final: bool = False     # object delimited by a trailing verb ("youtube kholo")
    free_text: bool = False      # carries dictated text / a query copied from speech
    bare: bool = False           # just a name ("youtube") with no verb: act only on final
    destructive: bool = False
    source: str = "rules"

    def signature(self) -> tuple:
        return (self.intent, tuple(sorted((k, str(v)) for k, v in self.args.items())))

    def describe(self) -> str:
        a = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        return f"{self.intent}({a})"


# Intents with no free-form object: safe to run as soon as they are heard.
CLOSED = {
    "scroll", "back", "forward", "reload", "new_tab", "close_tab", "next_tab", "prev_tab",
    "goto_tab", "reopen_tab", "volume", "media", "brightness", "window", "keys", "screenshot",
    "confirm", "cancel", "pick", "power", "open_settings", "open_folder", "open_browser",
    "close_browser",
}


def safe_on_partial(cmd: Command) -> bool:
    return cmd.intent in CLOSED or (cmd.verb_final and not cmd.bare)


# ---------------------------------------------------------------- lexicons

WAKE = words("james", "jarvis", "hey", "assistant")
LEAD_FILLERS = words("please", "plz", "pls", "zara", "jara", "bhai", "yaar", "yar", "ok", "okay",
                     "so", "now", "abhi", "ab", "just", "um", "uh", "hmm", "achha", "acha")
LEAD_PHRASES = phrases("can you", "could you", "would you", "will you", "i want to", "i want you to",
                       "i would like to", "mujhe", "meko", "mere liye", "for me")
TAIL = words("karo", "kro", "kar", "kardo", "kariye", "kijiye", "kijie", "karein", "karen", "karna",
             "karde", "de", "do", "dijiye", "dena", "dijie", "lo", "le", "lijiye", "na", "please",
             "plz", "pls", "abhi", "jaldi", "zara", "bhai", "yaar", "yar", "ji", "now", "quickly",
             "sir", "for", "me", "mere", "liye", "dena", "hai", "chahiye", "chaiye")
ARTICLES = words("the", "a", "an", "this", "that", "ye", "yeh", "vo", "voh", "wo", "woh", "is",
                 "us", "isko", "usko", "ise", "use", "it", "my", "mera", "meri", "mere", "apna")
POSTP = words("pe", "par", "per", "me", "mein", "main", "mai", "mei", "ko", "ke", "ki", "ka",
              "se", "on", "in", "into", "at", "to", "onto", "tak")
CONJ = words("and", "then", "aur", "fir", "phir", "also")
CONJ_PHRASES = phrases("and then", "uske baad", "iske baad", "us ke baad", "after that", "fir se")
VERB_END = words("kholo", "kholiye", "khol", "karo", "kro", "kardo", "kijiye", "jao", "chalo", "dabao",
                 "chalao", "lagao", "bajao", "badhao", "ghatao", "likho", "dikhao", "lo", "do", "hatao",
                 "roko", "chuno", "sunao", "badlo", "dijiye", "lijiye", "kariye", "karein")

OPEN_PRE = phrases("open", "launch", "start", "run", "go to", "goto", "visit", "take me to",
                   "navigate to", "bring up", "show me", "show", "load", "kholo", "khol do", "khol",
                   "open up", "fire up")
OPEN_POST = phrases("kholo", "kholiye", "khol do", "khol de", "khol dijiye", "kholna", "khol",
                    "open karo", "open kar do", "open kardo", "open kijiye", "open", "open kr do",
                    "chalu karo", "chalu kar do", "start karo", "start kar do", "launch karo",
                    "pe jao", "par jao", "pe chalo", "par chalo", "pe le chalo", "par le chalo",
                    "jao", "chalao", "chala do", "dikhao", "open karna", "kholna hai")
SWITCH_PRE = phrases("switch to", "go back to", "focus", "bring", "activate")
SWITCH_POST = phrases("pe switch karo", "par switch karo", "pe switch kar do", "switch karo",
                      "pe wapas jao", "par wapas jao", "pe vapas jao")
CLOSE_PRE = phrases("close", "quit", "exit", "shut", "kill", "band karo")
CLOSE_POST = phrases("band karo", "band kar do", "band kardo", "band kijiye", "bandh karo",
                     "close karo", "close kar do", "close", "hatao", "band", "exit karo", "quit karo")
CLICK_PRE = phrases("click on", "click", "tap on", "tap", "press on", "press", "select", "choose",
                    "hit", "double click", "double click on")
CLICK_POST = phrases("pe click karo", "par click karo", "per click karo", "ko click karo", "click karo",
                     "pe click kar do", "par click kar do", "click kar do", "pe click", "par click",
                     "pe tap karo", "par tap karo", "tap karo", "dabao", "ko dabao", "daba do",
                     "press karo", "select karo", "select kar do", "chuno", "choose karo")
SEARCH_PRE = phrases("search for", "search", "search about", "google", "look up", "lookup", "find",
                     "find me", "search karo", "dhundo", "dhoondo", "dhoondho", "khojo")
SEARCH_POST = phrases("search karo", "search kar do", "search kardo", "search kijiye", "search",
                      "dhundo", "dhoondo", "dhoondho", "dhund do", "dhoondh do", "khojo", "google karo",
                      "search karna", "search karke dikhao", "search kar ke dikhao", "dhund ke dikhao")
PLAY_PRE = phrases("play", "play me", "put on", "chalao", "lagao", "bajao", "suna do", "sunao")
PLAY_POST = phrases("chalao", "chala do", "lagao", "laga do", "bajao", "baja do", "play karo",
                    "play kar do", "play", "sunao", "suna do")
TYPE_PRE = phrases("type", "write", "type in", "enter text", "likho", "likh do", "type karo", "dictate")
TYPE_POST = phrases("likho", "likh do", "likh dijiye", "likhiye", "likh", "type karo", "type kar do",
                    "type kardo", "type kijiye", "type")
ABOUT_TAIL = phrases("ke bare me", "ke bare mein", "ke baare me", "ke baare mein", "ke bare main",
                     "ke baare main", "about", "ke liye", "ki info", "ki jankari")

MEDIA_NOUNS = words("song", "songs", "gana", "gaana", "gaane", "gane", "music", "track", "video",
                    "videos", "audio", "movie", "film", "podcast")
RESULT_KINDS = {**{w: "result" for w in words("result", "results", "search result")},
                **{w: "link" for w in words("link", "links")},
                **{w: "video" for w in words("video", "videos")},
                **{w: "button" for w in words("button", "buttons", "batan")},
                **{w: "image" for w in words("image", "images", "photo", "picture", "tasveer")},
                **{w: "item" for w in words("item", "option", "product", "article", "post", "one",
                                            "wala", "vala", "wali", "vali", "wale", "vale")}}
FIELD_NOUNS = words("box", "field", "bar", "textbox", "input", "searchbox", "searchbar", "column",
                    "khana")
PC = words("computer", "laptop", "pc", "system", "windows", "machine", "desktop")


def _starts(toks: list[Token], options: set[tuple[str, ...]]) -> int:
    """Length of the longest phrase in `options` that starts `toks`, else 0."""
    best = 0
    for p in options:
        n = len(p)
        if n > best and len(toks) >= n and tuple(t.c for t in toks[:n]) == p:
            best = n
    return best


def _ends(toks: list[Token], options: set[tuple[str, ...]]) -> int:
    best = 0
    for p in options:
        n = len(p)
        if n > best and len(toks) >= n and tuple(t.c for t in toks[-n:]) == p:
            best = n
    return best


def _has(toks: list[Token], vocab: set[str]) -> bool:
    return any(t.c in vocab for t in toks)


def _strip(toks: list[Token], lead: set[str] = frozenset(), tail: set[str] = frozenset()) -> list[Token]:
    i, j = 0, len(toks)
    while i < j and toks[i].c in lead:
        i += 1
    while j > i and toks[j - 1].c in tail:
        j -= 1
    return toks[i:j]


HINDI_POSTP = words("pe", "par", "per", "me", "mein", "mai", "mei", "ko", "ke", "ki", "ka", "se", "tak")
_WALA = words("wala", "wali", "wale", "vala", "vali", "vale")


def _object(toks: list[Token]) -> list[Token]:
    """Drop articles / postpositions / politeness at both ends of an object phrase.

    English prepositions are only dropped at the front: "sign in" and "log on" keep their tail.
    """
    lead = ARTICLES | POSTP | TAIL | LEAD_FILLERS | _WALA
    tail = ARTICLES | HINDI_POSTP | TAIL | LEAD_FILLERS | _WALA
    return _strip(toks, lead, tail)


def _covered(toks: list[Token], vocab: set[str]) -> bool:
    return all(t.c in vocab for t in toks)


# ---------------------------------------------------------------- object resolution

def _lookup(toks: list[Token], table: dict):
    key = tuple(t.c for t in toks)
    return table.get(key)


def spoken_url(toks: list[Token], text: str) -> str | None:
    """"example dot com", "example.com", "news dot ycombinator dot com" -> URL."""
    raw = [t.raw.lower() for t in toks]
    s = " ".join(raw)
    s = re.sub(r"\s*\b(dot|daat|dat|point)\b\s*", ".", s)
    s = s.replace(" ", "")
    if re.fullmatch(r"(https?://)?[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|in|org|net|io|dev|ai|co|edu|gov|app|me|tv|info|co\.in|uk|us)(/\S*)?", s):
        return s if s.startswith("http") else "https://" + s
    return None


def resolve_target(toks: list[Token], text: str) -> dict | None:
    """Map an object phrase to what it names. Unknown names come back as `thing`."""
    obj = _object(toks)
    if not obj:
        return None
    key = tuple(t.c for t in obj)
    # "youtube website", "notepad app"
    trimmed = obj
    if len(obj) > 1 and obj[-1].c in words("website", "site", "app", "application", "program",
                                           "software", "page", "dot com", "wala", "vala"):
        trimmed = obj[:-1]
    tkey = tuple(t.c for t in trimmed)
    if key in catalog.BROWSER_BY_NAME or tkey in catalog.BROWSER_BY_NAME:
        return {"kind": "browser"}
    if tkey in (canon_phrase("new tab"), canon_phrase("naya tab"), canon_phrase("nayi tab"),
                canon_phrase("ek naya tab"), canon_phrase("another tab"), canon_phrase("new tab page"),
                canon_phrase("naya page"), canon_phrase("new page"), canon_phrase("blank page")):
        return {"kind": "new_tab"}
    for table, kind in ((catalog.SETTINGS_BY_NAME, "settings"), (catalog.FOLDER_BY_NAME, "folder")):
        hit = table.get(key) or table.get(tkey)
        if hit:
            return {"kind": kind, "key": hit[0], "target": hit[1]}
    site = catalog.SITE_BY_NAME.get(key) or catalog.SITE_BY_NAME.get(tkey)
    if site:
        return {"kind": "site", "site": site.key, "url": site.url}
    app = catalog.APP_BY_NAME.get(key) or catalog.APP_BY_NAME.get(tkey)
    if app:
        return {"kind": "app", "app": app.key}
    url = spoken_url(obj, text)
    if url:
        return {"kind": "url", "url": url}
    if key and key[-1] in (canon_phrase("settings") + canon_phrase("setting")):
        return {"kind": "settings", "key": "home", "target": "ms-settings:"}
    return {"kind": "thing", "name": span_text(text, trimmed)}


def _open_command(res: dict, seg_text: str, verb_final: bool, bare: bool = False) -> Command:
    kind = res["kind"]
    if kind == "browser":
        return Command("open_browser", {}, seg_text, verb_final, bare=bare)
    if kind == "new_tab":
        return Command("new_tab", {}, seg_text, verb_final)
    if kind == "settings":
        return Command("open_settings", {"page": res["key"], "target": res["target"]}, seg_text, verb_final)
    if kind == "folder":
        return Command("open_folder", {"folder": res["key"], "target": res["target"]}, seg_text, verb_final)
    if kind == "site":
        return Command("open_site", {"site": res["site"], "url": res["url"]}, seg_text, verb_final, bare=bare)
    if kind == "url":
        return Command("open_site", {"url": res["url"]}, seg_text, verb_final, bare=bare)
    if kind == "app":
        return Command("open_app", {"app": res["app"]}, seg_text, verb_final, bare=bare)
    return Command("open_thing", {"name": res["name"]}, seg_text, verb_final, bare=bare)


# ---------------------------------------------------------------- individual parsers
# Each takes the (edge-stripped) tokens of one segment plus the transcript text and returns a
# Command or None. They run in order; the first match wins.

CONFIRM = phrases("confirm", "yes", "yeah", "yep", "yup", "haan", "han", "ha", "haanji", "hanji",
                  "ha ji", "haan ji", "ok", "okay", "sure", "go ahead", "kar do", "haan kar do",
                  "do it", "theek hai", "thik hai", "confirm karo", "yes confirm", "haan confirm",
                  "bilkul", "haan bhai", "yes please", "chalega")
CANCEL = phrases("cancel", "no", "nahi", "nahin", "na", "mat karo", "rehne do", "rahne do", "chhodo",
                 "chodo", "never mind", "nevermind", "abort", "kuch nahi", "cancel karo", "nahi karna",
                 "no cancel", "mat kar", "ruko mat karo", "stop it", "nako")


def p_confirm(toks, text):
    key = tuple(t.c for t in toks)
    if key in CONFIRM:
        return Command("confirm", {}, text)
    if key in CANCEL:
        return Command("cancel", {}, text)
    return None


PICK_FILL = words("number", "no", "option", "wala", "vala", "wali", "vali", "wale", "vale", "vaala",
                  "select", "click", "pe", "par", "karo", "choose", "the", "one", "chuno", "dabao")


def p_pick(toks, text):
    nums = [number_of(t, allow_do=True) for t in toks]
    idx = [i for i, n in enumerate(nums) if n is not None]
    if len(idx) != 1:
        return None
    rest = [t for i, t in enumerate(toks) if i != idx[0]]
    if not _covered(rest, PICK_FILL):
        return None
    return Command("pick", {"n": nums[idx[0]]}, text)


def p_power(toks, text):
    ws = [t.c for t in toks]
    core = [t for t in toks if t.c not in TAIL | ARTICLES | PC | words("mode", "now", "abhi", "screen", "my")]
    cs = " ".join(t.c for t in core)
    has_pc = _has(toks, PC)
    if cs in S("shutdown", "shut down", "power of", "switch of", "turn of") or \
            (has_pc and cs in S("band", "of", "switch of", "turn of", "shutdown", "shut down", "power of")):
        return Command("power", {"action": "shutdown"}, text, destructive=True)
    if cs in S("restart", "reboot", "restart kar", "dobara start") or (has_pc and cs in S("restart", "reboot")):
        return Command("power", {"action": "restart"}, text, destructive=True)
    if cs in S("sleep", "sula", "so ja", "sleep me dal", "sleep pe dal", "put to sleep", "put sleep",
               "go to sleep", "sleep kar") and (has_pc or canon_phrase("sleep")[0] in ws):
        return Command("power", {"action": "sleep"}, text, destructive=True)
    if cs in S("lock", "lock kar") or (cs == "lock" and has_pc):
        return Command("power", {"action": "lock"}, text)
    if cs in S("sign out", "signout", "log out", "logout", "log of", "logof"):
        return Command("power", {"action": "signout"}, text, destructive=True)
    return None


VOL = words("volume", "awaaz", "awaz", "aawaz", "avaaz", "sound", "voice", "speaker")
BRIGHT = words("brightness", "brightnes", "roshni", "brightness level")
UP = words("up", "upar", "uppar", "bada", "badha", "badhao", "badao", "badhana", "increase", "raise",
           "zyada", "jyada", "tez", "tej", "loud", "louder", "high", "higher", "more", "bright", "brighter")
DOWN = words("down", "neeche", "niche", "neche", "kam", "kum", "ghatao", "ghata", "decrease", "lower",
             "reduce", "dheere", "dhima", "dhimi", "low", "halka", "halki", "less", "dim", "quieter", "soft")
MUTE = words("mute", "chup", "silent", "silence", "khamosh")
UNMUTE = words("unmute", "chalu", "on", "wapas", "vapas")
OFF = words("band", "bandh", "off")
FULL = words("full", "max", "maximum", "poora", "pura", "hundred")
LITTLE = words("thoda", "thodi", "bit", "little", "slightly", "halka", "sa", "si", "zara")
LOT = words("bahut", "bohot", "lot", "much", "zyada", "jyada", "kaafi", "kafi")
LEVEL_FILL = words("percent", "par", "pe", "to", "at", "set", "level", "tak", "karo", "kar", "do",
                   "the", "per", "cent", "%")


def _level(toks):
    for t in toks:
        n = number_of(t)
        if n is not None and 0 <= n <= 100 and not is_ordinal(t):
            return n
    return None


def p_volume(toks, text):
    if not (_has(toks, VOL) or _has(toks, BRIGHT)):
        return None
    what = "brightness" if _has(toks, BRIGHT) else "volume"
    rest = [t for t in toks if t.c not in VOL | BRIGHT]
    lvl = _level(rest)
    if lvl is not None:
        return Command(what, {"set": lvl}, text)
    if _has(rest, FULL):
        return Command(what, {"set": 100}, text)
    if what == "volume":
        if _has(rest, words("unmute")) or (_has(rest, UNMUTE) and not _has(rest, OFF)):
            return Command("volume", {"mute": False}, text)
        if _has(rest, MUTE) or _has(rest, OFF):
            return Command("volume", {"mute": True}, text)
    steps = 2 if _has(rest, LITTLE) else 10 if _has(rest, LOT - words("zyada", "jyada")) else 5
    if _has(rest, DOWN):
        return Command(what, {"change": -steps}, text)
    if _has(rest, UP) or _has(rest, LOT):
        return Command(what, {"change": steps}, text)
    return None


MEDIA_VOCAB = MEDIA_NOUNS | TAIL | ARTICLES | words("the", "this", "current", "abhi", "wala", "vala")
PLAY_VERBS = words("lagao", "chalao", "bajao", "play", "sunao", "chala", "laga", "baja", "suna")


def p_media(toks, text):
    ws = {t.c for t in toks}
    core = [t for t in toks if t.c not in MEDIA_VOCAB]
    cs = " ".join(t.c for t in core)
    if cs in S("mute",):
        return Command("volume", {"mute": True}, text)
    if cs in S("unmute",):
        return Command("volume", {"mute": False}, text)
    nav = " ".join(t.c for t in core if t.c not in PLAY_VERBS)
    if nav in S("next", "agla", "agle", "skip", "next one", "agla vala") and (ws & MEDIA_NOUNS or cs == "skip"):
        return Command("media", {"action": "next"}, text)
    if nav in S("previous", "prev", "pichla", "pichle", "last") and ws & MEDIA_NOUNS:
        return Command("media", {"action": "previous"}, text)
    if cs in S("pause", "resume", "play pause", "play", "ruko", "roko", "rok", "stop", "band", "chalu",
              "chalao", "lagao", "bajao", "play kar", "fir se chalao", "vapas chalao") and \
            (ws & MEDIA_NOUNS or cs in S("pause", "resume", "play pause", "play")):
        return Command("media", {"action": "play_pause"}, text)
    return None


TAB = words("tab", "tabs", "taab")


def p_tabs(toks, text):
    if not _has(toks, TAB):
        return None
    if _has(toks, words("press", "dabao", "key")):
        return None
    rest = [t for t in toks if t.c not in TAB | TAIL | ARTICLES | POSTP | words("jao", "chalo", "go")]
    rs = " ".join(t.c for t in rest)
    if _has(rest, words("new", "naya", "nayi", "nai", "another", "ek")) or rs in S("open", "kholo", "khol", "add"):
        return Command("new_tab", {}, text)
    if _has(rest, words("reopen", "restore")) or rs in S("band hua vapas", "closed vapas lao"):
        return Command("reopen_tab", {}, text)
    if _has(rest, words("close", "band", "bandh", "hatao", "remove", "rid")):
        return Command("close_tab", {}, text)
    if _has(rest, words("next", "agla", "agle", "agli", "right", "aage")):
        return Command("next_tab", {}, text)
    if _has(rest, words("previous", "prev", "pichla", "pichle", "pichli", "left", "back")):
        return Command("prev_tab", {}, text)
    n = next((number_of(t, allow_do=True) for t in rest if number_of(t, allow_do=True) is not None), None)
    if n is not None and _covered(rest, words("open", "kholo", "switch", "number", "no") |
                                  {t.c for t in rest if number_of(t, allow_do=True) is not None}):
        return Command("goto_tab", {"n": n}, text)
    return None


HIST_FILL = TAIL | ARTICLES | POSTP | words("go", "jao", "chalo", "le", "lo", "page", "ek", "one", "take", "me",
                                             "step", "karo", "ja", "chale", "jaye", "jaiye")


def p_history(toks, text):
    core = [t for t in toks if t.c not in HIST_FILL]
    cs = " ".join(t.c for t in core)
    if cs in S("back", "vapas", "piche", "previous", "pichla", "pichle", "vapis", "go back", "back previous",
              "previous page", "piche vapas", "back button", "vapas piche"):
        return Command("back", {}, text)
    if cs in S("forward", "age", "aage", "next page age", "forward button"):
        return Command("forward", {}, text)
    if cs in S("reload", "refresh", "dobara load", "fir se load", "reload kar", "refresh kar",
              "dobara refresh", "hard refresh"):
        return Command("reload", {}, text)
    return None


SCROLL_WORD = words("scroll", "scrol", "scrolling")
S_DOWN = words("down", "neeche", "niche", "neche", "nichai")
S_UP = words("up", "upar", "uppar", "upr")
S_END = words("bottom", "end", "last", "aakhir", "akhir")
S_TOP = words("top", "shuru", "start", "beginning", "starting")
S_ALL = words("sabse", "all", "way", "bilkul", "ekdam", "puri", "pura")
S_SMALL = words("thoda", "thodi", "bit", "little", "slightly", "halka", "sa", "zara", "jara")
S_PAGE = words("page", "screen", "ek", "one", "full")
SCROLL_VOCAB = SCROLL_WORD | S_DOWN | S_UP | S_END | S_TOP | S_ALL | S_SMALL | S_PAGE | TAIL | \
    ARTICLES | POSTP | words("go", "jao", "chalo", "le", "and", "aur", "more", "further", "of", "the",
                             "side", "taraf", "ki", "kar", "karo", "please", "abhi", "wapas", "vapas",
                             "hi", "bhi", "and", "then", "karte", "raho", "rakho", "move")


def p_scroll(toks, text):
    ws = {t.c for t in toks}
    if not (ws & (SCROLL_WORD | S_DOWN | S_UP | S_END | S_TOP)):
        return None
    if not _covered(toks, SCROLL_VOCAB):
        return None
    # "top" / "end" alone need a scroll word or "sabse"/"go"/"jao" to count
    if not (ws & (SCROLL_WORD | S_DOWN | S_UP)) and not (ws & (S_ALL | words("go", "jao", "chalo", "tak"))):
        return None
    if ws & S_END or (ws & S_ALL and ws & S_DOWN):
        return Command("scroll", {"direction": "down", "amount": "end"}, text)
    if ws & S_TOP or (ws & S_ALL and ws & S_UP):
        return Command("scroll", {"direction": "up", "amount": "end"}, text)
    direction = "up" if ws & S_UP and not ws & S_DOWN else "down"
    amount = "small" if ws & S_SMALL else "page"
    return Command("scroll", {"direction": direction, "amount": amount}, text)


WINDOW = words("window", "windows", "screen", "app", "application", "program")
WIN_FILL = WINDOW | TAIL | ARTICLES | POSTP | words("current", "abhi", "vali", "wali", "vala", "wala",
                                                     "all", "sab", "sabhi", "saari", "sari", "sare", "saare")


def p_window(toks, text):
    ws = {t.c for t in toks}
    fs = " ".join(t.c for t in toks if t.c not in TAIL | ARTICLES)
    if fs in S("full screen", "fullscreen", "full screen mode", "exit full screen", "full screen band",
               "full screen se bahar", "full screen hatao"):
        return Command("keys", {"combo": "f11"}, text)
    core = [t for t in toks if t.c not in WIN_FILL]
    cs = " ".join(t.c for t in core)
    if cs in S("minimize", "minimise", "chota", "choti", "minimize kar", "hide", "chupa", "chupao",
              "niche kar"):
        if ws & words("all", "sab", "sabhi", "saari", "sari", "sare", "saare"):
            return Command("window", {"action": "show_desktop"}, text)
        if cs in S("hide", "chupa", "chupao", "niche kar") and not ws & WINDOW:
            return None
        return Command("window", {"action": "minimize"}, text)
    if cs in S("maximize", "maximise", "bada", "badi", "maximize kar", "full size"):
        return Command("window", {"action": "maximize"}, text)
    if cs in S("restore", "normal", "restore down"):
        return Command("window", {"action": "restore"}, text)
    if cs in S("switch", "next", "change", "badlo", "dusri", "dusra", "agli", "alt tab", "other",
              "switch kar", "change kar") and (ws & WINDOW or cs == "alt tab"):
        return Command("window", {"action": "switch"}, text)
    if cs in S("show desktop", "desktop dikhao", "desktop", "go to desktop", "desktop dikha",
              "desktop pe", "desktop par") and "folder" not in ws and \
            (cs != "desktop" or ws & words("dikhao", "jao", "go", "show", "dikha")):
        return Command("window", {"action": "show_desktop"}, text)
    if cs in S("snap left", "left", "left side", "left me", "baye", "left taraf") and ws & WINDOW:
        return Command("window", {"action": "snap_left"}, text)
    if cs in S("snap right", "right", "right side", "right me", "daye", "right taraf") and ws & WINDOW:
        return Command("window", {"action": "snap_right"}, text)
    if cs in S("close", "band", "bandh", "close kar", "band kar", "hatao", "exit", "quit") and ws & WINDOW:
        return Command("window", {"action": "close"}, text)
    return None


KEY_NAMES = {
    **{w: "enter" for w in words("enter", "return", "enter key", "inter")},
    **{w: "esc" for w in words("escape", "esc", "escape key")},
    **{w: "tab" for w in words("tab")},
    **{w: "space" for w in words("space", "spacebar", "space bar")},
    **{w: "backspace" for w in words("backspace", "back space")},
    **{w: "delete" for w in words("delete", "del")},
    **{w: "home" for w in words("home")},
    **{w: "end" for w in words("end")},
    **{w: "up" for w in words("up", "up arrow", "arrow up", "upar")},
    **{w: "down" for w in words("down", "down arrow", "arrow down", "neeche")},
    **{w: "left" for w in words("left", "left arrow", "arrow left")},
    **{w: "right" for w in words("right", "right arrow", "arrow right")},
    **{w: "page_up" for w in words("page up", "pageup")},
    **{w: "page_down" for w in words("page down", "pagedown")},
    **{w: "win" for w in words("windows key", "windows", "start button", "win")},
}
MODS = {**{w: "ctrl" for w in words("control", "ctrl", "ctl", "cntrl")},
        **{w: "shift" for w in words("shift")}, **{w: "alt" for w in words("alt")},
        **{w: "win" for w in words("win", "windows", "window")}}
SHORTCUTS = {
    **{p: "ctrl+c" for p in phrases("copy", "copy kar", "copy this", "copy it", "copy kar lo", "copy karo")},
    **{p: "ctrl+v" for p in phrases("paste", "paste kar", "paste it", "paste here", "yaha paste", "paste karo")},
    **{p: "ctrl+x" for p in phrases("cut", "cut kar", "cut it", "cut karo")},
    **{p: "ctrl+z" for p in phrases("undo", "undo kar", "undo that", "undo karo")},
    **{p: "ctrl+y" for p in phrases("redo", "redo kar", "redo karo")},
    **{p: "ctrl+a" for p in phrases("select all", "sab select", "sab kuch select", "sab select kar",
                                     "select everything", "sab chuno", "pura select", "sab kuch select kar")},
    **{p: "ctrl+s" for p in phrases("save", "save kar", "save it", "save this", "save file", "save karo",
                                     "file save", "save kar lo")},
    **{p: "ctrl+p" for p in phrases("print", "print kar", "print karo", "print this")},
    **{p: "ctrl+plus" for p in phrases("zoom in", "zoom badhao", "zoom", "bada dikhao", "zoom karo")},
    **{p: "ctrl+minus" for p in phrases("zoom out", "zoom kam", "chota dikhao", "zoom kam kar")},
    **{p: "ctrl+0" for p in phrases("reset zoom", "zoom reset", "normal zoom", "zoom normal")},
    **{p: "ctrl+f" for p in phrases("find on page", "find in page", "page me dhundo")},
    **{p: "enter" for p in phrases("enter", "enter dabao", "enter kar", "hit enter", "press enter",
                                    "submit kar", "enter key", "ok enter")},
    **{p: "ctrl+shift+t" for p in phrases("reopen closed tab", "reopen tab", "band tab vapas", "undo close tab")},
}
PRESS = phrases("press", "hit", "dabao", "daba do", "press karo", "type key", "key dabao", "button dabao")
SHOT = phrases("screenshot", "screen shot", "screenshot lo", "screenshot le lo", "take a screenshot",
               "take screenshot", "screenshot le", "screenshot kar", "screenshot karo", "capture screen",
               "screen capture", "ss lo", "screenshot lelo")


def _combo(toks) -> str | None:
    """"control shift t" / "alt f4" / "ctrl c" / "enter" -> "ctrl+shift+t" etc."""
    mods, keys = [], []
    i = 0
    while i < len(toks):
        two = " ".join(t.c for t in toks[i:i + 2])
        if len(toks) - i >= 2 and two in KEY_NAMES:
            keys.append(KEY_NAMES[two]); i += 2; continue
        c = toks[i].c
        if c in MODS and (keys == [] and (i + 1 < len(toks))):
            mods.append(MODS[c])
        elif c in KEY_NAMES:
            keys.append(KEY_NAMES[c])
        elif re.fullmatch(r"f([1-9]|1[0-2])", c):
            keys.append(c)
        elif len(toks[i].raw) == 1 and toks[i].raw.isalnum():
            keys.append(toks[i].raw.lower())
        elif c in words("key", "button", "the", "ko", "plus", "and", "karo", "kar", "do"):
            pass
        else:
            return None
        i += 1
    if len(keys) != 1:
        return None
    return "+".join(dict.fromkeys(mods + keys))


def p_keys(toks, text):
    key = tuple(t.c for t in _strip(toks, ARTICLES, TAIL | ARTICLES))
    if key in SHOT:
        return Command("screenshot", {}, text)
    if key in SHORTCUTS:
        return Command("keys", {"combo": SHORTCUTS[key]}, text)
    n = _starts(toks, PRESS)
    body = toks[n:] if n else toks
    if not n:
        m = _ends(toks, PRESS)
        if not m:
            # bare combos with a modifier ("control c", "alt f4") are unambiguous
            if toks and toks[0].c in MODS and len(toks) >= 2 and toks[0].c not in words("windows", "window"):
                combo = _combo(toks)
                if combo:
                    return Command("keys", {"combo": combo}, text)
            return None
        body = toks[:-m]
    body = _strip(body, ARTICLES | POSTP, ARTICLES | POSTP | TAIL | words("key", "button"))
    combo = _combo(body) if body else None
    if combo:
        return Command("keys", {"combo": combo}, text)
    return None


def p_type(toks, text):
    n = _starts(toks, TYPE_PRE)
    field_toks: list[Token] = []
    app_key = None
    if n:
        body = toks[n:]
        # "... in the search box" / "... into the name field"
        for i in range(len(body) - 1, 0, -1):
            if body[i].c in words("in", "into", "inside", "on"):
                tail = _object(body[i + 1:])
                if any(t.c in FIELD_NOUNS for t in tail):
                    field_toks = tail
                elif _lookup(tail, catalog.APP_BY_NAME):
                    app_key = _lookup(tail, catalog.APP_BY_NAME).key
                else:
                    continue
                body = body[:i]
                break
        verb_final = False
    else:
        m = _ends(toks, TYPE_POST)
        if not m:
            return None
        body = toks[:-m]
        # "search box me hello likho"
        for i, t in enumerate(body[:-1]):
            if t.c in words("me", "mein", "main", "mai", "pe", "par", "in"):
                head = _object(body[:i])
                if any(x.c in FIELD_NOUNS for x in head):
                    field_toks = head
                elif head and _lookup(head, catalog.APP_BY_NAME) and i <= 3:
                    app_key = _lookup(head, catalog.APP_BY_NAME).key
                else:
                    continue
                body = body[i + 1:]
                break
        verb_final = True
    body = _strip(body, words("that", "ki", "ke", "yeh", "ye", "this"), words("please", "plz"))
    if not body:
        return None
    payload = span_text(text, body)
    payload = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", payload).strip()
    if payload.endswith(".") and not payload.endswith(".."):
        payload = payload[:-1]
    args = {"text": payload}
    if field_toks:
        args["field"] = span_text(text, field_toks)
    if app_key:
        args["app"] = app_key
    return Command("type_text", args, text, verb_final=verb_final, free_text=True)


def _split_site(body: list[Token], text: str, leading: bool):
    """Pull a site out of "... on youtube" (English) or "youtube pe ..." (Hinglish)."""
    if not leading:
        for i in range(len(body) - 1, 0, -1):
            if body[i].c in words("on", "in", "at", "from", "using", "via", "pe", "par", "me"):
                name = _object(body[i + 1:])
                site = catalog.SITE_BY_NAME.get(tuple(t.c for t in name))
                if site and site.search:
                    return site.key, body[:i]
    else:
        for i in range(1, min(len(body), 4)):
            if body[i].c in words("pe", "par", "per", "me", "mein", "main", "mai", "on"):
                site = catalog.SITE_BY_NAME.get(tuple(t.c for t in body[:i]))
                if site and site.search:
                    return site.key, body[i + 1:]
    return None, body


def p_search(toks, text):
    if _ends(toks, SEARCH_POST):
        return _search_post(toks, text)
    # English / verb-first: "search youtube for lofi", "search for alan turing on wikipedia"
    n = _starts(toks, SEARCH_PRE)
    if n and toks[0].c == canon_phrase("google")[0] and (len(toks) == n or toks[n].c in POSTP or
                                       _covered(toks[n:], TAIL | words("kholo", "khol", "open", "jao",
                                                                        "chalo", "pe", "par"))):
        return None     # "google kholo" / "google pe ..." are not a search for "kholo"
    if n:
        body = toks[n:]
        site = None
        for i in range(1, min(len(body), 4)):
            if body[i].c == "for":
                s = catalog.SITE_BY_NAME.get(tuple(t.c for t in body[:i]))
                if s and s.search:
                    site, body = s.key, body[i + 1:]
                    break
        if not site:
            site, body = _split_site(body, text, leading=False)
        if not site:
            s2, b2 = _split_site(body, text, leading=True)
            if s2:
                site, body = s2, b2
        body = _strip(body, words("for", "about", "the") | ARTICLES, TAIL)
        m = _ends(body, ABOUT_TAIL)
        if m:
            body = body[:-m]
        if not body:
            return None
        return Command("search", {"query": span_text(text, body), "site": site}, text, free_text=True)
    return None


def _search_post(toks, text):
    m = _ends(toks, SEARCH_POST)
    body = toks[:-m]
    n = _starts(body, SEARCH_PRE - phrases("google"))
    if n:                    # "search karo alan turing search karo" -> drop the leading verb too
        body = body[n:]
    site, body = _split_site(body, text, leading=True)
    if not site:
        site, body = _split_site(body, text, leading=False)
    a = _ends(body, ABOUT_TAIL)
    if a:
        body = body[:-a]
    body = _strip(body, ARTICLES | POSTP, POSTP)
    if not body:
        return None
    return Command("search", {"query": span_text(text, body), "site": site}, text,
                   verb_final=True, free_text=True)


def p_play(toks, text):
    n = _starts(toks, PLAY_PRE)
    verb_final = False
    if n:
        body = toks[n:]
        site, body = _split_site(body, text, leading=False)
    else:
        m = _ends(toks, PLAY_POST)
        if not m:
            return None
        body = toks[:-m]
        verb_final = True
        site, body = _split_site(body, text, leading=True)
        if not site:
            site, body = _split_site(body, text, leading=False)
    body = _object(body)
    if not body:
        return Command("media", {"action": "play_pause"}, text)
    if _covered(body, MEDIA_NOUNS | ARTICLES | words("koi", "some", "kuch", "a", "the", "ek", "achha",
                                                      "acha", "vala", "wala")):
        if not _has(body, words("koi", "some", "kuch", "ek")):
            return Command("media", {"action": "play_pause"}, text)
    res = resolve_target(body, text)
    if res and res["kind"] in ("app", "site", "browser") and not site:
        # "spotify chalao" -> open the app, not a search for "spotify"
        return _open_command(res, text, verb_final)
    return Command("play", {"query": span_text(text, body), "site": site or "youtube"}, text,
                   verb_final=verb_final, free_text=True)


def _click_target(body: list[Token], text: str) -> dict | None:
    body = _object(body)
    if not body:
        return None
    ords = [(i, number_of(t, allow_do=False)) for i, t in enumerate(body)
            if is_ordinal(t) or (t.raw.isdigit() and len(body) > 1)]
    kinds = [RESULT_KINDS[t.c] for t in body if t.c in RESULT_KINDS]
    if ords:
        i, n = ords[0]
        rest = [t for j, t in enumerate(body) if j != i]
        if _covered(rest, set(RESULT_KINDS) | ARTICLES | POSTP | words("number", "no", "search", "wala",
                                                                        "vala", "on", "page")):
            return {"ordinal": n, "kind": kinds[0] if kinds else None}
    kind = None
    if body and body[-1].c in RESULT_KINDS and len(body) > 1:
        kind = RESULT_KINDS[body[-1].c]
        body = _object(body[:-1])
    if not body:
        return None
    return {"name": span_text(text, body), "kind": kind}


def p_click(toks, text):
    n = _starts(toks, CLICK_PRE)
    if n:
        tgt = _click_target(toks[n:], text)
        if tgt:
            if toks[0].c == "double":
                tgt["double"] = True
            return Command("click", tgt, text)
        return None
    m = _ends(toks, CLICK_POST)
    if m:
        tgt = _click_target(toks[:-m], text)
        if tgt:
            return Command("click", tgt, text, verb_final=True)
    return None


def p_close(toks, text):
    n = _starts(toks, CLOSE_PRE)
    verb_final = False
    if n:
        body = toks[n:]
    else:
        m = _ends(toks, CLOSE_POST)
        if not m:
            return None
        body = toks[:-m]
        verb_final = True
    obj = _object(body)
    if not obj or _covered(obj, words("this", "it", "ye", "yeh", "isko", "ise", "sab", "window", "app",
                                      "current", "abhi", "vala", "wala")):
        return Command("window", {"action": "close"}, text, verb_final=verb_final)
    res = resolve_target(obj, text)
    if res["kind"] == "browser":
        return Command("close_browser", {}, text, verb_final=verb_final)
    if res["kind"] == "app":
        return Command("close_app", {"app": res["app"]}, text, verb_final=verb_final)
    if res["kind"] == "site":
        return Command("close_tab", {"site": res["site"]}, text, verb_final=verb_final)
    if res["kind"] == "thing":
        return Command("close_app", {"name": res["name"]}, text, verb_final=verb_final)
    return None


def p_switch(toks, text):
    n = _starts(toks, SWITCH_PRE)
    if n:
        body, vf = toks[n:], False
    else:
        m = _ends(toks, SWITCH_POST)
        if not m:
            return None
        body, vf = toks[:-m], True
    obj = _object(body)
    if not obj:
        return None
    res = resolve_target(obj, text)
    if res["kind"] == "app":
        return Command("switch_app", {"app": res["app"]}, text, verb_final=vf)
    if res["kind"] == "thing":
        return Command("switch_app", {"name": res["name"]}, text, verb_final=vf)
    return _open_command(res, text, vf)


def p_open(toks, text):
    n = _starts(toks, OPEN_PRE)
    if n:
        body, vf = toks[n:], False
    else:
        m = _ends(toks, OPEN_POST)
        if not m:
            return None
        body, vf = toks[:-m], True
    if not body:
        return None
    # "doosra result kholo" / "open the first link" -> click
    tgt = _click_target(body, text)
    if tgt and "ordinal" in tgt:
        return Command("click", tgt, text, verb_final=vf)
    res = resolve_target(body, text)
    if res is None:
        return None
    if res["kind"] == "thing" and tgt and tgt.get("kind") in ("link", "button", "result", "video", "image"):
        return Command("click", tgt, text, verb_final=vf)
    return _open_command(res, text, vf)


def p_bare(toks, text):
    res = resolve_target(toks, text)
    if res and res["kind"] in ("site", "app", "browser", "url", "settings", "folder"):
        return _open_command(res, text, verb_final=False, bare=True)
    return None


PARSERS = [p_confirm, p_pick, p_power, p_volume, p_media, p_tabs, p_history, p_scroll, p_window,
           p_keys, p_type, p_search, p_play, p_click, p_close, p_switch, p_open, p_bare]


def _clean_edges(toks: list[Token]) -> list[Token]:
    changed = True
    while changed and toks:
        changed = False
        if toks[0].c in WAKE | LEAD_FILLERS | CONJ and len(toks) > 1:
            toks = toks[1:]; changed = True
            continue
        n = _starts(toks, LEAD_PHRASES)
        if n and len(toks) > n:
            toks = toks[n:]; changed = True
            continue
        if len(toks) > 1 and toks[-1].c in words("please", "plz", "pls", "bhai", "yaar", "yar", "ji",
                                                  "na", "jaldi", "abhi", "now", "quickly", "thanks",
                                                  "thank", "you", "zara", "sir"):
            if toks[-1].c == "you" and len(toks) > 1 and toks[-2].c != "thank":
                break
            toks = toks[:-1]; changed = True
    return toks


def parse_segment(toks: list[Token], text: str) -> Command | None:
    toks = _clean_edges(toks)
    if not toks:
        return None
    seg_text = span_text(text, toks)
    for p in PARSERS:
        cmd = p(toks, text)
        if cmd:
            cmd.text = seg_text
            return cmd
    return None


# ---------------------------------------------------------------- segmentation

_EN_START = words("open", "search", "click", "type", "scroll", "go", "play", "close", "press", "launch",
                  "start", "switch", "volume", "mute", "take", "tap", "select", "write", "find", "show")


def _conj_len(toks: list[Token], i: int) -> int:
    for p in CONJ_PHRASES:
        if tuple(t.c for t in toks[i:i + len(p)]) == p:
            if p == canon_phrase("fir se") and (i + 2 < len(toks) and toks[i + 2].c in
                                                 words("load", "chalao", "start", "karo")):
                return 0
            return len(p)
    if toks[i].c in CONJ:
        if toks[i].c == canon_phrase("tab")[0]:
            return 0      # "tab" is also a browser tab
        return 1
    return 0


def _split_verbs(toks: list[Token], text: str) -> list[tuple[list[Token], Command]] | None:
    """Split one conjunction-free run into consecutive commands, or None if it doesn't parse."""
    whole = parse_segment(toks, text)
    n = len(toks)
    for i in range(1, n):
        left, right = toks[:i], toks[i:]
        boundary = left[-1].c in VERB_END or right[0].c in _EN_START
        if not boundary:
            continue
        lc = parse_segment(left, text)
        if not lc:
            continue
        if right[0].c in _EN_START and left[-1].c not in VERB_END and \
                (lc.free_text or lc.intent in ("open_thing",)):
            continue            # "search for how to open a file" stays one search
        if whole and whole.intent == lc.intent:
            continue            # "neeche scroll karo" is one scroll, not two
        rest = _split_verbs(right, text)
        if rest:
            if whole and whole.intent != "open_thing" and len(rest) == 1 and rest[0][1].intent in (
                    "open_thing", "pick") and not left[-1].c in VERB_END:
                continue
            return [(left, lc)] + rest
    if whole:
        return [(toks, whole)]
    return None


def parse(text: str) -> list[Command]:
    """All commands in a transcript, in order. Unparseable pieces become `unknown` commands."""
    toks = tokenize(text)
    if not toks:
        return []
    # split on conjunctions, then merge pieces that don't parse on their own
    pieces: list[list[Token]] = []
    cur: list[Token] = []
    i = 0
    while i < len(toks):
        k = _conj_len(toks, i)
        if k and cur:
            pieces.append(cur)
            cur = []
            pieces.append(toks[i:i + k])      # keep the conjunction as its own marker piece
            i += k
            continue
        cur.append(toks[i])
        i += 1
    if cur:
        pieces.append(cur)
    segs: list[list[Token]] = []
    j = 0
    while j < len(pieces):
        p = pieces[j]
        if j + 1 < len(pieces) and _conj_len(pieces[j + 1], 0) and j + 2 < len(pieces):
            left_ok = _split_verbs(p, text) is not None
            right_ok = _split_verbs(pieces[j + 2], text) is not None
            if left_ok and right_ok:
                segs.append(p)
                j += 2
                continue
            # merge p + conj + next and re-examine
            pieces[j + 2] = p + pieces[j + 1] + pieces[j + 2]
            j += 2
            continue
        segs.append(p)
        j += 1
    out: list[Command] = []
    for s in segs:
        split = _split_verbs(s, text)
        if split:
            out.extend(c for _, c in split)
        elif all(t.c in CONJ | LEAD_FILLERS | TAIL | WAKE for t in s):
            continue                   # a dangling "aur" / "please" while the user is mid-sentence
        else:
            out.append(Command("unknown", {}, span_text(text, s)))
    return out
