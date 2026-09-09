# Product Requirements Document (PRD)

## AI Business Intelligence & Analysis Copilot

**Version:** 2.0
**Product Type:** SaaS Web Application
**Initial Target:** Small and medium-sized businesses
**Initial Vertical:** Restaurants / Multi-branch businesses
**Initial Data Sources:** Excel and CSV
**Primary Users:** Business owners, managers, operations managers, finance managers

---

## 1. Product Overview

The **AI Business Intelligence & Analysis Copilot** is a web-based analytics platform that allows business owners and managers to upload their existing business data and understand the performance of their **entire business** without requiring SQL, Python, statistics, or data-analysis expertise.

The platform analyzes both:

### External / Business Performance

* Revenue
* Sales
* Orders
* Customers
* Products
* Categories
* Discounts
* Taxes
* Service charges
* Delivery
* Customer ratings
* Sales channels

### Internal / Operational Performance

* Employees
* Salaries
* Employee count
* Departments
* Roles
* Attendance
* Overtime
* Incentives
* Labor costs
* Operating expenses
* Branch operations

### Organizational Performance

* Branch performance
* Branch-to-branch comparison
* Department comparison
* Company-wide performance
* Historical branch performance
* Overall business profitability

The system converts raw business data into:

> **What is happening → Why it is happening → What the business should focus on**

---

## 2. Problem Statement

Businesses often have large amounts of data spread across multiple Excel files and systems.

For example:

```text
Sales.xlsx
Employees.xlsx
Expenses.xlsx
Branches.xlsx
Inventory.xlsx
Customers.xlsx
```

Business owners may know how to operate their business but may not know how to analyze all of this information together.

A business owner may want to ask:

> "Which branch is performing best?"

> "Why is Branch A less profitable than Branch B?"

> "How much are we spending on salaries across all branches?"

> "Which branch has the highest employee cost compared with revenue?"

> "Why did our overall profit decrease this month?"

Today, answering these questions often requires manually combining spreadsheets or depending on an analyst.

The product aims to make this analysis accessible through an easy-to-use interface and natural-language interaction.

---

## 3. Product Vision

> **Give every business owner an intelligent analyst that can understand their business data, identify important changes, compare branches and operations, explain supported drivers, and help them make better decisions.**

The product should answer questions across the entire organization rather than analyzing individual spreadsheets in isolation.

---

## 4. Core Product Principle

### AI interprets. Analytics calculates. Evidence supports.

The LLM should **not be responsible for critical mathematical calculations**.

Instead:

```text
Raw Data
   ↓
Data Processing
   ↓
Analytics Engine
   ↓
Calculated Metrics
   ↓
Evidence
   ↓
AI
   ↓
Business Explanation
```

For example:

The analytics engine calculates:

```text
Revenue = ₹21,00,000
Employee Cost = ₹4,80,000
Employee Cost Ratio = 22.86%
```

The AI explains:

> "Branch B generates ₹21L in revenue while employee costs account for approximately 22.9% of revenue."

---

## 5. Target Users

### Primary

#### Business Owner

Needs:

* Overall business performance
* Branch comparison
* Profitability
* Employee costs
* Major problems
* Trends
* Recommendations

#### Branch Manager

Needs:

* Branch performance
* Employees
* Sales
* Expenses
* Operational metrics
* Comparisons with other branches

#### Operations Manager

Needs:

* Branch efficiency
* Employee costs
* Attendance
* Operational expenses
* Performance trends

#### Finance / Business Manager

Needs:

* Revenue
* Expenses
* Profit
* Cost structure
* Branch profitability
* Historical comparisons

---

## 6. Product Scope

The product will have five major analytical areas.

### A. Business Performance

```text
Revenue
Sales
Orders
Customers
Products
Categories
Discounts
Taxes
Fees
Channels
```

### B. Financial Performance

```text
Revenue
COGS
Employee Cost
Operating Expenses
Gross Profit
Operating Profit
Net Profit
Margins
```

