"""What the user can name: websites, Windows apps, folders and settings pages.

Code owns every URL and launch command; nothing here comes from a model. Apps that are not
listed are still found at runtime through the Start menu (see actions/system.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .text import canon_phrase


@dataclass
class Site:
    key: str
    names: list[str]
    url: str
    search: str | None = None          # URL template with {q}
    app: str | None = None             # prefer this installed app (Start-menu name) if present


@dataclass
class App:
    key: str
    names: list[str]
    launch: str                        # exe / URI given to ShellExecute
    exe: str | None = None             # process name, used to find/close its windows
    extra: list[str] = field(default_factory=list)       # other process names of the same app
    start_names: list[str] = field(default_factory=list)  # Start-menu names to try if launch fails
    fallback: str | None = None        # app key to open instead when this one isn't installed


SITES = [
    Site("youtube", ["youtube", "you tube", "yt"], "https://www.youtube.com",
         "https://www.youtube.com/results?search_query={q}"),
    Site("google", ["google"], "https://www.google.com", "https://www.google.com/search?q={q}"),
    Site("wikipedia", ["wikipedia", "wiki", "vikipedia"], "https://en.wikipedia.org",
         "https://en.wikipedia.org/w/index.php?search={q}"),
    Site("gmail", ["gmail", "g mail", "email", "mail"], "https://mail.google.com"),
    Site("maps", ["google maps", "maps", "map"], "https://www.google.com/maps",
         "https://www.google.com/maps/search/{q}"),
    Site("github", ["github", "git hub"], "https://github.com", "https://github.com/search?q={q}"),
    Site("amazon", ["amazon"], "https://www.amazon.in", "https://www.amazon.in/s?k={q}"),
    Site("flipkart", ["flipkart", "flip kart"], "https://www.flipkart.com",
         "https://www.flipkart.com/search?q={q}"),
    Site("reddit", ["reddit"], "https://www.reddit.com", "https://www.reddit.com/search/?q={q}"),
    Site("twitter", ["twitter", "x dot com"], "https://x.com", "https://x.com/search?q={q}"),
    Site("instagram", ["instagram", "insta"], "https://www.instagram.com"),
    Site("facebook", ["facebook", "fb"], "https://www.facebook.com"),
    Site("linkedin", ["linkedin", "linked in"], "https://www.linkedin.com",
         "https://www.linkedin.com/search/results/all/?keywords={q}"),
    Site("whatsapp", ["whatsapp", "whats app", "watsapp"], "https://web.whatsapp.com", app="WhatsApp"),
    Site("netflix", ["netflix"], "https://www.netflix.com", app="Netflix"),
    Site("hotstar", ["hotstar", "jio hotstar", "jiohotstar"], "https://www.hotstar.com"),
    Site("spotify", ["spotify"], "https://open.spotify.com",
         "https://open.spotify.com/search/{q}", app="Spotify"),
    Site("chatgpt", ["chatgpt", "chat gpt"], "https://chatgpt.com"),
    Site("stackoverflow", ["stack overflow", "stackoverflow"], "https://stackoverflow.com",
         "https://stackoverflow.com/search?q={q}"),
    Site("duckduckgo", ["duckduckgo", "duck duck go"], "https://duckduckgo.com",
         "https://duckduckgo.com/?q={q}"),
    Site("bing", ["bing"], "https://www.bing.com", "https://www.bing.com/search?q={q}"),
    Site("hackernews", ["hacker news", "hackernews"], "https://news.ycombinator.com"),
]

APPS = [
    App("notepad", ["notepad", "note pad", "notepad app"], "notepad.exe", "notepad.exe"),
    App("calculator", ["calculator", "calc", "calci", "calculater"], "calc.exe", "calculatorapp.exe",
        extra=["calculator.exe"]),
    App("paint", ["paint", "ms paint", "mspaint"], "mspaint.exe", "mspaint.exe"),
    App("cmd", ["command prompt", "cmd", "command line"], "cmd.exe", "cmd.exe"),
    App("powershell", ["powershell", "power shell"], "powershell.exe", "powershell.exe"),
    App("terminal", ["terminal", "windows terminal"], "wt.exe", "windowsterminal.exe"),
    App("explorer", ["file explorer", "explorer", "files", "file manager", "my files"],
        "explorer.exe", "explorer.exe"),
    App("taskmgr", ["task manager", "taskmanager"], "taskmgr.exe", "taskmgr.exe"),
    App("control", ["control panel"], "control.exe"),
    App("snipping", ["snipping tool", "snip tool", "snipping"], "ms-screenclip:", "snippingtool.exe"),
    App("camera", ["camera", "camera app", "photo booth", "photobooth", "webcam", "selfie camera",
                   "windows camera"], "microsoft.windows.camera:", "windowscamera.exe"),
    App("notes", ["notes", "notes app", "note app", "sticky notes", "sticky note", "stickynotes"],
        "", "microsoft.notes.exe",
        extra=["stickynotes.exe"], start_names=["Sticky Notes", "OneNote"], fallback="notepad"),
    App("photos", ["photos", "photo", "gallery"], "ms-photos:", "photos.exe"),
    App("store", ["microsoft store", "store", "app store"], "ms-windows-store:"),
    App("clock", ["clock", "alarm", "alarms", "timer", "stopwatch"], "ms-clock:"),
    App("calendar", ["calendar"], "outlookcal:"),
    App("word", ["word", "ms word", "microsoft word"], "winword.exe", "winword.exe"),
    App("excel", ["excel", "ms excel", "microsoft excel"], "excel.exe", "excel.exe"),
    App("powerpoint", ["powerpoint", "power point", "ppt"], "powerpnt.exe", "powerpnt.exe"),
    App("outlook", ["outlook"], "outlook.exe", "outlook.exe"),
    App("vscode", ["vs code", "vscode", "visual studio code", "code editor"], "code", "code.exe"),
    App("firefox", ["firefox", "fire fox"], "firefox.exe", "firefox.exe"),
    App("vlc", ["vlc", "vlc player", "media player"], "vlc.exe", "vlc.exe"),
    App("wordpad", ["wordpad", "word pad"], "write.exe", "wordpad.exe"),
]

# Folders open in File Explorer.
FOLDERS = {
    "downloads": (["downloads", "download", "downloads folder", "download folder"], "shell:Downloads"),
    "documents": (["documents", "document", "documents folder", "my documents"], "shell:Personal"),
    "desktop": (["desktop folder"], "shell:Desktop"),
    "pictures": (["pictures", "pictures folder", "photos folder", "images folder"], "shell:My Pictures"),
    "music": (["music folder", "songs folder"], "shell:My Music"),
    "videos": (["videos", "videos folder", "video folder"], "shell:My Video"),
    "thispc": (["this pc", "my computer", "this computer", "my pc"], "shell:MyComputerFolder"),
    "recycle": (["recycle bin", "dustbin", "trash"], "shell:RecycleBinFolder"),
    "c": (["c drive"], "C:\\"),
    "d": (["d drive"], "D:\\"),
    "e": (["e drive"], "E:\\"),
}

SETTINGS = {
    "home": (["settings", "setting", "windows settings", "system settings"], "ms-settings:"),
    "wifi": (["wifi", "wi fi", "wifi settings", "internet settings", "network settings", "network"],
             "ms-settings:network-wifi"),
    "bluetooth": (["bluetooth", "bluetooth settings"], "ms-settings:bluetooth"),
    "display": (["display settings", "display", "screen settings"], "ms-settings:display"),
    "sound": (["sound settings", "audio settings"], "ms-settings:sound"),
    "battery": (["battery", "battery settings", "battery saver", "power settings"],
                "ms-settings:batterysaver"),
    "update": (["windows update", "update settings", "updates"], "ms-settings:windowsupdate"),
    "apps": (["apps settings", "installed apps", "apps and features"], "ms-settings:appsfeatures"),
    "notifications": (["notifications", "notification settings"], "ms-settings:notifications"),
    "storage": (["storage", "storage settings"], "ms-settings:storagesense"),
    "mouse": (["mouse settings", "touchpad settings", "touchpad"], "ms-settings:mousetouchpad"),
    "datetime": (["date and time", "time settings", "date time settings"], "ms-settings:dateandtime"),
    "wallpaper": (["wallpaper", "background", "wallpaper settings"], "ms-settings:personalization-background"),
}

BROWSER_NAMES = ["browser", "chrome", "google chrome", "edge", "microsoft edge", "chromium",
                 "web browser", "internet", "arc", "arc browser", "brave", "brave browser", "opera",
                 "the browser", "my browser", "internet browser"]


def _index(entries):
    out: dict[tuple[str, ...], object] = {}
    for entry, names in entries:
        for n in names:
            out[canon_phrase(n)] = entry
    return out


SITE_BY_NAME = _index((s, s.names) for s in SITES)
SITE_BY_KEY = {s.key: s for s in SITES}
APP_BY_NAME = _index((a, a.names) for a in APPS)
FOLDER_BY_NAME = _index(((k, v[1]), v[0]) for k, v in FOLDERS.items())
SETTINGS_BY_NAME = _index(((k, v[1]), v[0]) for k, v in SETTINGS.items())
BROWSER_BY_NAME = {canon_phrase(n) for n in BROWSER_NAMES}


def site_for_url(url: str) -> Site | None:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    host = host.removeprefix("www.").removeprefix("m.")
    for s in SITES:
        sh = (urlparse(s.url).hostname or "").removeprefix("www.")
        if sh and (host == sh or host.endswith("." + sh)):
            return s
    return None
