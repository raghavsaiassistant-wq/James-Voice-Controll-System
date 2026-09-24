"""Parser table: what people say -> what the parser must produce.

Each case lists the expected commands in order as (intent, {subset of args}).
"""
import pytest

from voicemode.parser import parse, safe_on_partial

CASES = [
    # --- open websites
    ("go to youtube", [("open_site", {"site": "youtube"})]),
    ("open youtube", [("open_site", {"site": "youtube"})]),
    ("youtube kholo", [("open_site", {"site": "youtube"})]),
    ("YouTube kholo.", [("open_site", {"site": "youtube"})]),
    ("wikipedia pe jao", [("open_site", {"site": "wikipedia"})]),
    ("google kholo", [("open_site", {"site": "google"})]),
    ("Gmail open karo", [("open_site", {"site": "gmail"})]),
    ("go to example dot com", [("open_site", {"url": "https://example.com"})]),
    ("open github.com", [("open_site", {"url": "https://github.com"})]),
    ("youtube", [("open_site", {"site": "youtube"})]),
    ("James, youtube kholo please", [("open_site", {"site": "youtube"})]),
    # --- search
    ("search for alan turing", [("search", {"query": "alan turing", "site": None})]),
    ("search youtube for lofi beats", [("search", {"query": "lofi beats", "site": "youtube"})]),
    ("search lofi beats on youtube", [("search", {"query": "lofi beats", "site": "youtube"})]),
    ("google pe weather search karo", [("search", {"query": "weather", "site": "google"})]),
    ("alan turing ke baare me search karo", [("search", {"query": "alan turing"})]),
    ("Alan Turing search karo", [("search", {"query": "Alan Turing"})]),
    ("search karo alan turing", [("search", {"query": "alan turing"})]),
    ("cricket score dhundo", [("search", {"query": "cricket score"})]),
    ("search for tom and jerry", [("search", {"query": "tom and jerry"})]),
    ("search for how to open a file", [("search", {"query": "how to open a file"})]),
    ("google alan turing", [("search", {"query": "alan turing"})]),
    ("amazon pe headphones search karo", [("search", {"query": "headphones", "site": "amazon"})]),
    # --- play
    ("youtube pe lofi songs chalao", [("play", {"query": "lofi songs", "site": "youtube"})]),
    ("play despacito", [("play", {"query": "despacito"})]),
    ("arijit singh ke gaane chalao", [("play", {"query": "arijit singh ke gaane"})]),
    ("spotify chalao", [("open_site", {"site": "spotify"})]),
    ("gaana chalao", [("media", {"action": "play_pause"})]),
    ("pause karo", [("media", {"action": "play_pause"})]),
    ("gaana band karo", [("media", {"action": "play_pause"})]),
    ("next song", [("media", {"action": "next"})]),
    ("agla gaana", [("media", {"action": "next"})]),
    ("pichla gaana lagao", [("media", {"action": "previous"})]),
    # --- click
    ("click the first result", [("click", {"ordinal": 1, "kind": "result"})]),
    ("pehle result pe click karo", [("click", {"ordinal": 1, "kind": "result"})]),
    ("doosra video kholo", [("click", {"ordinal": 2, "kind": "video"})]),
    ("open the second link", [("click", {"ordinal": 2, "kind": "link"})]),
    ("click on login", [("click", {"name": "login"})]),
    ("login button dabao", [("click", {"name": "login", "kind": "button"})]),
    ("click the sign in button", [("click", {"name": "sign in", "kind": "button"})]),
    ("subscribe pe click karo", [("click", {"name": "subscribe"})]),
    ("press the like button", [("click", {"name": "like", "kind": "button"})]),
    ("last result pe click karo", [("click", {"ordinal": -1})]),
    # --- type
    ("type hello world", [("type_text", {"text": "hello world"})]),
    ("likho kal milte hain", [("type_text", {"text": "kal milte hain"})]),
    ("Hello, how are you likho", [("type_text", {"text": "Hello, how are you"})]),
    ("type alan turing in the search box", [("type_text", {"text": "alan turing", "field": "search box"})]),
    ("search box me alan turing likho", [("type_text", {"text": "alan turing", "field": "search box"})]),
    # --- scroll
    ("scroll down", [("scroll", {"direction": "down", "amount": "page"})]),
    ("scroll down a bit", [("scroll", {"direction": "down", "amount": "small"})]),
    ("neeche scroll karo", [("scroll", {"direction": "down"})]),
    ("niche karo", [("scroll", {"direction": "down"})]),
    ("thoda upar karo", [("scroll", {"direction": "up", "amount": "small"})]),
    ("thoda aur neeche", [("scroll", {"direction": "down", "amount": "small"})]),
    ("scroll to the bottom", [("scroll", {"direction": "down", "amount": "end"})]),
    ("sabse upar jao", [("scroll", {"direction": "up", "amount": "end"})]),
    ("top pe jao", [("scroll", {"direction": "up", "amount": "end"})]),
    ("scroll up", [("scroll", {"direction": "up"})]),
    # --- history
    ("go back", [("back", {})]),
    ("wapas jao", [("back", {})]),
    ("peeche jao", [("back", {})]),
    ("pichle page pe jao", [("back", {})]),
    ("aage jao", [("forward", {})]),
    ("page refresh karo", [("reload", {})]),
    ("reload", [("reload", {})]),
    # --- tabs
    ("open a new tab", [("new_tab", {})]),
    ("naya tab kholo", [("new_tab", {})]),
    ("close this tab", [("close_tab", {})]),
    ("ye tab band karo", [("close_tab", {})]),
    ("next tab", [("next_tab", {})]),
    ("agla tab", [("next_tab", {})]),
    ("pichla tab", [("prev_tab", {})]),
    ("second tab", [("goto_tab", {"n": 2})]),
    ("tab 3 pe jao", [("goto_tab", {"n": 3})]),
    ("youtube band karo", [("close_tab", {"site": "youtube"})]),
    # --- apps
    ("open notepad", [("open_app", {"app": "notepad"})]),
    ("calculator kholo", [("open_app", {"app": "calculator"})]),
    ("notepad open karo", [("open_app", {"app": "notepad"})]),
    ("vs code kholo", [("open_app", {"app": "vscode"})]),
    ("open discord", [("open_thing", {"name": "discord"})]),
    ("chrome kholo", [("open_browser", {})]),
    ("notepad band karo", [("close_app", {"app": "notepad"})]),
    ("close notepad", [("close_app", {"app": "notepad"})]),
    ("switch to notepad", [("switch_app", {"app": "notepad"})]),
    ("downloads folder kholo", [("open_folder", {"folder": "downloads"})]),
    ("open documents", [("open_folder", {"folder": "documents"})]),
    ("settings kholo", [("open_settings", {"page": "home"})]),
    ("wifi settings kholo", [("open_settings", {"page": "wifi"})]),
    ("bluetooth settings open karo", [("open_settings", {"page": "bluetooth"})]),
    # --- volume / brightness
    ("volume badhao", [("volume", {"change": 5})]),
    ("volume up", [("volume", {"change": 5})]),
    ("awaaz thodi kam karo", [("volume", {"change": -2})]),
    ("volume bahut kam karo", [("volume", {"change": -10})]),
    ("volume 50 karo", [("volume", {"set": 50})]),
    ("set volume to 30 percent", [("volume", {"set": 30})]),
    ("full volume", [("volume", {"set": 100})]),
    ("mute karo", [("volume", {"mute": True})]),
    ("volume band karo", [("volume", {"mute": True})]),
    ("unmute", [("volume", {"mute": False})]),
    ("brightness badhao", [("brightness", {"change": 5})]),
    ("brightness 70 karo", [("brightness", {"set": 70})]),
    # --- windows
    ("minimize karo", [("window", {"action": "minimize"})]),
    ("minimize this window", [("window", {"action": "minimize"})]),
    ("window chhota karo", [("window", {"action": "minimize"})]),
    ("maximize", [("window", {"action": "maximize"})]),
    ("window band karo", [("window", {"action": "close"})]),
    ("band karo", [("window", {"action": "close"})]),
    ("close this", [("window", {"action": "close"})]),
    ("switch window", [("window", {"action": "switch"})]),
    ("desktop dikhao", [("window", {"action": "show_desktop"})]),
    ("sab minimize karo", [("window", {"action": "show_desktop"})]),
    ("full screen karo", [("keys", {"combo": "f11"})]),
    # --- keys
    ("press enter", [("keys", {"combo": "enter"})]),
    ("enter dabao", [("keys", {"combo": "enter"})]),
    ("tab dabao", [("keys", {"combo": "tab"})]),
    ("ctrl c", [("keys", {"combo": "ctrl+c"})]),
    ("Control Shift T", [("keys", {"combo": "ctrl+shift+t"})]),
    ("press alt f4", [("keys", {"combo": "alt+f4"})]),
    ("copy karo", [("keys", {"combo": "ctrl+c"})]),
    ("isko paste karo", [("keys", {"combo": "ctrl+v"})]),
    ("sab select karo", [("keys", {"combo": "ctrl+a"})]),
    ("save karo", [("keys", {"combo": "ctrl+s"})]),
    ("undo", [("keys", {"combo": "ctrl+z"})]),
    ("zoom in", [("keys", {"combo": "ctrl+plus"})]),
    ("screenshot lo", [("screenshot", {})]),
    ("take a screenshot", [("screenshot", {})]),
    # --- power
    ("shutdown the computer", [("power", {"action": "shutdown"})]),
    ("computer band karo", [("power", {"action": "shutdown"})]),
    ("laptop band kar do", [("power", {"action": "shutdown"})]),
    ("restart karo", [("power", {"action": "restart"})]),
    ("laptop lock karo", [("power", {"action": "lock"})]),
    ("lock", [("power", {"action": "lock"})]),
    ("sleep mode", [("power", {"action": "sleep"})]),
    # --- confirm / pick
    ("confirm", [("confirm", {})]),
    ("haan", [("confirm", {})]),
    ("cancel", [("cancel", {})]),
    ("nahi", [("cancel", {})]),
    ("two", [("pick", {"n": 2})]),
    ("do", [("pick", {"n": 2})]),
    ("number 3", [("pick", {"n": 3})]),
    ("doosra wala", [("pick", {"n": 2})]),
    # --- more phrasing seen in testing
    ("gaane ki awaaz thodi tez kar do", [("volume", {"change": 2})]),
    ("page ko thoda neeche le jao", [("scroll", {"direction": "down", "amount": "small"})]),
    ("mujhe pichle page pe le chalo", [("back", {})]),
    ("take me back to the previous page", [("back", {})]),
    ("ek naya tab chahiye", [("new_tab", {})]),
    ("put the laptop to sleep", [("power", {"action": "sleep"})]),
    ("get rid of this tab", [("close_tab", {})]),
    ("hide this window", [("window", {"action": "minimize"})]),
    ("notepad mein hello world likho", [("type_text", {"text": "hello world", "app": "notepad"})]),
    ("type good morning in notepad", [("type_text", {"text": "good morning", "app": "notepad"})]),
    ("YouTube pe Arijit Singh ke gaane chalao", [("play", {"query": "Arijit Singh ke gaane", "site": "youtube"})]),
    ("search box mein lofi type karo", [("type_text", {"text": "lofi", "field": "search box"})]),
    ("screen lock kar do", [("power", {"action": "lock"})]),
    ("Chrome band karo", [("close_browser", {})]),
    ("sabse neeche jao", [("scroll", {"direction": "down", "amount": "end"})]),
    ("calculator open kar do please", [("open_app", {"app": "calculator"})]),
    # --- follow-ups, new items, photos (the reel flow)
    ("once you are there, can you create a new note", [("new_item", {"what": "note"})]),
    ("nayi note banao", [("new_item", {"what": "note"})]),
    ("ek nayi file banao", [("new_item", {"what": "file"})]),
    ("new folder banao", [("new_item", {"what": "folder"})]),
    ("inside this new note, let's make the title say hello", [("type_text", {"text": "hello"})]),
    ("title hello likho", [("type_text", {"text": "hello"})]),
    ("title me Shopping list likho", [("type_text", {"text": "Shopping list"})]),
    ("nayi file me hello likho", [("type_text", {"text": "hello", "new_item": "file"})]),
    ("write good morning in a new note", [("type_text", {"text": "good morning", "new_item": "note"})]),
    ("usme hello likho", [("type_text", {"text": "hello"})]),
    ("wahan pe lofi search karo", [("search", {"query": "lofi"})]),
    ("ab neeche scroll karo", [("scroll", {"direction": "down"})]),
    ("meri photo lo", [("take_photo", {})]),
    ("let's take a picture of me", [("take_photo", {})]),
    ("selfie le lo", [("take_photo", {})]),
    ("photo khincho", [("take_photo", {})]),
    ("photos kholo", [("open_app", {"app": "photos"})]),
    ("open up the photo booth", [("open_app", {"app": "camera"})]),
    ("camera kholo", [("open_app", {"app": "camera"})]),
    ("open up the notes app for me", [("open_app", {"app": "notes"})]),
    ("open up the arc browser", [("open_browser", {})]),
    ("can you Google search Norbert Wiener?", [("search", {"query": "Norbert Wiener"})]),
    ("next tab", [("next_tab", {})]),
    ("Great great. Ok let's move on", []),
    ("Cool awesome thank you.", []),
    # --- chains
    ("youtube kholo aur lofi search karo",
     [("open_site", {"site": "youtube"}), ("search", {"query": "lofi"})]),
    ("youtube kholo lofi search karo",
     [("open_site", {"site": "youtube"}), ("search", {"query": "lofi"})]),
    ("go to example dot com and click the more information link",
     [("open_site", {"url": "https://example.com"}), ("click", {"name": "more information", "kind": "link"})]),
    ("open youtube and search for lofi",
     [("open_site", {"site": "youtube"}), ("search", {"query": "lofi"})]),
    ("open youtube search for lofi",
     [("open_site", {"site": "youtube"}), ("search", {"query": "lofi"})]),
    ("notepad kholo aur hello likho",
     [("open_app", {"app": "notepad"}), ("type_text", {"text": "hello"})]),
    ("volume badhao aur gaana chalao",
     [("volume", {"change": 5}), ("media", {"action": "play_pause"})]),
    ("scroll down then click the first result",
     [("scroll", {"direction": "down"}), ("click", {"ordinal": 1})]),
    # --- not commands
    ("so anyway I think we should get lunch", [("unknown", {})]),
    # --- the reel, one breath (English)
    ("Alright, can you open up the notes app for me and once you are there, can you create a new note? "
     "And inside this new note, let's make the title say hello. Great great. Ok let's move on and can you "
     "open up the arc browser and once you are there, can you Google search Norbert Wiener? Now can you open "
     "up x dot com? Nice nice. Ok. Now can you open up the photo booth? And let's take a picture of me. "
     "Cool awesome thank you.",
     [("open_app", {"app": "notes"}), ("new_item", {"what": "note"}), ("type_text", {"text": "hello"}),
      ("open_browser", {}), ("search", {"query": "Norbert Wiener"}), ("open_site", {"url": "https://x.com"}),
      ("confirm", {}), ("open_app", {"app": "camera"}), ("take_photo", {})]),
    # --- the same flow in Hinglish, with and without punctuation
    ("Notepad kholo nayi file me hello likho browser kholo Google pe Norbert Wiener search karo "
     "x.com kholo Camera kholo meri photo lo",
     [("open_app", {"app": "notepad"}), ("type_text", {"text": "hello", "new_item": "file"}),
      ("open_browser", {}), ("search", {"query": "Norbert Wiener", "site": "google"}),
      ("open_site", {"url": "https://x.com"}), ("open_app", {"app": "camera"}), ("take_photo", {})]),
    ("Notepad kholo. Usme nayi file banao aur title hello likho. Ab browser kholo, wahan pe Norbert Wiener "
     "search karo. Phir x.com kholo. Camera kholo aur meri photo lo.",
     [("open_app", {"app": "notepad"}), ("new_item", {"what": "file"}), ("type_text", {"text": "hello"}),
      ("open_browser", {}), ("search", {"query": "Norbert Wiener"}), ("open_site", {"url": "https://x.com"}),
      ("open_app", {"app": "camera"}), ("take_photo", {})]),
    ("mummy khana bana rahi hai", [("unknown", {})]),
]


