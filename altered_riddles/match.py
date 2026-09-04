"""altered_riddles.match — deterministic answer matching (PLAN.md, D5).

Normalization: lowercase, ASCII quotes, possessives and punctuation
stripped, whitespace collapsed, a leading article dropped. A reply matches
an answer if the normalized answer occurs in the normalized reply on word
boundaries (single-word answers) or as a substring or a token subset
(multi-word answers). Anything that does not match any list goes to the
judge; this module never decides "wrong" on its own.
"""

from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\s$.]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
_ARTICLES = ("a ", "an ", "the ")


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("'s ", " ").replace("'", "")
    s = _PUNCT.sub(" ", s)
    s = _DOT.sub(" ", s)  # drop periods except decimal points (1.05)
    s = _SPACES.sub(" ", s).strip()
    for art in _ARTICLES:
        if s.startswith(art):
            s = s[len(art):]
    return s


def norm_words(s: str) -> list[str]:
    return norm(s).split()


def matches(reply: str, answers: list[str]) -> bool:
    """True if `reply` contains any of `answers` after normalization."""
    r = norm(reply)
    if not r:
        return False
    r_tokens = set(r.split())
    for a in answers:
        n = norm(a)
        if not n:
            continue
        toks = n.split()
        if len(toks) == 1:
            if re.search(rf"\b{re.escape(n)}\b", r):
                return True
        elif n in r or set(toks) <= r_tokens:
            return True
    return False


_ANSWER_LINE = re.compile(r"(?im)^\s*\**answer\**\s*[:\-–]\s*(.+?)\s*\**\s*$")


def extract_final_answer(text: str) -> str:
    """The content of the last 'Answer: ...' line, else the last non-empty line."""
    found = _ANSWER_LINE.findall(text or "")
    if found:
        return found[-1].strip()
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def label(reply_answer: str, *, correct: list[str], original: list[str]) -> str:
    """'correct' | 'original' | 'both' | 'unmatched'. 'both' means the reply
    matched both lists (e.g. it listed several answers) and needs the judge."""
    c = matches(reply_answer, correct)
    o = matches(reply_answer, original)
    if c and o:
        return "both"
    if c:
        return "correct"
    if o:
        return "original"
    return "unmatched"
