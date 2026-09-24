"""Text helpers: tokenizing transcripts and folding Hinglish spelling variants.

Whisper writes Hinglish in Roman script, and the same word shows up spelled many ways
("neeche" / "niche", "awaaz" / "awaz", "bandh" / "band"). Every lexicon word and every
transcript token goes through the same `canon()` fold, so the parser compares folded forms
while the original text is kept for anything we copy verbatim (search queries, typed text).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*|[ऀ-ॿ]+")


def canon(word: str) -> str:
    """Fold a word to a spelling-insensitive key. Applied identically to lexicons and input."""
    w = word.lower().replace("'", "")
    for a, b in (("ee", "i"), ("oo", "u"), ("aa", "a"), ("ph", "f"), ("ck", "k"),
                 ("w", "v"), ("z", "j"), ("q", "k")):
        w = w.replace(a, b)
    w = re.sub(r"(.)\1+", r"\1", w)                      # scroll -> scrol, uppar -> upar
    w = re.sub(r"([bcdfgjklmnpqrstvxz])h$", r"\1", w)     # bandh -> band, dhoondh -> dhund
    return w


def canon_phrase(phrase: str) -> tuple[str, ...]:
    return tuple(canon(t) for t in _TOKEN_RE.findall(phrase))


def words(*phrases: str) -> set[str]:
    """Set of folded words; multi-word items become space-joined folded phrases."""
    return {" ".join(canon_phrase(p)) for p in phrases}


S = words   # alias used for comparing space-joined folded phrases


def phrases(*items: str) -> set[tuple[str, ...]]:
    """Set of folded multi-word phrases (tuples of folded tokens)."""
    return {canon_phrase(p) for p in items}


@dataclass(frozen=True)
class Token:
    raw: str      # as written in the transcript
    c: str        # folded key
    start: int    # char span in the transcript
    end: int


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(0), canon(m.group(0)), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def span_text(text: str, toks: list[Token]) -> str:
    """Original transcript text covered by `toks` (keeps case and inner punctuation)."""
    if not toks:
        return ""
    return text[toks[0].start:toks[-1].end].strip()


def join(toks: list[Token]) -> str:
    return " ".join(t.c for t in toks)


# ---------------------------------------------------------------- numbers

_CARDINALS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "ek": 1, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "tees": 30, "chalis": 40,
    "chaalis": 40, "pachas": 50, "pachaas": 50, "saath": 60, "sattar": 70, "assi": 80,
    "nabbe": 90, "sau": 100,
}
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "last": -1,
    "pehla": 1, "pehle": 1, "pehli": 1, "pahla": 1, "pahle": 1, "pahli": 1,
    "doosra": 2, "doosre": 2, "doosri": 2, "dusra": 2, "dusre": 2, "dusri": 2,
    "teesra": 3, "teesre": 3, "teesri": 3, "tisra": 3, "tisre": 3,
    "chautha": 4, "chauthe": 4, "chauthi": 4, "paanchva": 5, "paanchvan": 5, "panchva": 5,
    "aakhri": -1, "akhri": -1, "aakhiri": -1, "aakhri wala": -1,
}
CARDINALS = {canon(k): v for k, v in _CARDINALS.items()}
ORDINALS = {canon(k): v for k, v in _ORDINALS.items()}
_ORD_SUFFIX = re.compile(r"^(\d+)(st|nd|rd|th)$")


def number_of(tok: Token, allow_do: bool = False) -> int | None:
    """Value of a number/ordinal token, else None. "do" (= 2) only when `allow_do`."""
    if tok.raw.isdigit():
        return int(tok.raw)
    m = _ORD_SUFFIX.match(tok.raw.lower())
    if m:
        return int(m.group(1))
    if tok.c in ORDINALS:
        return ORDINALS[tok.c]
    if tok.c in CARDINALS:
        return CARDINALS[tok.c]
    if allow_do and tok.c == "do":
        return 2
    return None


def is_ordinal(tok: Token) -> bool:
    return tok.c in ORDINALS or bool(_ORD_SUFFIX.match(tok.raw.lower()))