@pytest.mark.parametrize("text,expected", CASES, ids=[c[0] for c in CASES])
def test_parse(text, expected):
    got = parse(text)
    summary = [c.describe() for c in got]
    assert len(got) == len(expected), summary
    for cmd, (intent, args) in zip(got, expected):
        assert cmd.intent == intent, summary
        for k, v in args.items():
            val = cmd.args.get(k)
            if isinstance(v, str) and isinstance(val, str):
                assert val.lower() == v.lower(), summary
            else:
                assert val == v, summary


def test_partial_safety():
    assert safe_on_partial(parse("youtube kholo")[0])          # verb came last: object complete
    assert not safe_on_partial(parse("open you")[0])            # English verb-first: wait
    assert not safe_on_partial(parse("youtube")[0])             # bare name: wait
    assert safe_on_partial(parse("scroll down")[0])             # closed set
    assert not safe_on_partial(parse("search for alan")[0])     # free text: wait for final
    assert safe_on_partial(parse("alan turing search karo")[0])  # verb-final free text


def test_follow_up_is_marked_context():
    c = parse("usme hello likho")[0]
    assert c.context
    assert not parse("hello likho")[0].context
    cmds = parse("notepad kholo aur usme hello likho")
    assert [c.context for c in cmds] == [False, True]


def test_destructive_power():
    assert parse("shutdown the computer")[0].destructive
    assert not parse("lock")[0].destructive
