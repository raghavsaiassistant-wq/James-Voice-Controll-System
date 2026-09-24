"""Whole-computer actions on Windows: apps, windows, keys, volume, brightness, power.

Uses plain Win32 calls (ctypes) plus pynput for keystrokes, so nothing needs admin rights.
`DryRunSystem` records calls instead of performing them (tests, and non-Windows machines).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from rapidfuzz import fuzz

from .. import catalog
from ..text import canon_phrase

log = logging.getLogger("voicemode")
IS_WINDOWS = sys.platform == "win32"


@dataclass
class Win:
    hwnd: int
    title: str
    exe: str


def fold(s: str) -> str:
    return " ".join(canon_phrase(s))


def _match(name: str, candidates: list[str], cutoff: float = 80) -> int | None:
    q = fold(name)
    best, best_i = 0.0, None
    for i, c in enumerate(candidates):
        f = fold(c)
        s = max(fuzz.ratio(q, f), fuzz.token_set_ratio(q, f) - (5 if len(f.split()) > len(q.split()) + 2 else 0))
        if f.startswith(q) and len(q) >= 3:
            s = max(s, 90)
        if s > best:
            best, best_i = s, i
    return best_i if best >= cutoff else None


def parse_combo(combo: str) -> list[str]:
    return [k for k in combo.lower().split("+") if k] if combo != "ctrl+plus" else ["ctrl", "="]


class DryRunSystem:
    """Logs what would happen. Used in tests and when not on Windows."""
    real = False

    def __init__(self):
        self.calls: list[tuple] = []
        self.start_apps: list[dict] = []

    def _rec(self, *a):
        self.calls.append(a)
        log.info("[dry-run] %s", a)
        return True

    def warm(self): ...
    def foreground(self): return None
    def focus_title(self, title): return self._rec("focus_title", title)
    def open_app(self, key=None, name=None): return self._rec("open_app", key or name) and (key or name)
    def find_start_app(self, name): return None
    def has_app(self, name): return False
    def close_app(self, key=None, name=None): return self._rec("close_app", key or name) and 1
    def switch_app(self, key=None, name=None): return self._rec("switch_app", key or name)
    def wait_foreground(self, key=None, name=None, timeout=5.0): return True
    def shell_open(self, target): return self._rec("shell_open", target)
    def type_text(self, text): return self._rec("type_text", text)
    def press(self, combo): return self._rec("press", combo)
    def scroll(self, direction, amount): return self._rec("scroll", direction, amount)
    def volume(self, change=None, set=None, mute=None): self._rec("volume", change, set, mute); return None
    def brightness(self, change=None, set=None): self._rec("brightness", change, set); return None
    def media(self, action): return self._rec("media", action)
    def window(self, action): return self._rec("window", action)
    def screenshot(self): return self._rec("screenshot")
    def power(self, action): return self._rec("power", action)


class WindowsSystem:
    real = True

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        from pynput.keyboard import Controller, Key
        from pynput.mouse import Controller as Mouse
        self.ct, self.wt = ctypes, wt
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kb, self.Key, self.mouse = Controller(), Key, Mouse()
        self.start_apps: list[dict] = []
        self._apps_lock = threading.Lock()
        self._overlay_hwnds: set[int] = set()
        self.user32.GetForegroundWindow.restype = wt.HWND
        self.user32.GetWindowTextLengthW.argtypes = [wt.HWND]
        self.user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        self.user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        self.user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        self.user32.SetForegroundWindow.argtypes = [wt.HWND]
        self.user32.BringWindowToTop.argtypes = [wt.HWND]
        self.user32.IsIconic.argtypes = [wt.HWND]
        self.user32.IsWindowVisible.argtypes = [wt.HWND]
        self.user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        self.user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
        self.user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
        self.user32.GetWindow.restype = wt.HWND
        self.kernel32.OpenProcess.restype = wt.HANDLE
        self.kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self.kernel32.CloseHandle.argtypes = [wt.HANDLE]
        self.kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                             ctypes.POINTER(wt.DWORD)]
        try:
            self.dwm = ctypes.WinDLL("dwmapi")
        except OSError:
            self.dwm = None

    # ------------------------------------------------------------ windows
    def _title(self, hwnd) -> str:
        n = self.user32.GetWindowTextLengthW(hwnd)
        buf = self.ct.create_unicode_buffer(n + 1)
        self.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _exe(self, hwnd) -> str:
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, self.ct.byref(pid))
        h = self.kernel32.OpenProcess(0x1000, False, pid.value)       # QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = self.ct.create_unicode_buffer(520)
            size = self.wt.DWORD(520)
            if self.kernel32.QueryFullProcessImageNameW(h, 0, buf, self.ct.byref(size)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            self.kernel32.CloseHandle(h)

    def _cloaked(self, hwnd) -> bool:
        """Hidden Store-app windows and windows on other virtual desktops are 'cloaked'."""
        if self.dwm is None:
            return False
        try:
            val = self.ct.c_int(0)
            self.dwm.DwmGetWindowAttribute(self.wt.HWND(hwnd), 14, self.ct.byref(val), self.ct.sizeof(val))
            return val.value != 0
        except Exception:
            return False

    def windows(self) -> list[Win]:
        out: list[Win] = []
        proc = self.ct.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)

        def cb(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd) or hwnd in self._overlay_hwnds:
                return True
            if self.user32.GetWindow(hwnd, 4):           # GW_OWNER: skip owned popups
                return True
            if self.user32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
                return True
            title = self._title(hwnd)
            if not title or title in ("Program Manager",) or self._cloaked(hwnd):
                return True
            out.append(Win(int(hwnd), title, self._exe(hwnd)))
            return True

        self.user32.EnumWindows(proc(cb), 0)
        return out

    def foreground(self) -> Win | None:
        h = self.user32.GetForegroundWindow()
        if not h:
            return None
        return Win(int(h), self._title(h), self._exe(h))

    def _focus(self, hwnd: int) -> bool:
        u = self.user32
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)                          # SW_RESTORE
        fg = u.GetForegroundWindow()
        cur = self.kernel32.GetCurrentThreadId()
        fgt = u.GetWindowThreadProcessId(fg, None) if fg else 0
        if fgt and fgt != cur:
            u.AttachThreadInput(fgt, cur, True)
        u.BringWindowToTop(hwnd)
        ok = u.SetForegroundWindow(hwnd)
        if fgt and fgt != cur:
            u.AttachThreadInput(fgt, cur, False)
        return bool(ok)

    def focus_title(self, title: str) -> bool:
        if not title:
            return False
        for w in self.windows():
            if w.exe in ("chrome.exe", "msedge.exe", "chromium.exe") and title[:40] in w.title:
                return self._focus(w.hwnd)
        return False

    def _windows_for(self, key=None, name=None) -> list[Win]:
        wins = self.windows()
        app = next((a for a in catalog.APPS if a.key == key), None)
        if app:
            exes = {e for e in [app.exe, *app.extra] if e}
            hits = [w for w in wins if w.exe in exes]
            if hits:
                return hits
            names = app.names
        else:
            names = [name or ""]
        out = []
        for w in wins:
            base = w.exe.removesuffix(".exe")
            for n in names:
                q = fold(n)
                if q and (fold(base) == q.replace(" ", "") or q in fold(w.title) or
                          fuzz.partial_ratio(q, fold(w.title)) >= 90):
                    out.append(w)
                    break
        return out

    # ------------------------------------------------------------ apps
    def warm(self):
        """Cache the Start menu (desktop + Store apps) in the background."""
        threading.Thread(target=self._load_start_apps, name="start-apps", daemon=True).start()

    def _load_start_apps(self):
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                  "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                                 capture_output=True, text=True, timeout=30, creationflags=0x08000000)
            data = json.loads(out.stdout or "[]")
            if isinstance(data, dict):
                data = [data]
            with self._apps_lock:
                self.start_apps = [d for d in data if d.get("Name") and d.get("AppID")]
            log.info("start menu: %d apps", len(self.start_apps))
        except Exception as e:
            log.warning("could not list Start menu apps: %s", e)

    def find_start_app(self, name: str, cutoff: float = 80) -> dict | None:
        with self._apps_lock:
            apps = list(self.start_apps)
        i = _match(name, [a["Name"] for a in apps], cutoff)
        return apps[i] if i is not None else None

    def has_app(self, name: str) -> bool:
        return self.find_start_app(name, cutoff=92) is not None

    def _launch_start_app(self, app: dict):
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app["AppID"]])

    def open_app(self, key=None, name=None):
        """Focus the app if it's already open, else launch it. Returns the display name or None."""
        if key:
            app = next(a for a in catalog.APPS if a.key == key)
            wins = self._windows_for(key=key)
            if wins:
                self._focus(wins[0].hwnd)
                return app.names[0]
            try:
                os.startfile(app.launch)
                return app.names[0]
            except OSError:
                for n in app.names:              # not on PATH: look for it in the Start menu
                    hit = self.find_start_app(n)
                    if hit:
                        self._launch_start_app(hit)
                        return hit["Name"]
                return None
        hit = self.find_start_app(name)
        if hit:
            wins = self._windows_for(name=hit["Name"])
            if wins:
                self._focus(wins[0].hwnd)
            else:
                self._launch_start_app(hit)
            return hit["Name"]
        return None

    def close_app(self, key=None, name=None) -> int:
        wins = self._windows_for(key=key, name=name)
        for w in wins:
            self.user32.PostMessageW(w.hwnd, 0x0010, 0, 0)           # WM_CLOSE: app may ask to save
        return len(wins)

    def switch_app(self, key=None, name=None) -> bool:
        wins = self._windows_for(key=key, name=name)
        return bool(wins) and self._focus(wins[0].hwnd)

    def wait_foreground(self, key=None, name=None, timeout=5.0) -> bool:
        """After launching/focusing an app, wait until one of its windows is in front."""
        end = time.time() + timeout
        while time.time() < end:
            wins = self._windows_for(key=key, name=name)
            fg = self.user32.GetForegroundWindow()
            if wins:
                if any(w.hwnd == fg for w in wins):
                    time.sleep(0.15)          # let the edit control take focus
                    return True
                self._focus(wins[0].hwnd)
            time.sleep(0.2)
        return False

    def shell_open(self, target: str):
        if target.startswith("shell:") or (len(target) == 3 and target[1:] == ":\\"):
            subprocess.Popen(["explorer.exe", target])
        else:
            os.startfile(target)
        return True

    # ------------------------------------------------------------ keyboard / mouse
    def _key(self, name: str):
        K = self.Key
        table = {"ctrl": K.ctrl, "shift": K.shift, "alt": K.alt, "win": K.cmd, "enter": K.enter,
                 "esc": K.esc, "tab": K.tab, "space": K.space, "backspace": K.backspace,
                 "delete": K.delete, "home": K.home, "end": K.end, "up": K.up, "down": K.down,
                 "left": K.left, "right": K.right, "page_up": K.page_up, "page_down": K.page_down,
                 "print_screen": K.print_screen, "minus": "-", "plus": "="}
        if name in table:
            return table[name]
        if name.startswith("f") and name[1:].isdigit():
            return getattr(K, name)
        return name

    def press(self, combo: str):
        keys = [self._key(k) for k in parse_combo(combo)]
        mods, last = keys[:-1], keys[-1]
        for m in mods:
            self.kb.press(m)
        try:
            self.kb.press(last)
            self.kb.release(last)
        finally:
            for m in reversed(mods):
                self.kb.release(m)
        return True

    def type_text(self, text: str):
        self.kb.type(text)
        return True

    def scroll(self, direction: str, amount: str):
        if amount == "end":
            return self.press("ctrl+end" if direction == "down" else "ctrl+home")
        fg = self.user32.GetForegroundWindow()
        notches = 3 if amount == "small" else 10
        old = self.mouse.position
        if fg:
            r = self.wt.RECT()
            self.user32.GetWindowRect(fg, self.ct.byref(r))
            self.mouse.position = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        self.mouse.scroll(0, -notches if direction == "down" else notches)
        time.sleep(0.05)
        self.mouse.position = old
        return True

    # ------------------------------------------------------------ audio / display
    def _endpoint(self):
        try:
            import comtypes
            try:
                comtypes.CoInitialize()
            except OSError:
                pass
            from pycaw.pycaw import AudioUtilities
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)
            if ep is not None:
                return ep
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import IAudioEndpointVolume
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(iface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            log.debug("pycaw unavailable: %s", e)
            return None

    def volume(self, change=None, set=None, mute=None):
        """Returns the new level in percent when known."""
        ep = self._endpoint()
        if ep is not None:
            if mute is not None:
                ep.SetMute(1 if mute else 0, None)
                return None if mute else round(ep.GetMasterVolumeLevelScalar() * 100)
            if set is None:
                cur = ep.GetMasterVolumeLevelScalar() * 100
                set = cur + 2 * change
            set = max(0, min(100, set))
            ep.SetMute(0, None)
            ep.SetMasterVolumeLevelScalar(set / 100.0, None)
            return round(set)
        K = self.Key
        if mute is not None:
            self.kb.press(K.media_volume_mute); self.kb.release(K.media_volume_mute)
            return None
        if set is not None:
            for _ in range(50):
                self.kb.press(K.media_volume_down); self.kb.release(K.media_volume_down)
            change = set // 2
        key = K.media_volume_up if change > 0 else K.media_volume_down
        for _ in range(abs(change)):
            self.kb.press(key); self.kb.release(key)
        return set

    def _ps(self, command: str, timeout=15) -> str:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                             capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
        return out.stdout.strip()

    def brightness(self, change=None, set=None):
        if set is None:
            cur = self._ps("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
            if not cur.strip().split()[:1] or not cur.split()[0].isdigit():
                raise RuntimeError("Is screen ki brightness Windows se control nahi hoti (external monitor?)")
            set = int(cur.split()[0]) + 2 * change
        set = max(0, min(100, int(set)))
        self._ps("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                 f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0; Brightness={set}}}")
        return set

    def media(self, action: str):
        K = self.Key
        key = {"play_pause": K.media_play_pause, "next": K.media_next, "previous": K.media_previous}[action]
        self.kb.press(key)
        self.kb.release(key)
        return True

    # ------------------------------------------------------------ window management
    def window(self, action: str):
        fg = self.user32.GetForegroundWindow()
        if action == "minimize" and fg:
            self.user32.ShowWindow(fg, 6)
        elif action == "maximize" and fg:
            self.user32.ShowWindow(fg, 3)
        elif action == "restore" and fg:
            self.user32.ShowWindow(fg, 9)
        elif action == "close" and fg:
            self.user32.PostMessageW(fg, 0x0010, 0, 0)
        elif action == "switch":
            self.kb.press(self.Key.alt)
            try:
                self.kb.press(self.Key.tab); self.kb.release(self.Key.tab)
            finally:
                self.kb.release(self.Key.alt)
        elif action == "show_desktop":
            self.press("win+d")
        elif action == "snap_left":
            self.press("win+left")
        elif action == "snap_right":
            self.press("win+right")
        else:
            return False
        return True

    def screenshot(self):
        return self.press("win+print_screen")

    def power(self, action: str):
        flags = 0x08000000
        if action == "lock":
            self.user32.LockWorkStation()
        elif action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "5"], creationflags=flags)
        elif action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "5"], creationflags=flags)
        elif action == "signout":
            subprocess.Popen(["shutdown", "/l"], creationflags=flags)
        elif action == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=flags)
        return True


def make_system(dry_run: bool = False):
    if IS_WINDOWS and not dry_run:
        return WindowsSystem()
    return DryRunSystem()
