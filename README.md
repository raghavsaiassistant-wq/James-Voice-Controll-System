# Voice Mode — offline voice control for Windows

**Right Alt** dabake rakho, bolo, chhod do. Voice Mode aapki baat samajhta hai aur browser ya poore
computer pe wo kaam kar deta hai: websites, search, click, typing, apps, volume, windows, shutdown.
**Hindi, English aur Hinglish** teeno me. Setup ke baad **100% offline** chalta hai: awaaz aapke
computer se bahar nahi jaati.

```
 hold Right Alt ─▶ mic ─▶ Whisper-Hindi2Hinglish (local) ─▶ "youtube kholo aur lofi search karo"
                                                                │
                              rules parser (Hindi/English/Hinglish) + Laya (local model)
                                                                │
                    ┌───────────────────────────────┬───────────┴─────────────┐
               browser (Playwright)            Windows (apps, keys,      confirm / pick
               open, search, click, type        volume, windows, power)   "haan" · "do"
```

Aap bol hi rahe hote ho, tab tak kaam shuru ho jaata hai. Ek hi saans me poora flow bol sakte ho:

> "Notepad kholo, nayi file me hello likho, browser kholo, Google pe Norbert Wiener search karo,
> x.com kholo, Camera kholo, meri photo lo"

Har command jaise hi poori samajh aati hai, turant chalti hai (aap aage bolte rehte ho), order me,
ek hi baar. Screen ke upar ek chhota bar aapke words live dikhata hai.

## Install (ek baar, internet chahiye)

1. Ye repo download karo (Code → Download ZIP, extract) ya `git clone` karo.
2. **`setup.bat`** pe double-click karo.

Setup khud check karta hai aur jo missing hai wahi install karta hai:

| Step | Kya check / install hota hai |
| --- | --- |
| 1 | Windows 10/11 64-bit, disk space (~5 GB), RAM |
| 2 | Python 3.10–3.13 (nahi hai to winget ya python.org se Python 3.12 install) |
| 3 | Microsoft Visual C++ Runtime (PyTorch ke liye; admin popup aa sakta hai) |
| 4 | `.venv` + PyTorch (CPU) + saare Python packages (`requirements.txt`) |
| 5 | Chromium browser (Playwright) |
| 6 | Offline models → `models/` (speech ~290 MB, Laya ~650 MB) |
| 7 | Self-check (models internet ke bina load hote hain ya nahi) + Desktop shortcut |

Setup dobara chalana safe hai: jo ho chuka hai wo skip hota hai, adhoora download resume hota hai.

Options: `setup.bat -NoLaya` (Laya ke bina, kam RAM, sirf rules), `setup.bat -Gpu` (NVIDIA GPU
wala PyTorch), `setup.bat -NoShortcut`.

**System:** normal laptop chalega, GPU zaroori nahi. 4-core CPU, 8 GB RAM (16 GB comfortable).
Command khatam hone se action tak ~0.5–1 s lagta hai.

## Use

- **`run.bat`** (ya Desktop pe *Voice Mode*) chalao. Console me "Voice Mode ready" aayega.
- **Right Alt dabake rakho → bolo → chhod do.** Beep = sunna shuru / band.
- **Transcript bar:** Right Alt dabate hi screen ke **top-center** pe ek dark rounded bar aata hai:
  - left me waveform jo aapki awaaz ke saath hilta hai
  - beech me aapke words live, word-by-word (lamba ho to purana hissa left se kat jaata hai)
  - neeche har command ka result: **✓ Notepad khol diya** / **✗ Samajh nahi aaya** / **? Confirm karo**
  - key chhodne aur kaam khatam hone ke ~1.5 s baad fade out
  - focus nahi leta, clicks aar-paar jaate hain, taskbar me nahi dikhta
- Bar bina mic ke dekhna ho: `run.bat --overlay-demo` (ek demo sentence chalata hai, kuch karta nahi).
- Mic test: `run.bat --mic-test` (5 second bolo; dikhata hai kya suna aur kya samjha, kuch chalata
  nahi). Pehle isse apni awaaz pe check kar lo.
- Bina mic ke: `run.bat --text` (command type karo).
- Band karna: console me **Ctrl+C**.

## Kya bol sakte ho

