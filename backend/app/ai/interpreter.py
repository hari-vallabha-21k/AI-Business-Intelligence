"""The AI boundary (PRD sec. 30, sec. 35).

The model's job is to put validated results into readable English. It is given
the evidence the analytics engine produced -- labels, values, units, formulas,
caveats -- and nothing else. It never sees uploaded rows, customer names or
salaries against individuals, and it is never asked to compute, infer a missing
figure, or assert a cause.

Two implementations:

* ``TemplateInterpreter`` -- deterministic, always available, no API key. The
  system is fully functional without a model.
* ``ClaudeInterpreter`` -- used when an API key is configured. Its prompt
  forbids new numbers, and any reply that invents one is rejected in favour of
  the template output.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

MODEL = "claude-opus-5"
MAX_TOKENS = 1200

SYSTEM_PROMPT = """You explain business analysis results to a small-business owner.

You are given evidence that has already been calculated and validated by an
analytics engine. Your job is to explain it in plain English.

Rules you must follow:
- Never state a number that is not present in the evidence. Do not add, subtract,
  average or re-derive anything.
- Never claim one thing caused another. The evidence distinguishes a fact from a
  supported contribution from a hypothesis; keep those distinctions in your words.
  A contribution means "this accounts for part of the change", not "this caused it".
- If a limitation is listed, mention it plainly rather than glossing over it.
- Do not invent context about the business, its market, seasonality or customers.
- Write 2-4 short sentences. No headings, no bullet points, no preamble.
- Use the currency symbol exactly as it appears in the evidence.
"""


class Interpreter(Protocol):
    name: str

    def explain(self, answer) -> str: ...


def _format_value(row: dict) -> str:
    value, unit = row.get("value"), row.get("unit")
    if value is None:
        return "not available"
    if unit == "percent":
        return f"{value:,.1f}%"
    if unit == "count":
        return f"{value:,.0f}"
    return f"{value:,.0f}"


class TemplateInterpreter:
    """Deterministic prose. No model, no risk of invention."""

    name = "template"

    def explain(self, answer) -> str:
        parts = [answer.headline]

        facts = [f for f in answer.findings if f.get("kind") == "fact"]
        drivers = [f for f in answer.findings if f.get("kind") == "driver"]
        hypotheses = [f for f in answer.findings if f.get("kind") == "hypothesis"]

        for finding in facts[:2]:
            parts.append(finding["detail"])
        for finding in drivers[:2]:
            parts.append(finding["detail"])
        for finding in hypotheses[:1]:
            parts.append(f"Possibly, though not shown by this data: {finding['detail']}")

        if answer.limitations:
            parts.append("Worth knowing: " + answer.limitations[0])
        return " ".join(p.rstrip(".") + "." for p in parts if p)


class ClaudeInterpreter:
    """Explanation by Claude, over evidence only."""

    name = MODEL

    def __init__(self, api_key: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._fallback = TemplateInterpreter()

    def explain(self, answer) -> str:
        payload = _evidence_payload(answer)
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": payload}],
            )
        except Exception:  # noqa: BLE001 - an explanation is never worth a failed request
            return self._fallback.explain(answer)

        if response.stop_reason == "refusal":
            return self._fallback.explain(answer)

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text or _invents_numbers(text, payload):
            # The model produced a figure that is not in the evidence. The
            # deterministic explanation is used instead of a plausible wrong one.
            return self._fallback.explain(answer)
        return text


def _evidence_payload(answer) -> str:
    """The only thing the model is shown. Structured, aggregated, no raw rows."""
    lines = [f"Question: {answer.question.text}", f"Answer: {answer.headline}", "", "Evidence:"]

    for row in answer.evidence:
        if "values" in row:
            values = ", ".join(f"{k}: {v:,.1f}" for k, v in row["values"].items())
            lines.append(f"- {row.get('label')} by {row.get('scope', 'scope')}: {values}")
        elif "current" in row:
            lines.append(
                f"- {row.get('label')}: previous {row.get('previous'):,.0f}, "
                f"current {row.get('current'):,.0f}, change {row.get('percent')}%"
            )
        else:
            lines.append(
                f"- {row.get('label')}: {_format_value(row)} "
                f"(formula: {row.get('formula', 'n/a')})"
            )

    if answer.findings:
        lines += ["", "Findings (respect the kind of each):"]
        for finding in answer.findings:
            lines.append(f"- [{finding.get('kind', 'fact').upper()}] {finding.get('detail')}")

    if answer.limitations:
        lines += ["", "Limitations you must mention if relevant:"]
        lines += [f"- {item}" for item in answer.limitations]

    lines += ["", "Write the explanation now."]
    return "\n".join(lines)


_NUMBER = re.compile(r"\d[\d,]*\.?\d*")


def _invents_numbers(text: str, payload: str) -> bool:
    """Reject an explanation containing a figure absent from the evidence.

    Comparison is on the digits alone so that formatting differences (1,234 vs
    1234, 12.0% vs 12%) do not trip the check.
    """
    def digits(value: str) -> str:
        return value.replace(",", "").rstrip("0").rstrip(".")

    allowed = {digits(m) for m in _NUMBER.findall(payload)}
    for match in _NUMBER.findall(text):
        cleaned = digits(match)
        # Small integers are ordinary prose ("two branches"), not claims.
        if not cleaned or (cleaned.isdigit() and len(cleaned) <= 2):
            continue
        if cleaned not in allowed:
            return True
    return False


def get_interpreter() -> Interpreter:
    """The configured interpreter, or the deterministic one."""
    api_key = os.environ.get("BI_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return TemplateInterpreter()
    try:
        return ClaudeInterpreter(api_key)
    except ImportError:
        # The anthropic package is optional; without it the system still answers.
        return TemplateInterpreter()