Only metrics supported by the available data will be calculated.

---

### C. Employee & Internal Operations

```text
Employees
Departments
Roles
Salary
Attendance
Overtime
Incentives
Employee Cost
Employee Productivity
```

Possible analysis:

```text
Salary by Branch
Salary by Department
Salary by Role
Employee Count by Branch
Average Salary
Employee Cost %
Revenue per Employee
Profit per Employee
```

---

### D. Branch Intelligence

The system should support:

```text
Branch A
Branch B
Branch C
...
```

and:

```text
All Branches
```

Users should be able to analyze:

* Individual branch
* Multiple branches
* All branches
* Branch rankings
* Branch comparisons
* Branch trends

---

### E. Historical Intelligence

The system should maintain historical datasets.

For example:

```text
2026
 ├── January
 ├── February
 ├── March
 ├── April
 └── May
```

Users can compare:

* Month vs previous month
* Month vs same month last year
* Quarter vs quarter
* Year vs year
* Branch vs branch
* Department vs department
* Custom periods

---

## 7. Business Hierarchy

The system should understand the organization as a connected structure.

```text
Business
│
├── Branches
│   │
│   ├── Branch A
│   │   ├── Employees
│   │   ├── Sales
│   │   ├── Expenses
│   │   ├── Customers
│   │   └── Products
│   │
│   ├── Branch B
│   │   ├── Employees
│   │   ├── Sales
│   │   ├── Expenses
│   │   ├── Customers
│   │   └── Products
│   │
│   └── Branch C
│
└── Overall Business
```

This allows the system to move between:

**Company → Branch → Department → Employee**

where the uploaded data supports those relationships.

---

## 8. Data Upload

Users can upload:

* `.xlsx`
* `.xls` where supported
* `.csv`

The system should not require one rigid spreadsheet format.

Example:

### File 1

```text
employee_id
employee_name
branch
role
salary
```

### File 2

```text
emp_id
name
location
designation
monthly_pay
```

The semantic engine attempts to map both into common business concepts.

---

## 9. Data Profiling

After upload, the system analyzes:

* Number of rows
* Number of columns
* Data types
* Missing values
* Duplicate records
* Unique values
* Date fields
* Numeric ranges
* Categorical values
* Possible identifiers
* Possible relationships
* Branch values
* Employee identifiers
* Financial fields

Example:

```text
Rows: 12,450

Columns:
18

Potential entities:
Employee
Branch
Transaction

Potential measures:
Revenue
Salary
Discount
Tax

Potential dimensions:
Branch
Role
Department
Date
```

---

## 10. Data Quality Engine

The system identifies problems before analysis.

### Critical

Examples:

* Empty file
* Corrupted file
* Required relationship unavailable
* Invalid financial values
* Missing period information

### Warning

Examples:

* Missing salaries
* Duplicate employees
* Unknown branch
* Missing dates
* Inconsistent branch names

### Informational

Examples:

* New column detected
* New branch detected
* New employee role detected

The user should see understandable explanations rather than technical error messages.

---

## 11. Data Cleaning

The system may identify:

```text
Jubilee Hills
jubilee hills
Jubilee-Hills
JUBILEE HILLS
```

as potentially referring to the same branch.

Likewise:

```text
Manager
manager
Mgr
```

may represent the same role.

However, ambiguous transformations should not silently change business data.

The system should:

1. Detect
2. Suggest
3. Show the user when confirmation is needed
4. Preserve the original data
5. Record transformations

---

## 12. Semantic Engine

This is one of the most important components.

The system must understand what columns actually represent.

It should use:

### Column names

```text
salary
monthly_salary
pay
wage
```

### Data type

```text
numeric
date
text
identifier
```

### Values

For example:

```text
45000
38000
52000
```

### Statistical patterns

### Relationships

### Business vocabulary

### Business type

### Existing historical mappings

---

## 13. Canonical Business Concepts

The semantic engine maps different names to standard concepts.

Example:

