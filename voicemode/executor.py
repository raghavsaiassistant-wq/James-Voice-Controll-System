"""Runs one parsed Command against the browser or the operating system."""
from __future__ import annotations

import logging
import time
from urllib.parse import quote

from . import catalog
from .controller import Result
from .parser import Command

log = logging.getLogger("voicemode")

NAMES = {s.key: s.names[0].title() for s in catalog.SITES}
NAMES.update({"twitter": "X", "youtube": "YouTube", "github": "GitHub", "linkedin": "LinkedIn", "chatgpt": "ChatGPT",
              "whatsapp": "WhatsApp", "gmail": "Gmail", "duckduckgo": "DuckDuckGo"})
APP_NAMES = {a.key: a.names[0].title() for a in catalog.APPS}
APP_NAMES.update({"vscode": "VS Code", "cmd": "Command Prompt", "taskmgr": "Task Manager",
                  "powershell": "PowerShell", "notes": "Sticky Notes"})

BROWSER_INTENTS = {"open_site", "open_browser", "search", "play", "click", "pick", "back", "forward", "reload",
                   "new_tab", "close_tab", "next_tab", "prev_tab", "goto_tab", "reopen_tab"}
# Commands that act on "whatever is in front": they go to the last opened app/tab when that
# happened in the same breath, or when said as a follow-up ("usme", "once you're there").
FOLLOW_UP = {"type_text", "keys", "new_item", "take_photo", "scroll"}
NEW_LABEL = {"note": "Nayi note", "file": "Nayi file", "folder": "Naya folder", "window": "Nayi window"}


