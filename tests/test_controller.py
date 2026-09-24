"""Streaming behaviour: partial transcripts act early, each command runs once, confirmations."""
from voicemode.config import Settings
from voicemode.controller import Controller, Result


class FakeExecutor:
    def __init__(self):
        self.ran = []

    def execute(self, cmd, confirmed=False):
        self.ran.append((cmd.intent, dict(cmd.args), confirmed))
        if cmd.intent == "click" and cmd.args.get("name") == "place order" and not confirmed:
            from voicemode.parser import Command
            return Result(True, "confirm?", pending=("confirm", Command("click", {"el_id": "e9"}, cmd.text)))
        if cmd.intent == "click" and cmd.args.get("name") == "ambiguous":
            return Result(True, "which?", pending=("pick", 3))
        return Result(True, "ok")


def make():
    ex = FakeExecutor()
    return Controller(ex, settings=Settings()), ex


def speak(ctl, partials, final):
    ctl.begin()
    for p in partials:
        ctl.partial(p)
    ctl.final(final)


def test_acts_before_the_sentence_ends():
    ctl, ex = make()
    ctl.begin()
    ctl.partial("youtube")
    assert ex.ran == []                                # bare name: wait
    ctl.partial("youtube kholo")
    assert [r[0] for r in ex.ran] == ["open_site"]     # verb came: act now, key still held
    ctl.partial("youtube kholo aur lofi")
    assert len(ex.ran) == 1                            # "lofi" alone is not a command yet
    ctl.partial("youtube kholo aur lofi search")       # Hinglish verb at the end closes the query
    ctl.final("youtube kholo aur lofi search karo")
    assert [r[0] for r in ex.ran] == ["open_site", "search"]
    assert ex.ran[1][1]["query"] == "lofi"


def test_each_command_runs_once_despite_revisions():
    ctl, ex = make()
    speak(ctl, ["scroll down", "scroll down", "scroll down and", "scroll down and go back"],
          "scroll down and go back")
    assert [r[0] for r in ex.ran] == ["scroll", "back"]


def test_free_text_waits_for_final():
    ctl, ex = make()
    speak(ctl, ["search for alan", "search for alan turing"], "search for alan turing")
    assert ex.ran == [("search", {"query": "alan turing", "site": None}, False)]


def test_english_verb_first_waits_for_release():
    ctl, ex = make()
    ctl.begin()
    ctl.partial("open note")
    ctl.partial("open notepad")
    assert ex.ran == []
    ctl.final("open notepad")
    assert ex.ran[0][:2] == ("open_app", {"app": "notepad"})


def test_destructive_power_needs_confirm():
    ctl, ex = make()
    speak(ctl, [], "computer band karo")
    assert ex.ran == [] and ctl.pending_confirm is not None
    speak(ctl, [], "haan")
    assert ex.ran == [("power", {"action": "shutdown"}, True)]


def test_cancel_drops_pending():
    ctl, ex = make()
    speak(ctl, [], "restart karo")
    speak(ctl, [], "nahi")
    assert ex.ran == [] and ctl.pending_confirm is None


def test_other_command_drops_pending():
    ctl, ex = make()
    speak(ctl, [], "shutdown")
    speak(ctl, [], "scroll down")
    speak(ctl, [], "confirm")
    assert [r[0] for r in ex.ran] == ["scroll"]


def test_destructive_click_confirm_flow():
    ctl, ex = make()
    speak(ctl, [], "click place order")
    speak(ctl, [], "confirm")
    assert ex.ran[-1] == ("click", {"el_id": "e9"}, True)


def test_pick_after_choices():
    ctl, ex = make()
    speak(ctl, [], "click ambiguous")
    speak(ctl, [], "two")
    assert ex.ran[-1][:2] == ("pick", {"n": 2})


def test_pick_without_choices_clicks_nth_result():
    ctl, ex = make()
    speak(ctl, [], "doosra")
    assert ex.ran[-1][:2] == ("click", {"ordinal": 2})


def test_unknown_without_brain_is_reported_not_run():
    ctl, ex = make()
    speak(ctl, [], "mummy khana bana rahi hai")
    assert ex.ran == []
    assert ctl.results and ctl.results[0]["ok"] is False


def test_dangling_conjunction_is_ignored():
    ctl, ex = make()
    speak(ctl, ["volume badhao aur"], "volume badhao aur")
    assert [r[0] for r in ex.ran] == ["volume"]
    assert all(r["ok"] for r in ctl.results)


class FakeBrain:
    def __init__(self, cmd):
        self.cmd = cmd

    def classify(self, text):
        from voicemode.parser import Command
        return Command(*self.cmd, text=text, source="laya")


def test_safe_laya_guess_runs_directly():
    ex = FakeExecutor()
    ctl = Controller(ex, FakeBrain(("volume", {"change": 5})), settings=Settings())
    speak(ctl, [], "the music should be way louder")
    assert ex.ran == [("volume", {"change": 5}, False)]


def test_risky_laya_guess_asks_first():
    ex = FakeExecutor()
    ctl = Controller(ex, FakeBrain(("close_tab", {})), settings=Settings())
    speak(ctl, [], "dispose of the current tab")
    assert ex.ran == [] and ctl.pending_confirm is not None
    assert "Laya" in ctl.results[-1]["msg"]
    speak(ctl, [], "confirm")
    assert ex.ran == [("close_tab", {}, True)]
