# Backend — AI Business Intelligence & Analysis Copilot

FastAPI service implementing the V1 pipeline from [`../docs/PRD.md`](../docs/PRD.md)
section 35: upload → profile → quality → clean → semantic mapping → business
semantic layer → analytics → comparison → problem detection.

## Run it

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000/docs
```

SQLite is the default so nothing external is needed. Point at PostgreSQL with:

```bash
export BI_DATABASE_URL="postgresql+psycopg://user:pass@localhost/bi"
export BI_SECRET_KEY="a-real-secret"
```

## See it work

```bash
python scripts/generate_sample_data.py   # messy multi-branch restaurant data
python scripts/demo.py                   # runs the whole pipeline, prints the result
pytest                                   # 71 tests
```

The sample data is deliberately awkward: branch names in four spellings,
salaries as `₹45,000`, and a February sales file that renames `food_sales` to
`food_revenue` and adds a `delivery_fee` column that did not exist in January.

## Layout

| Path | Role |
| --- | --- |
| `app/semantic/concepts.py` | The canonical vocabulary (PRD §13) — 25 concepts every other module speaks in |
| `app/semantic/engine.py` | Column → concept mapping with confidence scoring (PRD §12, §14) |
| `app/services/workbook.py` | Workbook scanning — finds the sheet, the header row and the real table |
| `app/services/parsing.py` | Upload validation and type recovery, user-facing errors (PRD §34) |
| `app/services/profiling.py` | Row/column/type/missing profiling (PRD §9) |
| `app/services/quality.py` | Issue detection and analysis readiness (PRD §10) |
| `app/services/cleaning.py` | Label, numeric and date normalisation (PRD §11) |
| `app/services/ingest.py` | Canonical record construction, raw values preserved |
| `app/services/layer.py` | The business semantic layer — loads canonical frames by branch and period |
| `app/analytics/registry.py` | 20 metrics, each declaring exactly what it needs |
| `app/analytics/engine.py` | Metric evaluation with dependency-traced reasons |
| `app/analytics/comparison.py` | Branch-vs-branch and period-vs-period |
| `app/analytics/problems.py` | Problem detection, fact/driver/hypothesis (PRD §21–23) |
| `app/api/` | Routes: auth, businesses, datasets, analytics |

## Reading real spreadsheets

Business exports rarely put a header in cell A1. The scanner handles the shapes
that actually arrive:

| Shape | What happens |
| --- | --- |
| Title/banner rows above the header | Header row detected by scoring the first 25 rows; the rows above are skipped |
| Merged title cell | Same — a merged banner never wins the header |
| Cover sheet before the data sheet | Every sheet is scored on its detected table; the largest wins |
| Several data sheets | Best one chosen and named in the response; the user can override with `sheet=` |
| Totals / grand total row | Dropped, so a summary line is never counted as a transaction |
| Repeated column headings | Kept, made unique — neither column is lost |
| Blank spacer columns | Dropped |
| xlsx bytes named `.xls`, or no extension at all | Recognised by file signature, not by name |
| Amounts as `₹ 45,000.00` text | Recovered as numbers |
| Semicolon/tab/pipe CSV, or a CSV with title lines | Delimiter detected across the body, not from the first line |

Every decision is reported back on `profile.source` — sheet name, header row,
rows skipped, totals dropped — and shown in the interface, because a wrong guess
about the header row is otherwise invisible in the numbers.

**When detection genuinely fails, the file is kept and the user is asked.** An
unclassifiable upload is stored with its columns unmapped rather than rejected;
confirming what the columns mean re-derives the dataset kind and brings the data
into the analysis.

## Design decisions worth knowing

**Nothing is calculated that the data cannot support.** A metric declares its
requirements; if they are absent it comes back `available: false` with a reason
traced to the missing concept, rather than a number computed by treating a
missing cost as zero:

```json
{ "key": "operating_profit", "value": null, "available": false,
  "reason": "Operating profit needs Cost of goods sold, which is unavailable.
             Cost of goods sold needs Cost of goods sold in sales data or in expense data." }
```

**Every available metric carries its own evidence** — formula and input values —
so the UI can show "view calculation" (PRD §25).

**Findings are typed.** `fact` is a calculated movement, `driver` is a
decomposition the data supports, `hypothesis` is a possible explanation
explicitly marked as unproven. Contribution analysis refuses non-additive
metrics: branch shares of a margin do not sum to the company margin, so "who
drove it" is not a question that metric can answer.

**Rows are stored canonically, not per-file.** A dataset version holds records
keyed by concept plus the original row under `_raw`. That is what lets January's
`food_sales` and February's `food_revenue` aggregate together, and lets a user's
mapping correction re-run cleaning against the original values.

**Undated snapshots are excluded from period filters, not spread across them.**
A payroll file with no date column would otherwise count one month's wages in
every month. The exclusion is reported in the response `notes`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register`, `/api/auth/token` | Register / log in |
| `POST` | `/api/businesses` | Create a business with branches |
| `POST` | `/api/businesses/{id}/uploads` | Upload a file, run the pipeline |
| `PATCH` | `/api/versions/{id}/mappings` | Confirm column meanings; remembered for later uploads |
| `GET` | `/api/businesses/{id}/overview` | Company KPIs + what is not calculable |
| `GET` | `/api/businesses/{id}/compare/branches` | Branch ranking |
| `GET` | `/api/businesses/{id}/compare/dimension?concept=DEPARTMENT` | Any dimension |
| `GET` | `/api/businesses/{id}/compare/periods` | Period over period + findings + drivers |
| `GET` | `/api/businesses/{id}/problems` | Everything currently worth attention |

All business-scoped routes are tenant-isolated; another user's business returns
404, not 403.

## Not built yet

Natural-language Q&A, the AI interpretation layer, the recommendation engine and
report generation are V2 (PRD §36). The analytics engine deliberately lands
first: the AI layer consumes its evidence rather than calculating anything
itself.
