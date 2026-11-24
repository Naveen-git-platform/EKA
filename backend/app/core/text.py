"""Shared text utilities (tokenization) used by BM25 and the fake embedder."""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")

STOPWORDS = frozenset(
    """a an and are as at be but by for from has have how i if in into is it its of on or our
    so such that the their then there these they this to was we were what when where which who
    will with you your do does can should may must not no than also any each per""".split()
)


def stem_token(tok: str) -> str:
    """Very light suffix stripping so `passwords`/`password`, `days`/`day` match.

    Tokens containing digits (identifiers, amounts) are left untouched.
    """
    if len(tok) <= 3 or any(ch.isdigit() for ch in tok):
        return tok
    if tok.endswith("ies") and len(tok) > 4:
        tok = tok[:-3] + "y"
    elif tok.endswith("sses"):
        tok = tok[:-2]
    elif tok.endswith("ing") and len(tok) > 5:
        tok = tok[:-3]
    elif tok.endswith("ed") and len(tok) > 4:
        tok = tok[:-2]
    elif tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        tok = tok[:-1]
    # unify `expire` / `expired` / `expires` -> `expir`
    if len(tok) > 4 and tok.endswith("e"):
        tok = tok[:-1]
    return tok


def tokenize(text: str, *, drop_stopwords: bool = True, stem: bool = True) -> list[str]:
    """Lowercase tokenizer that keeps identifiers like `err-5031` or `sec-pol-014` whole.

    Each compound token is also emitted as its parts (`err-5031` -> `err-5031`, `err`, `5031`)
    so both exact-identifier and partial queries match.
    """
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        parts = re.split(r"[-_.]", raw)
        candidates = [raw] + parts if len(parts) > 1 else [raw]
        for tok in candidates:
            if not tok:
                continue
            if drop_stopwords and tok in STOPWORDS:
                continue
            tokens.append(stem_token(tok) if stem else tok)
    return tokens
