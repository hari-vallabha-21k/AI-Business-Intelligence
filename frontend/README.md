# Frontend — AI Business Intelligence & Analysis Copilot

React + Vite + Tailwind interface over the [backend](../backend/README.md) API.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

Start the backend first (`uvicorn app.main:app --reload` in `../backend`).

## Screens

| Screen | What it does |
| --- | --- |
| Sign in / register | Email + password, token kept in `localStorage` |
| Business setup | Name, type, currency, branches (process doc §1) |
| Upload data | File upload, then the profile, the column mappings, the quality issues and a plain-language log of what was cleaned |
| Dashboard | Company KPIs, branch ranking, detected problems, and what the data cannot answer yet |
| Compare periods | Period over period with findings and branch-level drivers |

## Interface decisions that carry the product's principles

**An unavailable metric shows the reason, never a zero.** `MetricTile` renders
"Not available" plus the explanation the API traced back to the missing concept,
so a blank cost sheet can never look like a profitable month.

**Every figure can be opened.** "View calculation" shows the formula and the
input values behind the number (PRD §25) — the UI never displays a figure it
cannot account for.

**Findings are badged by kind.** Fact, Supported driver and Hypothesis are
visually distinct, and a hypothesis carries an explicit line saying the data
does not prove it (PRD §23).

**Rankings are suppressed where they would mislead.** A metric unavailable for
one branch is not ranked, and absolute cost totals are shown but never given a
"best" — the smallest branch always spends least, which says nothing about how
well it is run. Both cases say why in the interface.

**Column mapping is a question, not an assumption.** Low-confidence columns
render a dropdown with the engine's reasoning shown underneath; confirming one
saves it for later uploads.