class Executor:
    def __init__(self, settings, system, browser, brain=None):
        self.settings = settings
        self.system = system
        self.browser = browser
        self.brain = brain
        self.utt = 0                  # utterance counter (one per key press)
        self.ctx: dict | None = None  # last thing we opened: {"kind": "app"|"browser", "key", "name", "t", "utt"}

    # ------------------------------------------------------------ context
    def begin_utterance(self):
        self.utt += 1

    def _set_ctx(self, kind: str, key: str | None = None, name: str | None = None, fresh: bool = True):
        self.ctx = {"kind": kind, "key": key, "name": name, "t": time.time() if fresh else 0.0, "utt": self.utt}

    def _ctx_applies(self, cmd: Command) -> bool:
        return self.ctx is not None and (cmd.context or self.ctx["utt"] == self.utt)

    def _focus_ctx(self, cmd: Command) -> None:
        if not self._ctx_applies(cmd):
            return
        if self.ctx["kind"] == "app":
            self.system.wait_foreground(key=self.ctx["key"], name=self.ctx["name"], timeout=6)
        elif self.ctx["kind"] == "browser" and self.browser.running:
            self.browser.front()

    def _pause(self, seconds: float):
        if self.system.real and seconds > 0:
            time.sleep(seconds)

    def execute(self, cmd: Command, confirmed: bool = False) -> Result:
        fn = getattr(self, "do_" + cmd.intent, None)
        if fn is None:
            return Result(False, f"Ye abhi support nahi hai: {cmd.intent}")
        if cmd.intent in FOLLOW_UP and not cmd.args.get("app") and not cmd.args.get("field") \
                and cmd.intent != "take_photo":
            self._focus_ctx(cmd)
        res = fn(cmd, confirmed) if cmd.intent in ("click", "pick") else fn(cmd)
        if res.ok and cmd.intent in BROWSER_INTENTS and not (self.ctx and self.ctx.get("via_app")):
            self._set_ctx("browser")
        if self.ctx:
            self.ctx.pop("via_app", None)
        return res

    # ------------------------------------------------------------ browser
    def do_open_site(self, c: Command) -> Result:
        site = catalog.SITE_BY_KEY.get(c.args.get("site", ""))
        if site and site.app and self.system.has_app(site.app):
            self.system.open_app(name=site.app)
            self._set_ctx("app", name=site.app)
            self.ctx["via_app"] = True
            return Result(True, f"{site.app} app khol diya")
        title = self.browser.open(c.args["url"])
        return Result(True, f"{NAMES.get(site.key, title) if site else title} khol diya")

    def do_open_browser(self, c: Command) -> Result:
        self.browser.front()
        return Result(True, "Browser khol diya")

    def do_close_browser(self, c: Command) -> Result:
        self.browser.close()
        return Result(True, "Browser band kar diya")

    def do_search(self, c: Command) -> Result:
        q = c.args["query"]
        site = self.browser.search(q, c.args.get("site"))
        return Result(True, f"{NAMES.get(site, site)} pe search: “{q}”")

    def do_play(self, c: Command) -> Result:
        q, site = c.args["query"], c.args.get("site") or "youtube"
        if site == "spotify" and self.system.has_app("Spotify"):
            self.system.shell_open("spotify:search:" + quote(q))
            return Result(True, f"Spotify pe “{q}”")
        title = self.browser.play_youtube(q)
        return Result(True, f"YouTube pe chala diya: {title or q}")

    def do_click(self, c: Command, confirmed: bool = False) -> Result:
        a = c.args
        status, found = self.browser.click(name=a.get("name"), ordinal=a.get("ordinal"), kind=a.get("kind"),
                                           double=a.get("double", False), confirmed=confirmed,
                                           el_id=a.get("el_id"))
        return self._click_result(status, found, c)

    def _click_result(self, status, found, c: Command) -> Result:
        if status == "clicked":
            return Result(True, f"Click: {found.name[:60]}")
        if status == "choose":
            names = " · ".join(f"{i + 1}) {e.name[:30]}" for i, e in enumerate(found))
            return Result(True, f"Kaunsa? Number bolo — {names}", pending=("pick", len(found)))
        if status == "confirm":
            again = Command("click", {"el_id": found.id}, c.text)
            return Result(True, f"“{found.name[:50]}” — ye important hai. 'confirm' ya 'cancel' bolo",
                          pending=("confirm", again))
        what = c.args.get("name") or (f"result #{c.args.get('ordinal')}" if c.args.get("ordinal") else "")
        return Result(False, f"Page pe “{what}” nahi mila")

    def do_pick(self, c: Command, confirmed: bool = False) -> Result:
        status, found = self.browser.pick(c.args["n"])
        return self._click_result(status, found, c)

    def do_type_text(self, c: Command) -> Result:
        text, field, app = c.args["text"], c.args.get("field"), c.args.get("app")
        if app:
            if not self.system.open_app(key=app) or not self.system.wait_foreground(key=app, timeout=6):
                return Result(False, f"{APP_NAMES.get(app, app)} tak nahi pahunch paya")
            self._set_ctx("app", key=app)
            if c.args.get("new_item"):
                self._new_item(c.args["new_item"])
            self.system.type_text(text)
            return Result(True, f"{APP_NAMES.get(app, app)} me likh diya: “{text}”")
        if c.args.get("new_item"):
            self._new_item(c.args["new_item"])
        if field and self.browser.running:
            el = self.browser.fill(field, text)
            if el is not None:
                return Result(True, f"Likh diya: “{text}”")
        self.system.type_text(text)
        return Result(True, f"Likh diya: “{text}”")

    def do_scroll(self, c: Command) -> Result:
        d, amt = c.args["direction"], c.args["amount"]
        if self.browser.is_foreground():
            self.browser.scroll(d, amt)
        else:
            self.system.scroll(d, amt)
        label = {"down": "neeche", "up": "upar"}[d]
        return Result(True, f"Scroll {label}" + (" (end tak)" if amt == "end" else ""))

    def do_back(self, c):
        self.browser.back()
        return Result(True, "Peeche gaye")

    def do_forward(self, c):
        self.browser.forward()
        return Result(True, "Aage gaye")

    def do_reload(self, c):
        self.browser.reload()
        return Result(True, "Page reload")

    def do_new_tab(self, c):
        self.browser.new_tab()
        return Result(True, "Naya tab")

    def do_close_tab(self, c):
        ok = self.browser.close_tab(c.args.get("site"))
        if not ok and c.args.get("site"):
            return Result(False, f"{NAMES.get(c.args['site'])} ka koi tab khula nahi hai")
        return Result(ok, "Tab band kiya" if ok else "Koi tab khula nahi hai")

    def do_next_tab(self, c):
        return Result(True, f"Tab {self.browser.switch_tab(+1)}")

    def do_prev_tab(self, c):
        return Result(True, f"Tab {self.browser.switch_tab(-1)}")

    def do_goto_tab(self, c):
        return Result(True, f"Tab {self.browser.switch_tab(n=c.args['n'])}")

    def do_reopen_tab(self, c):
        self.system.press("ctrl+shift+t") if self.system.real else self.browser.press("Control+Shift+T")
        return Result(True, "Band tab wapas khola")

    # ------------------------------------------------------------ apps & files
    def do_open_app(self, c: Command) -> Result:
        key = c.args["app"]
        was_open = self.system.is_running(key=key)
        name = self.system.open_app(key=key)
        if not name:
            return Result(False, f"{APP_NAMES.get(key, key)} is computer pe nahi mila")
        used = getattr(self.system, "resolved_key", None) or key
        self._set_ctx("app", key=used, fresh=not was_open)
        if used != key:
            return Result(True, f"{APP_NAMES.get(key, key)} nahi mila — {APP_NAMES.get(used, name)} khol diya")
        return Result(True, f"{APP_NAMES.get(key, name)} khol diya")

    def do_open_thing(self, c: Command) -> Result:
        """An unlisted name: page element -> installed app -> web search."""
        name = c.args["name"]
        if self.browser.is_foreground():
            status, found = self.browser.resolve(name, None, None)
            if status == "click":
                return self.do_click(Command("click", {"name": name}, c.text))
        app = self.system.find_start_app(name)
        if app:
            self.system.open_app(name=name)
            self._set_ctx("app", name=app["Name"])
            return Result(True, f"{app['Name']} khol diya")
        return Result(False, f"“{name}” nahi mila — web pe dhundhna ho to “{name} search karo” bolo")

    def do_close_app(self, c: Command) -> Result:
        n = self.system.close_app(key=c.args.get("app"), name=c.args.get("name"))
        label = APP_NAMES.get(c.args.get("app"), c.args.get("name"))
        return Result(bool(n), f"{label} band kiya" if n else f"{label} khula nahi mila")

    def do_switch_app(self, c: Command) -> Result:
        ok = self.system.switch_app(key=c.args.get("app"), name=c.args.get("name"))
        label = APP_NAMES.get(c.args.get("app"), c.args.get("name"))
        if not ok and c.args.get("app"):
            return self.do_open_app(Command("open_app", {"app": c.args["app"]}, c.text))
        if ok:
            self._set_ctx("app", key=c.args.get("app"), name=c.args.get("name"), fresh=False)
        return Result(bool(ok), f"{label} pe switch" if ok else f"{label} khula nahi mila")

    def do_open_folder(self, c):
        self.system.shell_open(c.args["target"])
        self._set_ctx("app", key="explorer")
        return Result(True, f"{c.args['folder'].title()} folder khola")

    def do_open_settings(self, c):
        self.system.shell_open(c.args["target"])
        self._set_ctx("app", name="Settings")
        return Result(True, "Settings khol di" if c.args["page"] == "home" else f"{c.args['page'].title()} settings")

    # ------------------------------------------------------------ system
    def do_volume(self, c):
        a = c.args
        lvl = self.system.volume(change=a.get("change"), set=a.get("set"), mute=a.get("mute"))
        if a.get("mute") is True:
            return Result(True, "Mute")
        if a.get("mute") is False:
            return Result(True, "Unmute" + (f" — {lvl}%" if lvl is not None else ""))
        if lvl is not None:
            return Result(True, f"Volume {lvl}%")
        return Result(True, "Volume " + ("badhaya" if (a.get("change") or 0) > 0 else "kam kiya"))

    def do_brightness(self, c):
        lvl = self.system.brightness(change=c.args.get("change"), set=c.args.get("set"))
        return Result(True, f"Brightness {lvl}%" if lvl is not None else "Brightness badli")

    def do_media(self, c):
        self.system.media(c.args["action"])
        return Result(True, {"play_pause": "Play/Pause", "next": "Agla track", "previous": "Pichla track"}[c.args["action"]])

    def do_window(self, c):
        action = c.args["action"]
        if action == "close" and self.browser.is_foreground():
            self.browser.close_tab()
            return Result(True, "Tab band kiya")
        self.system.window(action)
        return Result(True, {"minimize": "Minimize", "maximize": "Maximize", "restore": "Restore",
                             "close": "Window band", "switch": "Window switch", "show_desktop": "Desktop",
                             "snap_left": "Left side", "snap_right": "Right side"}.get(action, action))

    def do_keys(self, c):
        combo = c.args["combo"]
        if self.system.real or not self.browser.running:
            self.system.press(combo)
        else:
            pw = {"ctrl": "Control", "shift": "Shift", "alt": "Alt", "win": "Meta", "enter": "Enter",
                  "esc": "Escape", "tab": "Tab", "space": " ", "backspace": "Backspace", "delete": "Delete",
                  "page_up": "PageUp", "page_down": "PageDown", "up": "ArrowUp", "down": "ArrowDown",
                  "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End",
                  "plus": "=", "minus": "-"}
            self.browser.press("+".join(pw.get(k, k.upper() if k.startswith("f") and k[1:].isdigit() else k)
                                        for k in combo.split("+")))
        return Result(True, f"Key: {combo}")

    # ------------------------------------------------------------ new things / camera
    def _new_item(self, what: str) -> str:
        """Ctrl+N in the app in front (Notepad: new tab, Sticky Notes: new note, Word: new doc);
        in the browser a new tab; a folder in Explorer is Ctrl+Shift+N."""
        in_browser = (self.ctx is not None and self.ctx["kind"] == "browser" and self.ctx["utt"] == self.utt) \
            or (self.browser.is_foreground() and not (self.ctx and self.ctx["kind"] == "app"
                                                      and self.ctx["utt"] == self.utt))
        if in_browser and what != "folder":
            self.browser.new_tab()
            return "Naya tab"
        self.system.press("ctrl+shift+n" if what == "folder" else "ctrl+n")
        self._pause(0.6)
        return NEW_LABEL.get(what, "Naya item")

    def do_new_item(self, c):
        return Result(True, self._new_item(c.args["what"]) + " bana di")

    def do_take_photo(self, c):
        """Camera app: open (or focus) it, give it time to start the webcam, press the shutter."""
        warm = getattr(self.settings, "camera_warmup", 2.5)
        if not (self.ctx and self.ctx["kind"] == "app" and self.ctx["key"] == "camera"):
            was_open = self.system.is_running(key="camera")
            if not was_open and not self.system.open_app(key="camera"):
                return Result(False, "Camera app nahi mila")
            if was_open:
                self.system.switch_app(key="camera")
            self._set_ctx("app", key="camera", fresh=not was_open)
        if not self.system.wait_foreground(key="camera", timeout=8):
            return Result(False, "Camera app saamne nahi aaya")
        self._pause(warm - (time.time() - self.ctx["t"]))
        self.system.press("space")                  # Windows Camera: Space / Enter = take photo
        return Result(True, "Photo le li 📸 (Pictures › Camera Roll)")

    def do_screenshot(self, c):
        self.system.screenshot()
        return Result(True, "Screenshot le liya (Pictures › Screenshots)")

    def do_power(self, c):
        action = c.args["action"]
        self.system.power(action)
        return Result(True, {"lock": "Lock kar diya", "shutdown": "5 second me shutdown",
                             "restart": "5 second me restart", "sleep": "Sleep", "signout": "Sign out"}[action])
