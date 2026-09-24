"""The video flow end to end: streaming partials -> controller -> executor, with a recording
system backend and a fake browser. Checks order, no duplicates, context and new actions."""
from voicemode.actions.system import DryRunSystem
from voicemode.config import Settings
from voicemode.controller import Controller
from voicemode.executor import Executor


class FakeBrowser:
    def __init__(self):
        self.calls = []
        self.running = False
        self.fg = False

    def _c(self, *a):
        self.calls.append(a)

    def front(self):
        self.running = True
        self._c("front")

    def open(self, url):
        self.running = True
        self._c("open", url)
        return url

    def search(self, q, site):
        self.running = True
        self._c("search", q, site)
        return site or "google"

    def new_tab(self, url=None):
        self._c("new_tab")

    def is_foreground(self):
        return self.fg

    def play_youtube(self, q):
        self._c("play", q)
        return q


def make():
    s = Settings()
    sysm = DryRunSystem()
    br = FakeBrowser()
    ex = Executor(s, sysm, br)
    return Controller(ex, settings=s), sysm, br, ex


def words_stream(sentence):
    w = sentence.split()
    return [" ".join(w[:i]) for i in range(1, len(w) + 1)]


def actions(sysm, br):
    """Interleaved, meaningful actions only (no focus waits)."""
    return [c for c in sysm.calls if c[0] != "wait_foreground"], br.calls


HINGLISH = ("Notepad kholo nayi file me hello likho browser kholo Google pe Norbert Wiener search karo "
            "x.com kholo Camera kholo meri photo lo")


def test_hinglish_flow_runs_while_speaking_in_order_once():
    ctl, sysm, br, ex = make()
    ctl.begin()
    ran_before_final = None
    for p in words_stream(HINGLISH):
        ctl.partial(p)
        if p.endswith("Camera kholo"):
            ran_before_final = len(ctl.results)
    ctl.final(HINGLISH)
    assert ran_before_final is not None and ran_before_final >= 5     # all but the photo, mid-sentence
    intents = [r["cmd"].split("(")[0] for r in ctl.results]
    assert intents == ["open_app", "type_text", "open_browser", "search", "open_site", "open_app", "take_photo"]
    assert all(r["ok"] for r in ctl.results), ctl.results
    sys_calls, br_calls = actions(sysm, br)
    assert sys_calls == [("open_app", "notepad"), ("press", "ctrl+n"), ("type_text", "hello"),
                         ("open_app", "camera"), ("press", "space")]
    assert ("search", "Norbert Wiener", "google") in br_calls
    assert ("open", "https://x.com") in br_calls


def test_new_file_text_goes_to_the_app_opened_in_the_same_breath():
    ctl, sysm, br, ex = make()
    ctl.begin()
    ctl.final("notepad kholo aur nayi file me hello likho")
    # focus Notepad before Ctrl+N and typing
    assert sysm.calls.index(("wait_foreground", "notepad")) < sysm.calls.index(("press", "ctrl+n"))


def test_follow_up_in_next_utterance_uses_context_word():
    ctl, sysm, br, ex = make()
    ctl.begin(); ctl.final("notepad kholo")
    sysm.calls.clear()
    ctl.begin(); ctl.final("hello likho")             # no follow-up word: types where you are
    assert ("wait_foreground", "notepad") not in sysm.calls
    sysm.calls.clear()
    ctl.begin(); ctl.final("usme hello likho")        # "usme" = in that one
    assert sysm.calls[0] == ("wait_foreground", "notepad")
    assert sysm.calls[-1] == ("type_text", "hello")


def test_browser_follow_up_goes_to_browser():
    ctl, sysm, br, ex = make()
    ctl.begin(); ctl.final("youtube kholo")
    ctl.begin(); ctl.final("wahan pe lofi search karo")
    assert br.calls[-1][0] == "search" and br.calls[-1][1] == "lofi"


def test_new_note_in_browser_is_a_tab_but_in_app_is_ctrl_n():
    ctl, sysm, br, ex = make()
    ctl.begin(); ctl.final("browser kholo aur nayi file banao")
    assert ("new_tab",) in br.calls
    ctl.begin(); ctl.final("notepad kholo aur nayi file banao")
    assert ("press", "ctrl+n") in sysm.calls


def test_photo_opens_camera_when_needed():
    ctl, sysm, br, ex = make()
    ctl.begin(); ctl.final("meri photo lo")
    sc, _ = actions(sysm, br)
    assert sc == [("open_app", "camera"), ("press", "space")]


def test_english_reel_flow():
    reel = ("Alright, can you open up the notes app for me and once you are there, can you create a new note? "
            "And inside this new note, let's make the title say hello. Great great. Ok let's move on and can "
            "you open up the arc browser and once you are there, can you Google search Norbert Wiener? Now "
            "can you open up x dot com? Nice nice. Ok. Now can you open up the photo booth? And let's take a "
            "picture of me. Cool awesome thank you.")
    ctl, sysm, br, ex = make()
    ctl.begin()
    for p in words_stream(reel):
        ctl.partial(p)
    ctl.final(reel)
    sc, bc = actions(sysm, br)
    assert sc == [("open_app", "notes"), ("press", "ctrl+n"), ("type_text", "hello"),
                  ("open_app", "camera"), ("press", "space")]
    assert ("search", "Norbert Wiener", None) in bc and ("open", "https://x.com") in bc
    assert not [r for r in ctl.results if not r["ok"]]


def test_pause_lets_english_command_run_before_release():
    ctl, sysm, br, ex = make()
    ctl.begin()
    ctl.partial("open notepad", 0.2)
    assert sysm.calls == []
    ctl.partial("open notepad", 0.8)                 # user paused: the command is complete
    assert ("open_app", "notepad") in sysm.calls
    ctl.partial("search for alan", 0.8)              # free text needs a longer pause
    assert not br.calls


def test_unreadable_piece_does_not_block_later_commands():
    ctl, sysm, br, ex = make()
    ctl.begin()
    ctl.partial("notepad kholo. blah blorp zzz. volume badhao")
    assert ("open_app", "notepad") in sysm.calls
    assert any(c[0] == "volume" for c in sysm.calls)
