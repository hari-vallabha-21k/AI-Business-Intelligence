"""Cleaning and normalisation (PRD sec. 11).

The rule throughout is that the original data survives: canonical records carry
the cleaned value, ``_raw`` carries what the file said, and every transformation
is written to the version's cleaning log.
"""

from __future__ import annotations

import re
from collections import Counter

import pandas as pd

_PUNCT = re.compile(r"[^a-z0-9]+")

# Tokens kept upper-case when a label is rendered to its canonical spelling.
_ACRONYMS = {"kfc", "hsr", "mg", "cbd", "it", "hq", "gk", "jp"}

# Role spellings that are safe to fold because they are pure abbreviations.
_ROLE_CANONICAL = {
    "mgr": "manager",
    "asst": "assistant",
    "asst mgr": "assistant manager",
    "sr": "senior",
    "jr": "junior",
    "exec": "executive",
    "supervisor": "supervisor",
}


def normalize_label(value: str) -> str:
    """``Jubilee-Hills `` -> ``jubilee hills``, the key branch names collapse on."""
    return " ".join(t for t in _PUNCT.split(str(value).strip().lower()) if t)


def canonical_role(value: str) -> str:
    norm = normalize_label(value)
    return _ROLE_CANONICAL.get(norm, norm)


def canonical_display(normalized: str) -> str:
    """The one spelling a normalised label is always shown as.

    Derived from the normalised form alone, never from which spelling happened
    to be most common in this file: two uploads that disagree ("JUBILEE HILLS"
    in January, "Jubilee Hills" in February) must still produce one branch.
    Short all-caps tokens are kept as acronyms, so "KFC hitech city" stays
    "KFC Hitech City".
    """
    return " ".join(t.upper() if len(t) <= 3 and t.isalpha() and t in _ACRONYMS else t.capitalize()
                    for t in normalized.split())


def build_label_map(values: pd.Series) -> tuple[dict[str, str], list[dict]]:
    """Group spelling variants of the same label onto one canonical spelling.

    Only case, punctuation and whitespace are folded. Anything requiring a
    judgement call ("Jubilee" vs "Jubilee Hills") is left alone -- the engine
    detects, it does not silently rewrite business data.
    """
    variants: dict[str, Counter] = {}
    for raw in values.dropna().astype(str):
        variants.setdefault(normalize_label(raw), Counter())[raw.strip()] += 1

    mapping: dict[str, str] = {}
    log: list[dict] = []
    for norm, counter in variants.items():
        if not norm:
            continue
        display = canonical_display(norm)
        for raw in counter:
            mapping[raw] = display
        if len(counter) > 1 or display not in counter:
            log.append(
                {
                    "type": "label_normalisation",
                    "canonical": display,
                    "variants": sorted(counter),
                    "rows_affected": sum(counter.values()) - counter.get(display, 0),
                }
            )
    return mapping, log


def clean_numeric(series: pd.Series) -> pd.Series:
    """Strip currency symbols and thousands separators, keep parentheses negative."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype(str).str.strip()
    negative = text.str.match(r"^\(.*\)$")
    text = text.str.replace(r"^\((.*)\)$", r"\1", regex=True)
    text = text.str.replace(r"[,\s₹$€£%]", "", regex=True)
    out = pd.to_numeric(text, errors="coerce")
    return out.where(~negative, -out)


# 2026-01-02 is unambiguous and must never be read as 1 February; 02/01/2026 is
# ambiguous and, for the businesses this targets, is day-first.
_ISO_DATE = re.compile(r"^\s*\d{4}-\d{1,2}-\d{1,2}")


def prefers_dayfirst(series: pd.Series) -> bool:
    """Whether a column's dates should be read day-first."""
    sample = series.dropna().astype(str).head(200)
    if sample.empty:
        return False
    return float(sample.str.match(_ISO_DATE).mean()) < 0.8


def clean_dates(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(
        series, errors="coerce", format="mixed", dayfirst=prefers_dayfirst(series)
    )
