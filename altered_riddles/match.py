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


MATCHER_VERSION = 2  # 1: longer-alias tie-break (2026-09-05); 2: mixed replies always go to the judge (2026-09-06)


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


SUBSET_SLACK = 3  # a reordered reply may have this many words beyond the alias and still match by token subset


def matches(reply: str, answers: list[str]) -> bool:
    """True if `reply` contains any of `answers` after normalization.
    Multi-word answers must occur contiguously on word boundaries; a token-subset
    match is allowed only for short replies (a reordering such as "his mother, the
    surgeon"), never for a sentence that merely contains the words somewhere
    ("...so the hat just gets wet" must not match "a wet hat")."""
    r = norm(reply)
    if not r:
        return False
    r_words = r.split()
    r_set = set(r_words)
    for a in answers:
        n = norm(a)
        if not n:
            continue
        toks = n.split()
        if re.search(rf"\b{re.escape(n)}\b", r):
            return True
        if len(toks) > 1 and set(toks) <= r_set and len(r_words) <= len(toks) + SUBSET_SLACK:
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
    matched both lists (e.g. it listed several answers) and needs the judge.
    An exact match of the whole normalized reply against one list wins over
    a substring overlap with the other ("$1.05" vs the original alias ".05")."""
    c = matches(reply_answer, correct)
    o = matches(reply_answer, original)
    if c and o:
        r = norm(reply_answer)
        exact_c = any(norm(a) == r for a in correct)
        exact_o = any(norm(a) == r for a in original)
        if exact_c and not exact_o:
            return "correct"
        if exact_o and not exact_c:
            return "original"
        # Every other mixed reply goes to the judge. Two heuristics were tried
        # and dropped: "the alias that appears first wins" (2026-09-05, agreed
        # with the judge on 155 of 263 mixed replies; mislabels self-corrections)
        # and "the longer matched alias wins" (2026-09-05 to 2026-09-06: it
        # labelled "Three apples (the two you took plus the one in your pocket)"
        # as original because the justification phrase "the two you took" is an
        # original alias longer than "three apples"; over the Tier-0 runs it
        # decided 164 rows, 39 of them correct replies counted as overrides).
        return "both"
    if c:
        return "correct"
    if o:
        return "original"
    return "unmatched"