| Kaam | English | Hinglish / Hindi |
| --- | --- | --- |
| Website | "open youtube", "go to example dot com" | "youtube kholo", "wikipedia pe jao" |
| Search | "search for alan turing", "search youtube for lofi" | "google pe weather search karo", "alan turing ke baare me search karo" |
| Gaana / video | "play despacito" | "youtube pe arijit singh ke gaane chalao", "agla gaana", "pause karo" |
| Click | "click the first result", "click on sign in" | "pehle result pe click karo", "login button dabao", "doosra video kholo" |
| Type | "type hello world", "type alan turing in the search box" | "kal milte hain likho", "notepad mein hello likho" |
| Scroll | "scroll down a bit", "scroll to the bottom" | "neeche scroll karo", "thoda upar karo", "sabse upar jao" |
| Browser | "go back", "reload", "open a new tab", "next tab" | "wapas jao", "page refresh karo", "naya tab kholo", "ye tab band karo" |
| Apps | "open notepad", "close notepad", "switch to excel" | "calculator kholo", "vs code open karo", "notepad band karo" |
| Folders / settings | "open downloads" | "downloads folder kholo", "wifi settings kholo", "bluetooth settings" |
| Volume / brightness | "volume up", "set volume to 30 percent", "mute" | "awaaz thodi kam karo", "volume 50 karo", "brightness badhao" |
| Windows | "minimize", "maximize", "switch window" | "window chhota karo", "desktop dikhao", "window band karo" |
| Keys | "press enter", "ctrl c", "alt f4" | "enter dabao", "copy karo", "sab select karo", "save karo" |
| Screen | "take a screenshot" | "screenshot lo", "full screen karo" |
| Naya note / file | "create a new note", "make the title say hello" | "nayi note banao", "nayi file me hello likho", "title hello likho", "new folder banao" |
| Camera | "open the camera", "take a picture of me" | "camera kholo", "meri photo lo", "selfie le lo" |
| Power | "lock", "shutdown the computer" | "laptop lock karo", "computer band karo", "restart karo" |

### Ek saans me kai kaam, aur follow-ups

- Commands ko "aur", "phir", "then", comma ya full stop se jodo, ya bas ek ke baad ek bolo:
  "notepad kholo nayi file me hello likho browser kholo…". Hinglish me verb ("kholo", "karo",
  "likho") aate hi command chal jaati hai; English me agla command shuru hone pe ya ~0.7 s ruk jaane
  pe (search / typing ke liye ~1.2 s).
- Har command ek hi baar chalti hai, bolne ke order me. Speech model beech ke words badal de to bhi
  dobara nahi chalti.
- **Follow-ups** pichle khule app/tab pe lagte hain: "once you're there…", "wahan pe…", "usme…",
  "ab…", "inside this note…". Jaise "Notepad kholo" ke baad "usme hello likho" Notepad me hi likhega,
  aur "YouTube kholo, wahan pe lofi search karo" YouTube pe hi search karega. Ek hi baar key dabake
  bola gaya har command bhi apne-aap pichle khule app pe jaata hai.
- Beech ki baatein ("great, great, okay", "thank you") ignore hoti hain.
- **Camera:** "meri photo lo" Camera app kholta hai (agar khula nahi hai), webcam start hone ka ~2.5 s
  wait karta hai, phir photo leta hai (Space). Photo *Pictures › Camera Roll* me save hoti hai.
- **Notes:** "notes app" = Sticky Notes (na ho to OneNote, phir Notepad). "Nayi note" = Ctrl+N us
  app me jo saamne hai (browser me naya tab).

**Safety:** shutdown / restart / sign-out aur "buy", "place order", "delete", "send" jaise buttons
pe pehle poochta hai. **"confirm" / "haan"** bolo to hoga, **"cancel" / "nahi"** bolo to nahi.
Agar page pe kai milte-julte buttons hain to un pe **number** dikhte hain: "do" / "two" / "teesra" bolo.

## Kaise kaam karta hai

