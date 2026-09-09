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

## Documentation

| Document | Contents |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | Product Requirements Document v2.0 — scope, users, semantic engine, analytics, architecture, security, V1/V2/V3 roadmap, success criteria |
| [docs/PROCESS.md](docs/PROCESS.md) | End-to-end process — business creation through upload, profiling, semantic mapping, analytics, comparison, problem detection, AI interpretation, dashboards and reports |

## Planned stack

- **Frontend:** React, Tailwind CSS, Plotly
- **Backend:** FastAPI, Python
- **Data processing:** Pandas, NumPy, OpenPyXL, PyArrow
- **Database:** PostgreSQL (relational, multi-tenant)
- **AI:** LLM API for interpretation only
- **Deployment:** Docker

## Status

Specification stage. The PRD and process document define the product; the
implementation follows the V1 scope in [docs/PRD.md](docs/PRD.md) §35.
