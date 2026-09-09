# AI Business Intelligence & Analysis Copilot

A web-based analytics platform that lets business owners and managers upload
their existing Excel/CSV business data and understand the performance of their
**entire business** — external performance, internal operations, employees and
salary costs, departments, and multiple branches — without SQL, Python, or
data-analysis expertise.

The system converts raw business data into:

> **What is happening → Why it is happening → What the business should focus on**

## Core principle

**AI interprets. Analytics calculates. Evidence supports.**

The LLM is not responsible for critical mathematical calculations. The analytics
engine computes the metrics; the AI explains them; every important answer is
backed by visible evidence the user can inspect.

```text
Raw Data → Data Processing → Analytics Engine → Calculated Metrics
        → Evidence → AI → Business Explanation
```

## What it analyzes

| Area | Covers |
| --- | --- |
| Business performance | Revenue, sales, orders, customers, products, categories, discounts, taxes, fees, channels |
| Financial performance | Revenue, COGS, employee cost, operating expenses, gross/operating/net profit, margins |
| Employees & operations | Employees, departments, roles, salary, attendance, overtime, incentives, productivity |
| Branch intelligence | Individual branch, multi-branch, all-branch rollup, rankings, comparisons, trends |
| Historical intelligence | Month/quarter/year comparisons, same-period-last-year, branch and department over time |

Only metrics that the uploaded data actually supports are calculated. When an
analysis is not possible, the system says so explicitly rather than failing
silently.

## Run it

```bash
# API
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload            # http://127.0.0.1:8000/docs

# Interface, in a second terminal
cd frontend
npm install && npm run dev               # http://localhost:5173
```

SQLite is the default, so nothing external is needed to start. To see it work
on realistic data without clicking through the UI:

```bash
cd backend
python scripts/generate_sample_data.py   # messy 3-branch restaurant data
python scripts/demo.py                   # runs the whole pipeline, prints the result
pytest                                   # 87 tests
```

## Repository

| Path | Contents |
| --- | --- |
| [backend/](backend/README.md) | FastAPI service: pipeline, semantic layer, analytics engine |
| [frontend/](frontend/README.md) | React interface: upload, mapping, dashboard, comparisons |
| [docs/PRD.md](docs/PRD.md) | Product Requirements Document v2.0 |
| [docs/PROCESS.md](docs/PROCESS.md) | End-to-end process, sign-in through reports |

## Stack

- **Frontend:** React, Vite, Tailwind CSS
- **Backend:** FastAPI, Python
- **Data processing:** Pandas, NumPy, OpenPyXL
- **Database:** PostgreSQL in deployment, SQLite for local work
- **AI:** LLM API for interpretation only (V2)

## Status

**V1 is built** — the pipeline through to dashboards and comparisons, as
specified in [docs/PRD.md](docs/PRD.md) §35:

authentication → business workspace → branch setup → Excel/CSV upload → data
profiling → data quality → cleaning → semantic mapping → historical storage →
core KPIs → branch comparison → company-wide analysis → problem detection →
dashboard.

**V2 is not built** — natural-language Q&A, the AI interpretation layer, the
recommendation engine and report generation ([docs/PRD.md](docs/PRD.md) §36).
The analytics engine deliberately came first: it produces the calculated
evidence that the AI layer will interpret, rather than asking the model to do
arithmetic.