```text
food_sales
sales_amount
revenue
total_sales
```

may map to appropriate revenue concepts depending on context.

Employee examples:

```text
salary
monthly_salary
pay
wages
```

→

```text
EMPLOYEE_COMPENSATION
```

Branch examples:

```text
branch
location
store
outlet
branch_name
```

→

```text
BRANCH
```

Employee identifiers:

```text
emp_id
employee_id
staff_id
```

→

```text
EMPLOYEE_ID
```

---

## 14. Confidence-Based Mapping

The system should not blindly map every column.

Example:

```text
salary → EMPLOYEE_COMPENSATION
Confidence: High
```

But:

```text
extra → ?
```

may have:

```text
Confidence: Low
```

The system asks:

> What does "extra" represent?

Options:

* Service charge
* Delivery fee
* Employee incentive
* Other expense
* Ignore

The user's correction should be saved for future datasets where appropriate.

---

## 15. Employee Analytics

If employee data exists, the system can calculate supported metrics such as:

### Workforce

* Employee count
* Employees by branch
* Employees by department
* Employees by role

### Compensation

* Total salary cost
* Average salary
* Salary by branch
* Salary by department
* Salary by role

### Efficiency

Where the data supports it:

```text
Revenue per Employee
Profit per Employee
Employee Cost / Revenue
Sales per Employee
```

The system should not automatically interpret salary as a business expense in every accounting context without validating the business model/data semantics.

---

## 16. Branch Analytics

Each branch gets its own analytical profile.

Example:

```text
Branch B

Revenue: ₹21L
Orders: 5,100
Employees: 24
Employee Cost: ₹4.8L
Operating Expenses: ₹6.2L
Profit: ₹5.4L
```

Then the user can compare:

```text
Branch A
vs
Branch B
vs
Branch C
```

---

## 17. Cross-Branch Comparison

The comparison engine should support metrics such as:

| Metric        | Branch A | Branch B | Branch C |
| ------------- | -------: | -------: | -------: |
| Revenue       |     ₹18L |     ₹21L |     ₹15L |
| Employees     |       28 |       24 |       26 |
| Employee Cost |    ₹6.2L |    ₹4.8L |    ₹5.1L |
| Orders        |    4,200 |    5,100 |    3,700 |
| Profit        |    ₹3.1L |    ₹5.4L |    ₹1.9L |

The system can identify patterns such as:

> Branch B generates the highest revenue and profit while having the lowest employee cost among the three branches.

This statement must be supported by the calculated metrics.

---

## 18. Company-Wide Analysis

The owner should be able to select:

### All Branches

and see:

```text
Total Revenue
Total Expenses
Total Employee Cost
Total Orders
Total Employees
Overall Profit
Overall Margin
```

where the required data exists.

The system should also allow drill-down:

```text
Company
 ↓
Branch
 ↓
Department
 ↓
Employee
```

---

## 19. Historical Intelligence

Every uploaded dataset should be associated with:

```text
Business
Period
Branch
Dataset
Dataset Version
Schema
Semantic Mapping
Metrics
Insights
```

Example:

```text
2026
 ├── January
 │   ├── Branch A
 │   ├── Branch B
 │   └── Branch C
 │
 ├── February
 │   ├── Branch A
 │   ├── Branch B
 │   └── Branch C
 │
 └── March
```

The UI can look like folders/months, but the database should use structured entities rather than physical folders.

---

## 20. Schema Changes

January:

```text
food_sales
service_charge
gst
total
```

February:

```text
food_revenue
service_fee
tax
bill_amount
```

The semantic engine maps both to the same concepts where justified.

If February introduces:

```text
delivery_fee
```

the system detects a new business concept.

It can tell the user:

> "A new delivery fee field was detected in February. Would you like to include it in cost/revenue comparisons?"

---

## 21. Problem Detection

The system should automatically detect meaningful patterns.

Examples:

### Revenue vs Profit

```text
Revenue ↑ 11%
Profit ↓ 14%
```

Insight:

