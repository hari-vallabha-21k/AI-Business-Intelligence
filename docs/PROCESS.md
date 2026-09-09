# Process Document

## AI Business Intelligence & Analysis Copilot — End-to-End Process

Companion to [PRD.md](./PRD.md) (Version 2.0). This document describes how the
system behaves from the moment a user signs in to the moment they receive an
answer, a dashboard, or a report.

---

## 1. Business Creation

User signs in.

```text
Create Business
      ↓
Business Name
      ↓
Business Type
      ↓
Currency
      ↓
Branches
```

The user can initially create one or multiple branches.

---

## 2. Upload Data

User uploads one or more files.

Example:

```text
Sales.xlsx
Employees.xlsx
Expenses.xlsx
Branches.xlsx
```

The system registers each dataset.

---

## 3. File Validation

System checks:

```text
File format
File readability
File size
Empty file
Corruption
Security
```

If invalid:

> "We couldn't read this file. Please upload a valid Excel or CSV file."

---

## 4. Data Profiling

The system examines the dataset.

```text
Rows
Columns
Types
Missing Values
Duplicates
Dates
Identifiers
Numeric Fields
Categories
Relationships
```

---

## 5. Entity Detection

The system determines what the dataset represents.

For example:

```text
Dataset
 ↓
Employee Dataset
```

or:

```text
Dataset
 ↓
Sales Transaction Dataset
```

or:

```text
Dataset
 ↓
Expense Dataset
```

Potential entities include:

```text
Business
Branch
Employee
Customer
Product
Transaction
Expense
Department
```

---

## 6. Semantic Mapping

Columns are mapped to business concepts.

Example:

```text
emp_id → EMPLOYEE_ID
name → EMPLOYEE_NAME
location → BRANCH
designation → ROLE
monthly_pay → EMPLOYEE_COMPENSATION
```

Confidence is assigned.

```text
High
Medium
Low
```

Low-confidence mappings require user confirmation.

---

## 7. Data Quality

The system checks whether the data can actually support the intended analysis.

Example:

```text
Revenue data ✓
Branch data ✓
Employee data ✓
Salary data ✓
Profit calculation ✕
```

It tells the user:

> "Revenue and employee-cost analysis are available. Profit analysis cannot be calculated because operating-cost data is missing."

---

## 8. Data Cleaning

System identifies:

```text
Branch name inconsistencies
Role inconsistencies
Date inconsistencies
Duplicate records
Missing values
```

The original data remains preserved.

---

## 9. Business Model Creation

The system builds a logical representation:

```text
Business
 ↓
Branches
 ↓
Departments
 ↓
Employees
 ↓
Transactions
 ↓
Revenue
 ↓
Costs
 ↓
Profitability
```

This becomes the **Business Semantic Layer**.

---

## 10. Historical Matching

The system checks previous datasets.

Example:

```text
January:
food_sales

February:
food_revenue
```

Semantic engine recognizes both as potentially representing the same business concept.

It compares the new dataset against historical schema and mappings.

---

## 11. Schema Evolution

If a new column appears:

```text
delivery_fee
```

the system detects it.

It can display:

> "A new delivery fee field was detected."

The user can decide whether it should participate in specific analyses.

---

## 12. Analytics Engine

The analytics engine calculates supported metrics.

Example:

```text
Total Revenue
Total Salary Cost
Employee Count
Revenue per Employee
Employee Cost Ratio
Branch Profit
Branch Growth
```

Only metrics supported by the data are generated.

---

## 13. Branch Analysis

Each branch is analyzed independently.

```text
Branch A
Branch B
Branch C
```

Metrics are calculated using consistent definitions where the underlying data permits.

---

## 14. Cross-Branch Comparison

The system compares:

```text
Branch A
vs
Branch B
vs
Branch C
```

It can rank branches according to selected metrics.

Example:

```text
Highest Revenue → Branch B
Highest Profit → Branch B
Lowest Employee Cost Ratio → Branch B
```

---

## 15. Company-Wide Aggregation

The system combines branch-level data where aggregation is valid.

```text
Branch A ─┐
Branch B ─┼──→ Overall Business
Branch C ─┘
```

The owner gets:

```text
Total Revenue
Total Employees
Total Employee Cost
Total Expenses
Total Profit
```

where supported.

---

## 16. Historical Comparison

The system compares current data with previous periods.

Example:

```text
March vs February
```

and:

```text
March 2026 vs March 2025
```

It can also compare:

