# Mutual Fund Data Pipeline

A Python-based data ingestion and live NAV fetching project for Indian Mutual Fund datasets.

## Project Structure

```
mutual-fund-pipeline/
├── data/
│   └── raw/                        # 15 raw CSV datasets
│       ├── 01_fund_master.csv
│       ├── 02_nav_history.csv
│       ├── 03_aum_by_fund_house.csv
│       ├── 04_monthly_sip_inflows.csv
│       ├── 05_category_inflows.csv
│       ├── 06_industry_folio_count.csv
│       ├── 07_scheme_performance.csv
│       ├── 08_investor_transactions.csv
│       ├── 09_portfolio_holdings.csv
│       ├── 10_benchmark_indices.csv
│       ├── 11_investor_profile_summary.csv
│       ├── 12_nav_returns_calculated.csv
│       ├── 13_sector_allocation_summary.csv
│       ├── 14_fund_house_performance_summary.csv
│       └── 15_monthly_transaction_summary.csv
├── data_ingestion.py               # Ingest all 15 CSVs into SQLite
├── live_nav_fetch.py               # Fetch live NAV from mfapi.in
├── loaders.py                      # Individual dataset loader functions
└── README.md
```

## Datasets (15 CSV Files)

### Original (10)
| # | File | Description | Rows |
|---|------|-------------|------|
| 01 | fund_master.csv | Scheme master reference | 40 |
| 02 | nav_history.csv | Daily NAV time-series | 46,000 |
| 03 | aum_by_fund_house.csv | Monthly AUM per fund house | 90 |
| 04 | monthly_sip_inflows.csv | Industry SIP statistics | 48 |
| 05 | category_inflows.csv | Monthly inflows by category | 144 |
| 06 | industry_folio_count.csv | Quarterly folio counts | 21 |
| 07 | scheme_performance.csv | Risk-return metrics | 40 |
| 08 | investor_transactions.csv | Investor transactions | 32,778 |
| 09 | portfolio_holdings.csv | Stock-level fund holdings | 322 |
| 10 | benchmark_indices.csv | Daily benchmark index values | 8,050 |

### Derived (5)
| # | File | Description | Rows |
|---|------|-------------|------|
| 11 | investor_profile_summary.csv | Aggregated investor profiles | 5,000 |
| 12 | nav_returns_calculated.csv | NAV with 1d/7d/30d returns + 52w high/low | 45,960 |
| 13 | sector_allocation_summary.csv | Sector-wise allocation across all funds | 14 |
| 14 | fund_house_performance_summary.csv | Fund house level performance metrics | 10 |
| 15 | monthly_transaction_summary.csv | Monthly transaction aggregates by type | 51 |

## Setup & Usage

### 1. Install dependencies
```bash
pip install pandas
```

### 2. Ingest all 15 CSVs into SQLite
```bash
python data_ingestion.py --csv-dir data/raw --db mutual_fund.db
```

### 3. Fetch live NAV from mfapi.in
```bash
python live_nav_fetch.py
```

### 4. Load individual datasets
```bash
python loaders.py --dataset fund_master --csv-dir data/raw
```

## API Source
Live NAV data fetched from [mfapi.in](https://mfapi.in) — free Indian Mutual Fund API (no auth required).

## 5 Schemes Tracked (Live NAV)
| AMFI Code | Scheme |
|-----------|--------|
| 119551 | SBI Bluechip Fund - Regular - Growth |
| 119552 | SBI Bluechip Fund - Direct - Growth |
| 119598 | SBI Small Cap Fund - Regular - Growth |
| 120503 | Axis Flexi Cap Fund - Direct - Growth |
| 125497 | HDFC Top 100 Fund - Direct - Growth |