> Revenue increased, but profitability declined.

### Employee Cost

```text
Revenue ↑ 8%
Employee Cost ↑ 21%
```

Insight:

> Employee costs are growing faster than revenue.

### Branch Performance

```text
Branch B
Revenue ↑ 15%
Employee Cost ↑ 4%
Profit ↑ 19%
```

Insight:

> Branch B improved profitability while employee costs grew more slowly than revenue.

---

## 22. Driver Analysis

The system should attempt to identify **supported drivers**, not blindly claim causes.

Example:

```text
Profit ↓
     │
     ├── Food Cost ↑
     ├── Employee Cost ↑
     └── Discounts ↑
```

Then drill down:

```text
Food Cost
   ↓
Category
   ↓
Chicken
   ↓
Cost increased 32%
```

The system can say:

> "Chicken-related costs showed the largest increase among the analyzed categories."

It should **not** automatically say:

> "Your supplier increased prices."

unless supplier-price data actually supports that conclusion.

---

## 23. Fact vs Driver vs Hypothesis

Every insight should distinguish:

### Fact

> Employee cost increased 18%.

### Supported Driver

> Branch A contributed 72% of the total employee-cost increase.

### Hypothesis

> Higher staffing levels may have contributed to the increase.

This prevents misleading AI-generated explanations.

---

## 24. Natural Language Q&A

Users can ask:

> "Which branch is performing best?"

> "How much are we spending on salaries?"

> "Compare employee costs across branches."

> "Why did profit fall in March?"

> "Which branch has the highest salary-to-revenue ratio?"

> "How is Branch A performing compared with Branch B?"

> "What changed this month?"

The workflow:

```text
User Question
↓
Intent Detection
↓
Semantic Mapping
↓
Analysis Plan
↓
SQL/Python Analytics
↓
Evidence
↓
AI Interpretation
↓
Answer
```

---

## 25. Evidence-Based Answers

Every important AI answer should be backed by visible evidence.

Example:

### AI Answer

> Branch B is currently the strongest-performing branch.

### Evidence

```text
Revenue: ₹21L
Profit: ₹5.4L
Employee Cost: ₹4.8L
Employee Cost Ratio: 22.9%
```

### View Calculation

The user can inspect how the metric was calculated.

---

## 26. Recommendation Engine

Recommendations should be generated from detected business patterns.

Example:

```text
Problem:
Employee Cost ↑ 22%

Evidence:
Revenue ↑ 5%
Employee Count ↑ 18%
```

Potential recommendation:

> Review staffing levels and scheduling at Branch A, particularly during periods where employee utilization is low.

Recommendations should be presented as **decision support**, not guaranteed solutions.

---

## 27. Dashboard

### Company Overview

```text
Revenue
Profit
Expenses
Employee Cost
Orders
Employees
```

### Branch Performance

```text
Branch Ranking
Revenue
Profit
Cost
Employee Cost
Growth
```

### Internal Operations

```text
Employees
Salary
Departments
Roles
Attendance
Labor Cost
```

### Business Performance

```text
Revenue Trends
Product Performance
Customer Performance
Costs
Profitability
```

### Historical Comparison

```text
Month
Quarter
Year
Branch
```

### Problems

```text
Revenue ↓
Profit ↓
Costs ↑
Employee Cost ↑
Branch Underperformance
```

### Ask Your Data

Natural-language interface.

---

## 28. Reports

The system can generate business reports containing:

1. Executive Summary
2. Overall KPIs
3. Branch Performance
4. Revenue Analysis
5. Expense Analysis
6. Employee & Salary Analysis
7. Profitability
8. Product/Category Analysis
9. Customer Analysis
10. Historical Comparison
11. Major Business Issues
12. Supported Drivers
13. Recommendations
14. Data Quality
15. Methodology

---

## 29. Database Architecture

The database should be relational and multi-tenant.

Core entities:

