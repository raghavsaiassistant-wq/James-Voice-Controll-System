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
NAMES.update({"youtube": "YouTube", "github": "GitHub", "linkedin": "LinkedIn", "chatgpt": "ChatGPT",
              "whatsapp": "WhatsApp", "gmail": "Gmail", "duckduckgo": "DuckDuckGo"})
APP_NAMES = {a.key: a.names[0].title() for a in catalog.APPS}
APP_NAMES.update({"vscode": "VS Code", "cmd": "Command Prompt", "taskmgr": "Task Manager",
                  "powershell": "PowerShell"})


class Executor:
    def __init__(self, settings, system, browser, brain=None):
        self.settings = settings
        self.system = system
        self.browser = browser
        self.brain = brain
        self._opened: tuple[str, float] | None = None     # (app key, when) of the last app we opened

    def _wait_for_opened_app(self):
        """"notepad kholo aur hello likho": give the app time to come up before typing into it."""
        if self._opened and time.time() - self._opened[1] < 10:
            self.system.wait_foreground(key=self._opened[0], timeout=6)
        self._opened = None

    def execute(self, cmd: Command, confirmed: bool = False) -> Result:
        fn = getattr(self, "do_" + cmd.intent, None)
        if fn is None:
            return Result(False, f"Ye abhi support nahi hai: {cmd.intent}")
        return fn(cmd, confirmed) if cmd.intent in ("click", "pick") else fn(cmd)

    # ------------------------------------------------------------ browser
    def do_open_site(self, c: Command) -> Result:
        site = catalog.SITE_BY_KEY.get(c.args.get("site", ""))
        if site and site.app and self.system.has_app(site.app):
            self.system.open_app(name=site.app)
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
            self.system.type_text(text)
            return Result(True, f"{APP_NAMES.get(app, app)} me likh diya: “{text}”")
        if field and self.browser.running:
            el = self.browser.fill(field, text)
            if el is not None:
                return Result(True, f"Likh diya: “{text}”")
        if self.system.real:
            self._wait_for_opened_app()
            self.system.type_text(text)
        elif self.browser.running:
            self.browser.type_here(text)
        else:
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
        name = self.system.open_app(key=key)
        if not name:
            return Result(False, f"{APP_NAMES.get(key, key)} is computer pe nahi mila")
        self._opened = (key, time.time())
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
            return Result(True, f"{app['Name']} khol diya")
        site = self.browser.search(name, None)
        return Result(True, f"“{name}” app nahi mila — {NAMES.get(site, site)} pe search kiya")

    def do_close_app(self, c: Command) -> Result:
        n = self.system.close_app(key=c.args.get("app"), name=c.args.get("name"))
        label = APP_NAMES.get(c.args.get("app"), c.args.get("name"))
        return Result(bool(n), f"{label} band kiya" if n else f"{label} khula nahi mila")

    def do_switch_app(self, c: Command) -> Result:
        ok = self.system.switch_app(key=c.args.get("app"), name=c.args.get("name"))
        label = APP_NAMES.get(c.args.get("app"), c.args.get("name"))
        if not ok and c.args.get("app"):
            return self.do_open_app(Command("open_app", {"app": c.args["app"]}, c.text))
        return Result(bool(ok), f"{label} pe switch" if ok else f"{label} khula nahi mila")

    def do_open_folder(self, c):
        self.system.shell_open(c.args["target"])
        return Result(True, f"{c.args['folder'].title()} folder khola")

    def do_open_settings(self, c):
        self.system.shell_open(c.args["target"])
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
            if self.system.real:
                self._wait_for_opened_app()
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

    def do_screenshot(self, c):
        self.system.screenshot()
        return Result(True, "Screenshot le liya (Pictures › Screenshots)")

    def do_power(self, c):
        action = c.args["action"]
        self.system.power(action)
        return Result(True, {"lock": "Lock kar diya", "shutdown": "5 second me shutdown",
                             "restart": "5 second me restart", "sleep": "Sleep", "signout": "Sign out"}[action])
