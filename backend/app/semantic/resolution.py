"""Entity resolution: many spellings, one business entity (PRD sec. 14).

A branch arrives as ``Jubilee Hills``, ``Jubilee-Hills``, ``JUBILEE HILLS``,
``Jubilee Hills Branch`` and ``JH``. The first four are the same thing by any
reading. ``JH`` might be, or might be ``Jubilee Hills Road`` -- and the
difference is a branch comparison that is wrong rather than merely incomplete.

So resolution is graded, not binary:

* an exact match on the normalised form is automatic;
* a strong structural match (contains, initials, close spelling) is automatic
  only when one candidate is clearly ahead;
* anything else is returned as a question with ranked candidates.

The raw value is always preserved; resolution records a link, it does not
overwrite what the user uploaded (Rule 9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.services.cleaning import canonical_display

# Words that carry no identifying information for a branch or department.
_NOISE = {"branch", "store", "outlet", "unit", "location", "shop", "centre", "center", "ltd",
          "pvt", "private", "limited", "the", "restaurant", "cafe", "hotel", "dept", "department"}

AUTO_ACCEPT = 0.90
NEEDS_REVIEW = 0.60
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class Candidate:
    entity_key: str
    display_name: str
    score: float
    reason: str


@dataclass
class Resolution:
    raw_value: str
    entity_key: str | None
    display_name: str | None
    confidence: float
    status: str  # resolved | ambiguous | new
    reason: str = ""
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def needs_user(self) -> bool:
        return self.status == "ambiguous"

    def as_dict(self) -> dict:
        return {
            "raw_value": self.raw_value,
            "entity_key": self.entity_key,
            "display_name": self.display_name,
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "reason": self.reason,
            "candidates": [
                {"entity_key": c.entity_key, "display_name": c.display_name,
                 "confidence": round(c.score, 3), "reason": c.reason}
                for c in self.candidates
            ],
        }


def signature(value: str) -> str:
    """Normalised form with noise words removed: the key entities match on."""
    tokens = [t for t in _NON_ALNUM.split(str(value).strip().lower()) if t]
    meaningful = [t for t in tokens if t not in _NOISE]
    return " ".join(meaningful or tokens)


def initials(value: str) -> str:
    return "".join(t[0] for t in signature(value).split() if t)


def _score(raw: str, known: str) -> tuple[float, str]:
    """How strongly ``raw`` refers to the known entity ``known``."""
    raw_sig, known_sig = signature(raw), signature(known)
    if not raw_sig or not known_sig:
        return 0.0, ""

    if raw_sig == known_sig:
        return 1.0, "same name once spelling and punctuation are ignored"

    raw_tokens, known_tokens = set(raw_sig.split()), set(known_sig.split())
    if raw_tokens and raw_tokens < known_tokens:
        # "jubilee" inside "jubilee hills" -- suggestive, never conclusive,
        # because "jubilee hills road" is an equally good host.
        return 0.72, f"'{raw}' is contained in '{known}'"
    if known_tokens and known_tokens < raw_tokens:
        return 0.86, f"'{raw}' adds words to '{known}'"

    # An abbreviation is only meaningful when it is short and complete.
    if 1 < len(raw_sig.replace(" ", "")) <= 4 and raw_sig.replace(" ", "") == initials(known):
        return 0.70, f"'{raw}' matches the initials of '{known}'"

    ratio = SequenceMatcher(None, raw_sig, known_sig).ratio()
    if ratio >= 0.88:
        return ratio * 0.95, f"'{raw}' is spelled almost identically to '{known}'"
    if ratio >= 0.75:
        return ratio * 0.8, f"'{raw}' resembles '{known}'"
    return 0.0, ""


def resolve_value(raw: str, known: dict[str, str]) -> Resolution:
    """Resolve one raw value against known entities (``key -> display name``)."""
    raw = str(raw).strip()
    if not raw:
        return Resolution(raw, None, None, 0.0, "new", "empty value")

    scored = []
    for key, display in known.items():
        score, reason = _score(raw, display)
        if score > 0:
            scored.append(Candidate(key, display, score, reason))
    scored.sort(key=lambda c: c.score, reverse=True)

    if not scored:
        return Resolution(raw, None, None, 0.0, "new", "no existing entity resembles this value")

    best = scored[0]
    runner_up = scored[1].score if len(scored) > 1 else 0.0

    # Two plausible homes is exactly the case that must not be merged silently.
    if best.score >= AUTO_ACCEPT and best.score - runner_up >= 0.1:
        return Resolution(raw, best.entity_key, best.display_name, best.score, "resolved",
                          best.reason, scored[1:3])
    if best.score >= NEEDS_REVIEW:
        return Resolution(raw, None, None, best.score, "ambiguous",
                          "more than one existing entity could be meant"
                          if runner_up >= NEEDS_REVIEW else "the match is not certain enough",
                          scored[:3])
    return Resolution(raw, None, None, best.score, "new",
                      "no existing entity is close enough to be the same one", scored[:2])


def resolve_values(values: list[str], known: dict[str, str]) -> list[Resolution]:
    """Resolve a column of raw values, learning as it goes.

    Values that resolve to a new entity become candidates for the ones after
    them, so ``Jubilee Hills`` then ``jubilee hills`` in the same file collapse
    even when neither was known beforehand.
    """
    working = dict(known)
    results = []
    for raw in dict.fromkeys(str(v).strip() for v in values if str(v).strip()):
        resolution = resolve_value(raw, working)
        if resolution.status == "new":
            key = f"auto:{signature(raw)}"
            display = canonical_display(signature(raw))
            working[key] = display
            resolution = Resolution(raw, key, display, 1.0, "new",
                                    "first time this value has been seen")
        results.append(resolution)
    return results