```text
users
businesses
branches
departments
employees

datasets
dataset_versions
columns
semantic_mappings
quality_issues

transactions
sales
expenses
employee_costs

metrics
comparisons
insights
recommendations
reports
```

Not every table needs to exist in the first implementation; the actual transactional schema should evolve according to supported data sources.

---

## 30. Important Data Relationships

Example:

```text
Business
   │
   ├── Branch
   │      │
   │      ├── Employees
   │      │
   │      ├── Sales
   │      │
   │      ├── Expenses
   │      │
   │      └── Customers
   │
   └── Overall Metrics
```

Employee:

```text
Employee
 ├── Employee ID
 ├── Branch
 ├── Department
 ├── Role
 ├── Compensation
 └── Attendance
```

Transaction:

```text
Transaction
 ├── Date
 ├── Branch
 ├── Product
 ├── Quantity
 ├── Revenue
 ├── Discount
 ├── Tax
 └── Other Charges
```

---

## 31. Architecture

```text
                Excel / CSV
                    ↓
              File Parser
                    ↓
             Data Profiler
                    ↓
           Data Quality Engine
                    ↓
             Cleaning Engine
                    ↓
             Semantic Engine
                    ↓
        Business Semantic Layer
                    ↓
          Historical Data Store
                    ↓
              Analytics Engine
                    ↓
           Comparison Engine
                    ↓
           Problem Detection
                    ↓
            Driver Analysis
                    ↓
        Recommendation Engine
                    ↓
             AI Interpreter
                    ↓
       ┌────────────┼─────────────┐
       ↓            ↓             ↓
   Dashboard      Q&A          Reports
```

---

## 32. Technology Stack

### Frontend

* React
* Tailwind CSS
* Plotly

### Backend

* FastAPI
* Python

### Data Processing

* Pandas
* NumPy
* OpenPyXL
* PyArrow

### Database

* PostgreSQL

### Analytics

* Python
* SQL
* Statistical analysis

### AI

* LLM API

### Deployment

* Docker

---

## 33. Security

The system must provide:

* Authentication
* Business-level data isolation
* Secure file handling
* Encryption in transit
* Protected storage
* Controlled file access
* Audit logging
* Data deletion
* Role-based access as team functionality expands

One business must never be able to access another business's data.

---

## 34. Error Handling

The system must explicitly handle:

```text
Invalid File
Empty File
Unsupported Format
Missing Date
Missing Branch
Ambiguous Column
Duplicate Data
Insufficient Data
Missing Salary Data
Missing Revenue Data
Comparison Unavailable
Schema Changed
Analysis Failed
```

The system should never silently fail.

---

## 35. V1 Scope

The first production version should focus on:

```text
Authentication
      ↓
Business Workspace
      ↓
Branch Setup
      ↓
Excel/CSV Upload
      ↓
Data Profiling
      ↓
Data Quality
      ↓
Cleaning
      ↓
Semantic Mapping
      ↓
Employee + Branch + Sales Data
      ↓
Core KPIs
      ↓
Historical Storage
      ↓
Branch Comparison
      ↓
Company-Wide Analysis
      ↓
Basic Problem Detection
      ↓
Dashboard
```

---

## 36. V2

Add:

* Natural-language Q&A
* Driver analysis
* Recommendation engine
* Automated reports
* Advanced employee analytics
* More operational analytics
* Advanced historical analysis

---

## 37. V3

Add:

* Retail
* E-commerce
* Hotels
* Salons
* Service businesses
* POS integrations
* Accounting integrations
* Automated data synchronization
* Forecasting
* Advanced anomaly detection

---

## 38. Product Success Criteria

The product should allow a business owner to answer:

> **How is my business performing?**

> **Which branch is performing best?**

> **Which branch is performing worst?**

> **How much are we spending on employees?**

> **Which branch has the highest employee cost?**

> **Is employee cost growing faster than revenue?**

> **What changed compared with last month?**

> **Why did profit change?**

> **What are the biggest problems?**

> **What should I investigate next?**

without requiring the owner to write SQL or Python.
