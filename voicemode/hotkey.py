"""Global hold-to-talk key (Windows).

A low-level keyboard hook sees the key before any app does and swallows it, so holding Right
Alt never opens an app's menu bar and never turns our own keystrokes into Alt+something.
Keys we inject ourselves are ignored (LLKHF_INJECTED).
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger("voicemode")

KEYS = {
    "right_alt": 0xA5, "right_ctrl": 0xA3, "right_shift": 0xA1, "caps_lock": 0x14,
    "scroll_lock": 0x91, "pause": 0x13, "insert": 0x2D, "f7": 0x76, "f8": 0x77, "f9": 0x78,
    "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_INJECTED = 0x10
VK_LCONTROL, VK_RMENU = 0xA2, 0xA5


class PushToTalk:
    def __init__(self, key: str, on_down, on_up):
        if key not in KEYS:
            raise ValueError(f"unknown hotkey {key!r}; use one of: {', '.join(KEYS)}")
        self.key = key
        self.vk = KEYS[key]
        self.on_down, self.on_up = on_down, on_up
        self.down = False
        self.listener = None

    def start(self):
        if sys.platform != "win32":
            raise RuntimeError("the global push-to-talk key needs Windows; use --text on other systems")
        from pynput import keyboard

        def filt(msg, data):
            if data.flags & LLKHF_INJECTED:
                return True
            if data.vkCode == self.vk:
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self.down:
                        self.down = True
                        self.on_down()
                elif msg in (WM_KEYUP, WM_SYSKEYUP):
                    if self.down:
                        self.down = False
                        self.on_up()
                self.listener.suppress_event()
            elif self.vk == VK_RMENU and data.vkCode == VK_LCONTROL and data.scanCode == 0x21D:
                # AltGr keyboard layouts send a fake Left Ctrl together with Right Alt
                self.listener.suppress_event()
            return True

        self.listener = keyboard.Listener(win32_event_filter=filt)
        self.listener.start()
        log.info("push-to-talk key: %s", self.key)

    def stop(self):
        if self.listener is not None:
            self.listener.stop()