```text
Branch A March
vs
Branch B March
```

---

## 17. Problem Detection

The system scans calculated metrics for meaningful changes.

Example:

```text
Revenue ↑ 10%
Employee Cost ↑ 25%
```

Problem:

> Employee costs are increasing significantly faster than revenue.

Another example:

```text
Branch B
Revenue ↑ 15%
Profit ↑ 20%

Branch C
Revenue ↑ 8%
Profit ↓ 12%
```

Potential issue:

> Branch C's profitability declined despite revenue growth.

---

## 18. Driver Analysis

The system investigates dimensions that can explain the observed change.

```text
Profit ↓
   ↓
Costs ↑
   ↓
Employee Cost ↑
   ↓
Branch C
   ↓
Employee Count ↑
```

The system reports the supported relationship.

It does not automatically claim causality.

---

## 19. AI Interpretation

The calculated evidence is passed to the AI.

Example input:

```text
Revenue: +8%
Employee Cost: +21%
Employee Count: +18%
Profit: -7%
```

AI generates:

> "Revenue grew 8%, but employee costs increased 21%, substantially faster than revenue. Employee count also increased 18%. This coincided with a 7% decline in profit."

This is much safer than asking the LLM to calculate everything itself.

---

## 20. User Question

User asks:

> "Why is Branch A performing worse than Branch B?"

System:

```text
Question
 ↓
Identify Branch A + Branch B
 ↓
Identify "performing"
 ↓
Select relevant metrics
 ↓
Calculate comparison
 ↓
Find major differences
 ↓
Collect evidence
 ↓
AI explanation
```

Possible answer:

> "Branch A generates 14% less revenue and has a higher employee-cost ratio than Branch B. Its order volume is also lower. The largest observed differences are employee cost and order volume."

---

## 21. Recommendation

The recommendation engine considers the evidence.

Example:

```text
Problem:
Employee cost ratio high

Evidence:
Employee Cost +22%
Revenue +5%
```

Recommendation:

> Review staffing and scheduling patterns at the affected branch and investigate whether staffing levels align with demand.

---

## 22. Dashboard Presentation

The user sees:

```text
┌──────────────────────────────────────┐
│        OVERALL BUSINESS              │
├──────────┬──────────┬───────────────┤
│ Revenue  │ Profit   │ Employees     │
├──────────┼──────────┼───────────────┤
│ ₹54L     │ ₹10.4L   │ 78            │
└──────────┴──────────┴───────────────┘

Branch Performance

Branch A   █████████
Branch B   ████████████
Branch C   ███████
```

Then:

```text
Business Issues
```

and:

```text
Ask Your Data
```

---

## 23. Report Generation

The system combines:

```text
Company Performance
+
Branch Performance
+
Employee Analytics
+
Financial Analysis
+
Historical Trends
+
Problems
+
Drivers
+
Recommendations
```

into a business report.

---

## 24. Complete System Flow

```text
                    USER
                     │
                     ↓
              Create Business
                     │
                     ↓
               Add Branches
                     │
                     ↓
                Upload Data
                     │
                     ↓
              File Validation
                     │
                     ↓
              Data Profiling
                     │
                     ↓
             Entity Detection
                     │
                     ↓
             Data Quality
                     │
                     ↓
              Data Cleaning
                     │
                     ↓
             Semantic Mapping
                     │
                     ↓
          Business Semantic Layer
                     │
                     ↓
           Historical Matching
                     │
                     ↓
             Analytics Engine
                     │
          ┌──────────┼──────────┐
          ↓          ↓          ↓
       Company     Branch     Employee
       Analysis   Analysis    Analysis
          │          │          │
          └──────────┼──────────┘
                     ↓
           Cross-Branch Comparison
                     ↓
           Historical Comparison
                     ↓
             Problem Detection
                     ↓
              Driver Analysis
                     ↓
           Recommendation Engine
                     ↓
               AI Interpreter
                     ↓
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
   Dashboard        Q&A          Reports
```

---

## 25. The Most Important Change From the Previous PRD

Previously, the product was essentially:

> **"Analyze my business data."**

The updated product is:

> **"Understand my entire business."**

That means the central analytical model is no longer just:

**Sales → Revenue → Customers → Products**

It becomes:

**Business → Branches → People → Operations → Revenue → Costs → Profitability → Historical Performance**

This direction gives a much stronger portfolio story: this is not simply an
Excel-to-AI dashboard; it is a **business intelligence layer that connects
internal operations and external performance across multiple branches.**
