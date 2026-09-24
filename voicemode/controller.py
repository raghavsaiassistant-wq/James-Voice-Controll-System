"""Turns a stream of transcripts into actions.

While the key is held, the speech thread sends growing partial transcripts ("youtube",
"youtube kholo", "youtube kholo aur lofi"...). Each one is re-parsed from scratch; commands that
are already complete run immediately, so the browser acts while the user is still talking.
On release the final transcript runs whatever is left. Each command runs at most once per
utterance: `executed` remembers how many commands of this utterance have been handled.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from .parser import Command, parse, safe_on_partial

log = logging.getLogger("voicemode")

# A Laya guess for these gets a spoken "confirm" first: a wrong guess would lose work or data.
RISKY_GUESS = {"window", "close_tab", "close_app", "close_browser", "power", "type_text", "click", "keys"}


@dataclass
class Result:
    ok: bool
    message: str
    pending: tuple | None = None       # ("confirm", Command) or ("pick", n_candidates)


class NullFeedback:
    def status(self, state: str, text: str = "") -> None: ...
    def transcript(self, text: str, final: bool) -> None: ...
    def action(self, message: str, ok: bool = True) -> None: ...


class Controller:
    def __init__(self, executor, brain=None, feedback=None, settings=None, utterance_log=None):
        self.executor = executor
        self.brain = brain
        self.fb = feedback or NullFeedback()
        self.settings = settings
        self.utterance_log = utterance_log
        self.executed: list[tuple] = []
        self.results: list[dict] = []
        self.pending_confirm: Command | None = None
        self.pending_confirm_at = 0.0
        self.pending_pick = False

    # ------------------------------------------------------------ utterance lifecycle
    def begin(self) -> None:
        self.executed = []
        self.results = []
        self.fb.status("listening")

    def partial(self, text: str) -> None:
        self.fb.transcript(text, final=False)
        if self.settings is None or self.settings.act_while_speaking:
            self._advance(text, final=False)

    def final(self, text: str) -> None:
        text = (text or "").strip()
        self.fb.transcript(text, final=True)
        if not text:
            self.fb.status("idle")
            return
        self._advance(text, final=True)
        if not self.results:
            self.fb.status("idle")
        if self.utterance_log:
            try:
                with open(self.utterance_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.time(), "text": text, "results": self.results},
                                       ensure_ascii=False) + "\n")
            except OSError:
                pass

    # ------------------------------------------------------------ core
    def _advance(self, text: str, final: bool) -> None:
        cmds = parse(text)
        for i in range(len(self.executed), len(cmds)):
            cmd = cmds[i]
            last = i == len(cmds) - 1
            if not final and (cmd.intent == "unknown" or (last and not safe_on_partial(cmd))):
                break
            if self.executed and cmd.signature() == self.executed[-1] and cmd.intent not in (
                    "scroll", "volume", "brightness", "keys", "media", "next_tab", "prev_tab"):
                # the recognizer revised earlier words and the same command shifted by one
                self.executed.append(cmd.signature())
                continue
            self.executed.append(cmd.signature())
            if cmd.intent == "unknown":
                cmd = self._fallback(cmd)
                if cmd is None:
                    continue
            self.run(cmd)

    def _fallback(self, cmd: Command) -> Command | None:
        """Ask Laya about text the rules could not read (final transcripts only)."""
        guess = None
        if self.brain is not None:
            try:
                guess = self.brain.classify(cmd.text)
            except Exception as e:           # a model failure must never kill the loop
                log.exception("laya fallback failed: %s", e)
        if guess is None:
            self.fb.action(f"Samajh nahi aaya: “{cmd.text}”", ok=False)
            self._record(cmd, Result(False, "not understood"))
            return None
        log.info("laya: %r -> %s", cmd.text, guess.describe())
        if guess.intent in RISKY_GUESS and not (guess.intent == "window" and guess.args.get("action") in (
                "minimize", "maximize", "restore", "switch", "show_desktop")):
            guess.destructive = True
        return guess

    def run(self, cmd: Command) -> Result:
        # an answer to a pending question?
        if self.pending_confirm is not None:
            expired = time.time() - self.pending_confirm_at > (self.settings.confirm_timeout if self.settings else 20)
            pending, self.pending_confirm = self.pending_confirm, None
            if not expired and cmd.intent == "confirm":
                return self._exec(pending, confirmed=True)
            if not expired and cmd.intent == "cancel":
                res = Result(True, "Cancel kar diya")
                self._report(cmd, res)
                return res
        if cmd.intent in ("confirm", "cancel"):
            res = Result(False, "Kuch confirm karne ko pending nahi hai")
            self._report(cmd, res)
            return res
        if cmd.intent == "pick" and not self.pending_pick:
            cmd = Command("click", {"ordinal": cmd.args["n"]}, cmd.text)
        if cmd.intent != "pick":
            self.pending_pick = False
        if cmd.destructive:
            return self._ask_confirm(cmd)
        return self._exec(cmd)

    def _ask_confirm(self, cmd: Command) -> Result:
        self.pending_confirm = cmd
        self.pending_confirm_at = time.time()
        what = f"(Laya ka guess: {cmd.describe()})" if cmd.source == "laya" else f"“{cmd.text}”"
        res = Result(True, f"Pakka? {what} — 'confirm/haan' ya 'cancel/nahi' bolo",
                     pending=("confirm", cmd))
        self.fb.status("confirm", res.message)
        self._record(cmd, res)
        return res

    def _exec(self, cmd: Command, confirmed: bool = False) -> Result:
        self.fb.status("working", cmd.describe())
        try:
            res = self.executor.execute(cmd, confirmed=confirmed)
        except Exception as e:
            log.exception("action failed: %s", cmd.describe())
            res = Result(False, f"Error: {e}")
        if res.pending and res.pending[0] == "confirm":
            self.pending_confirm = res.pending[1]
            self.pending_confirm_at = time.time()
            self.fb.status("confirm", res.message)
            self._record(cmd, res)
            return res
        if res.pending and res.pending[0] == "pick":
            self.pending_pick = True
        self._report(cmd, res)
        return res

    def _report(self, cmd: Command, res: Result) -> None:
        self.fb.action(res.message, ok=res.ok)
        self._record(cmd, res)

    def _record(self, cmd: Command, res: Result) -> None:
        log.info("%s %s -> %s", "OK " if res.ok else "ERR", cmd.describe(), res.message)
        self.results.append({"cmd": cmd.describe(), "source": cmd.source, "ok": res.ok, "msg": res.message})
