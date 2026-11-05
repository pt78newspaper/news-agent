"""Canonical date normalization for events reported by the AI model.

The model writes dates in free form (ISO, Russian month names, DD.MM.YYYY,
even mixed-up forms like '2026.10-06'). All downstream logic (dedup windows,
history trimming, prompts) does plain string comparisons on 'YYYY-MM-DD',
so every non-ISO date breaks those windows. This module reduces any
plausible date string to 'YYYY-MM-DD' and falls back to the run date.
"""
import re
from datetime import datetime, timedelta

_MONTHS_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
    "мая": 5, "мае": 5, "май": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
    "октябр": 10, "ноябр": 11, "декабр": 12,
}
_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_WORD = (
    "|".join(k + r"\w*" for k in _MONTHS_RU)
    + "|"
    + "|".join(sorted(_MONTHS_EN, key=len, reverse=True))
)
_MONTH_WORD_RE = re.compile(_MONTH_WORD, re.I)


def _month_num(word):
    word = word.strip(". ").lower().replace("ё", "е")
    for key, num in _MONTHS_RU.items():
        if word.startswith(key):
            return num
    if word in _MONTHS_EN:
        return _MONTHS_EN[word]
    return _MONTHS_EN.get(word[:3])


def _fmt(y, m, d):
    try:
        dt = datetime(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None
    if dt > datetime.utcnow() + timedelta(days=2):
        return None  # future dates from the model are hallucinations
    return dt.strftime("%Y-%m-%d")


def normalize_date(raw, fallback):
    """Return 'YYYY-MM-DD' for a model-provided date, else `fallback`.

    `fallback` must itself be a 'YYYY-MM-DD' string (the run date).
    """
    if not raw:
        return fallback
    s = str(raw).strip()
    if not s:
        return fallback
    low = s.lower().replace("ё", "е")

    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        out = _fmt(m[1], m[2], m[3])
        if out:
            return out
    m = re.match(r"^(\d{4})[./](\d{1,2})[./-](\d{1,2})", s)
    if m:
        out = _fmt(m[1], m[2], m[3])
        if out:
            return out
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        out = _fmt(m[3], m[2], m[1])
        if out:
            return out

    year_m = re.search(r"\b(20\d{2})\b", s)
    year = year_m.group(1) if year_m else str(fallback)[:4]

    # "5 ноября 2026", "5-7 ноября", "5-Nov-2026"
    m = re.search(
        rf"(\d{{1,2}})[-–—\s]+(?:\d{{1,2}}\s+)?({_MONTH_WORD})\w*\s*,?\s*(20\d{{2}})?", low)
    if m:
        out = _fmt(m[3] or year, _month_num(m[2]), m[1])
        if out:
            return out
    # "November 5, 2026", "Ноябрь 5"
    m = re.search(
        rf"({_MONTH_WORD})\w*\s*\.{0,1}\s*,?\s*(\d{{1,2}})\s*,?\s*(20\d{{2}})?", low)
    if m:
        out = _fmt(m[3] or year, _month_num(m[1]), m[2])
        if out:
            return out
    return fallback