| Part | Kya | Kyun |
| --- | --- | --- |
| Hotkey | Low-level keyboard hook (pynput); Right Alt ko apps tak pahunchne nahi deta | Menu bar nahi khulta, aur hamare bheje keys Alt+… nahi bante |
| Speech → text | [`Oriserve/Whisper-Hindi2Hinglish-Swift`](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift) (whisper-base, Indian-accented Hindi pe trained), CPU pe | Hindi/Hinglish/English sab Roman script me: "youtube pe lofi chalao" |
| Samajhna | `voicemode/parser.py`: Hindi/English/Hinglish rules, spelling variants ("neeche/niche") | Tez (microseconds), predictable, har partial transcript pe chal sakta hai |
| Laya | [`laya-multilingual`](https://huggingface.co/convaiinnovations/laya) (local) | (1) jo rules na samjhe uska fallback, (2) page pe sahi element chunna ("cart me daal do" → *Add to cart*) |
| Browser | Playwright + Chromium, apna profile `data/browser-profile` | Page ke buttons/links padh ke click/type |
| System | Win32 (ctypes), pynput, pycaw | Apps, windows, keys, volume, brightness, power, bina admin |

**Bolte-bolte action:** key dabe rehte hue har ~0.3 s me speech dobara transcribe hoti hai. Jo command
poori ho chuki hai (Hinglish verb aa gaya: "youtube *kholo*", ya uske baad agli command shuru ho
gayi, ya aap ruk gaye) wo turant chalti hai; baaki queue me order se. Search / type ka text tab
chalta hai jab uske baad kuch aur bola jaaye, aap ruk jaao, ya key chhodo, taaki query beech me na kate.

**Lambi recording:** Whisper ek baar me 30 s hi sunta hai, isliye lambi hold ko pause pe tukdon me
"commit" kiya jaata hai. Aap ek hold me minute bhar bhi bol sakte ho.

**Laya ke baare me sach:** hamare test me Laya-multilingual ne 12 me se sahi intent group 33 me se
25 baar chuna (76%), kabhi-kabhi galat bhi high confidence ke saath. Isliye main parser rules hain,
aur Laya ka guess agar risky ho (close, type, click, power) to pehle confirm poochta hai.

## Settings (`settings.json`, optional)

Repo folder me `settings.json` banao, sirf wo keys jo badalni hain:

```json
{
  "hotkey": "right_alt",
  "use_laya": true,
  "browser_channel": "",
  "search_engine": "google",
  "act_while_speaking": true,
  "pause_act_seconds": 0.7,
  "pause_act_free_seconds": 1.2,
  "camera_warmup": 2.5,
  "partial_interval": 0.3,
  "overlay": true,
  "beeps": true,
  "stt_threads": 0,
  "stt_quantize": false
}
```

- `hotkey`: `right_alt`, `right_ctrl`, `right_shift`, `caps_lock`, `scroll_lock`, `pause`, `insert`, `f7`–`f12`
- `browser_channel`: `""` = bundled Chromium, `"msedge"` = installed Edge, `"chrome"` = installed Chrome
  (profile alag rehta hai)
- `search_engine`: `google`, `duckduckgo`, `bing`
- `stt_quantize`: `true` = ~35% tez, lekin lambe Hindi sentences me words chhoot sakte hain
- `pause_act_seconds` / `pause_act_free_seconds`: kitna rukne pe command "poori" maani jaaye
- `camera_warmup`: Camera app khulne ke baad photo lene se pehle kitne second rukna hai
- `mic_device`: sounddevice device number/name, agar default mic galat hai

Logs: `logs/voicemode.log`, aur har command `logs/utterances.jsonl` me (sirf aapke computer pe;
`log_utterances: false` se band).

## Troubleshooting

- **Words galat sunai de rahe hain:** speech model chhota hai (CPU ke liye). Saaf aur thoda dheere
  bolo, mic paas rakho. Hinglish/Hindi pe ye sabse accha hai; English me naam kabhi galat sun leta
  hai (hamare test me reel ke audio pe "x dot com" → "extra kaam" suna). `run.bat --mic-test` se
  check karo kya suna ja raha hai.
- **Kuch sunai nahi deta:** Windows Settings → Privacy & security → Microphone → "Let desktop apps
  access your microphone" ON. `run.bat --mic-test` se check karo.
- **Right Alt kaam nahi karta:** kuch keyboards (AltGr layouts) pe Right Alt alag behave karta hai;
  `settings.json` me `"hotkey": "right_ctrl"` try karo.
- **Admin apps (Task Manager etc.) pe hotkey nahi chalta:** Windows admin windows ko normal apps ki
  keys nahi deta. Aisi window pe kaam karna ho to `run.bat` ko "Run as administrator" se chalao.
- **"DLL load failed" (torch):** Visual C++ Runtime install karo: https://aka.ms/vs/17/release/vc_redist.x64.exe
- **RAM kam hai / slow start:** `settings.json` me `"use_laya": false`.
- **Brightness nahi badalti:** Windows sirf laptop ki built-in screen ki brightness control karta
  hai, external monitor ki nahi.

## Development

```bash
pip install -r requirements-dev.txt
pytest                       # parser, controller, listener, real headless Chromium tests
python -m voicemode --text --dry-run   # system actions log hote hain, chalte nahi
```

Tests: 190+ Hindi/English/Hinglish phrases ka parser table (poora demo flow English aur Hinglish
me bhi), word-by-word streaming (har command ek baar, order me, bolte-bolte), follow-up context,
camera / new-note actions, 30 s se lambi hold ka commit logic, confirm/pick flows, bar ke helpers,
aur ek local test page pe asli Chromium (click, ordinal results, numbered badges, typing, scroll,
tabs). Laya tests `models/laya` hone pe chalte hain.

## Status

Core logic (parser, controller, streaming speech, browser actions, models offline load) automated
tests se check hai. Demo reel ka asli audio bhi end-to-end chalaya gaya (speech model → commands).
Transcript bar Linux (Xvfb) pe render karke dekha gaya. Windows-specific parts (hotkey hook,
system actions, bar ki transparency / no-focus styles, Camera shutter, `setup.ps1`) Win32 APIs pe
likhe gaye hain aur asli Windows pe abhi test nahi hue; `setup.ps1` PowerShell parser se validate
hai. Koi problem aaye to `logs/voicemode.log` ke saath issue kholo.

## Credits

- Design idea: [moritzkremb/jev-voice-browser](https://github.com/moritzkremb/jev-voice-browser) (MIT)
- Speech model: [Oriserve/Whisper-Hindi2Hinglish-Swift](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift) (Apache-2.0)
- Decision model: [Laya](https://pypi.org/project/laya/) by convaiinnovations (Apache-2.0)
