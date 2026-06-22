"""
loaders.py
==========
Individual loader functions for each of the 10 Mutual Fund CSV datasets.

Import and call any loader independently, or run this file directly
to ingest a single dataset for testing:

    python loaders.py --dataset nav_history --csv-dir ./data

Each function returns a clean, typed pandas DataFrame ready for
downstream use (analysis, DB write, API, etc.).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 01 · fund_master
# ─────────────────────────────────────────────────────────────────────────────
def load_fund_master(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    01_fund_master.csv
    Master reference for all mutual fund schemes.

    Columns
    -------
    amfi_code           int     AMFI scheme identifier (PK)
    fund_house          str
    scheme_name         str
    category            str     e.g. Equity, Debt, Hybrid
    sub_category        str     e.g. Large Cap, Small Cap
    plan                str     Regular | Direct
    launch_date         date
    benchmark           str     Benchmark index name
    expense_ratio_pct   float
    exit_load_pct       float
    min_sip_amount      int
    min_lumpsum_amount  int
    fund_manager        str
    risk_category       str
    sebi_category_code  str
    """
    path = Path(csv_dir) / "01_fund_master.csv"
    df = pd.read_csv(path, parse_dates=["launch_date"])

    df.columns = df.columns.str.strip().str.lower()
    df["amfi_code"] = df["amfi_code"].astype(int)
    df["sebi_category_code"] = df["sebi_category_code"].astype(str).str.strip()

    # Deduplicate on primary key
    before = len(df)
    df = df.drop_duplicates("amfi_code", keep="first")
    if len(df) < before:
        log.warning("fund_master: dropped %d duplicate amfi_code rows", before - len(df))

    # Sanity checks
    assert (df["expense_ratio_pct"] >= 0).all(), "Negative expense ratios found"
    assert (df["exit_load_pct"] >= 0).all(), "Negative exit loads found"
    assert df["amfi_code"].is_unique, "amfi_code is not unique after dedup"

    log.info("fund_master loaded: %d schemes", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 02 · nav_history
# ─────────────────────────────────────────────────────────────────────────────
def load_nav_history(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    02_nav_history.csv
    Daily NAV time-series for each scheme.

    Columns
    -------
    amfi_code   int     FK → fund_master.amfi_code
    date        date
    nav         float   Net Asset Value (INR)
    """
    path = Path(csv_dir) / "02_nav_history.csv"
    df = pd.read_csv(path, parse_dates=["date"])

    df["amfi_code"] = df["amfi_code"].astype(int)
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")

    # Drop invalid NAV rows
    invalid = df["nav"].isna() | (df["nav"] <= 0)
    if invalid.any():
        log.warning("nav_history: dropping %d rows with nav <= 0 or NaN", invalid.sum())
        df = df[~invalid]

    df = df.sort_values(["amfi_code", "date"]).reset_index(drop=True)

    log.info("nav_history loaded: %d rows | %d schemes | %s – %s",
             len(df), df["amfi_code"].nunique(),
             df["date"].min().date(), df["date"].max().date())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 03 · aum_by_fund_house
# ─────────────────────────────────────────────────────────────────────────────
def load_aum_by_fund_house(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    03_aum_by_fund_house.csv
    Monthly AUM snapshot per fund house.

    Columns
    -------
    date                date
    fund_house          str
    aum_lakh_crore      float
    aum_crore           int
    num_schemes         int
    """
    path = Path(csv_dir) / "03_aum_by_fund_house.csv"
    df = pd.read_csv(path, parse_dates=["date"])

    df["aum_crore"] = df["aum_crore"].astype(int)
    df["num_schemes"] = df["num_schemes"].astype(int)

    # Cross-check: aum_crore ≈ aum_lakh_crore × 100_000
    tolerance = df["aum_crore"] * 0.02          # 2 % tolerance
    mismatch = abs(df["aum_crore"] - df["aum_lakh_crore"] * 100_000) > tolerance
    if mismatch.any():
        log.warning("aum_by_fund_house: %d rows with aum_crore / aum_lakh_crore mismatch",
                    mismatch.sum())

    df = df.sort_values(["date", "fund_house"]).reset_index(drop=True)

    log.info("aum_by_fund_house loaded: %d rows | %d fund houses",
             len(df), df["fund_house"].nunique())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 04 · monthly_sip_inflows
# ─────────────────────────────────────────────────────────────────────────────
def load_monthly_sip_inflows(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    04_monthly_sip_inflows.csv
    Industry-wide SIP statistics per month.

    Columns
    -------
    month                       str     YYYY-MM
    sip_inflow_crore            int
    active_sip_accounts_crore   float
    new_sip_accounts_lakh       float
    sip_aum_lakh_crore          float
    yoy_growth_pct              float   NaN for first 12 months
    """
    path = Path(csv_dir) / "04_monthly_sip_inflows.csv"
    df = pd.read_csv(path)

    df["month"] = df["month"].astype(str).str.strip()
    # Validate YYYY-MM format
    bad = ~df["month"].str.match(r"^\d{4}-\d{2}$")
    if bad.any():
        log.warning("monthly_sip_inflows: %d rows with non-YYYY-MM month value", bad.sum())

    df = df.sort_values("month").reset_index(drop=True)

    log.info("monthly_sip_inflows loaded: %d months | %s – %s",
             len(df), df["month"].iloc[0], df["month"].iloc[-1])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 05 · category_inflows
# ─────────────────────────────────────────────────────────────────────────────
def load_category_inflows(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    05_category_inflows.csv
    Monthly net inflows broken down by fund category.

    Columns
    -------
    month               str     YYYY-MM
    category            str
    net_inflow_crore    float
    """
    path = Path(csv_dir) / "05_category_inflows.csv"
    df = pd.read_csv(path)

    df["month"] = df["month"].astype(str).str.strip()
    df["category"] = df["category"].str.strip()
    df["net_inflow_crore"] = pd.to_numeric(df["net_inflow_crore"], errors="coerce")

    df = df.sort_values(["month", "category"]).reset_index(drop=True)

    log.info("category_inflows loaded: %d rows | %d categories | %s – %s",
             len(df), df["category"].nunique(),
             df["month"].min(), df["month"].max())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 06 · industry_folio_count
# ─────────────────────────────────────────────────────────────────────────────
def load_industry_folio_count(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    06_industry_folio_count.csv
    Quarterly folio counts across asset classes.

    Columns
    -------
    month                   str     YYYY-MM (quarterly)
    total_folios_crore      float
    equity_folios_crore     float
    debt_folios_crore       float
    hybrid_folios_crore     float
    others_folios_crore     float
    """
    path = Path(csv_dir) / "06_industry_folio_count.csv"
    df = pd.read_csv(path)

    df["month"] = df["month"].astype(str).str.strip()

    # Validate sub-totals sum to total (±2 %)
    computed_total = (
        df["equity_folios_crore"]
        + df["debt_folios_crore"]
        + df["hybrid_folios_crore"]
        + df["others_folios_crore"]
    )
    diff_pct = abs(computed_total - df["total_folios_crore"]) / df["total_folios_crore"]
    bad = diff_pct > 0.02
    if bad.any():
        log.warning("industry_folio_count: %d rows where sub-totals don't reconcile", bad.sum())

    df = df.sort_values("month").reset_index(drop=True)

    log.info("industry_folio_count loaded: %d quarters | %s – %s",
             len(df), df["month"].iloc[0], df["month"].iloc[-1])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 07 · scheme_performance
# ─────────────────────────────────────────────────────────────────────────────
def load_scheme_performance(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    07_scheme_performance.csv
    Risk-return metrics per scheme (point-in-time snapshot).

    Columns
    -------
    amfi_code               int
    scheme_name             str
    fund_house              str
    category                str
    plan                    str
    return_1yr_pct          float
    return_3yr_pct          float
    return_5yr_pct          float
    benchmark_3yr_pct       float
    alpha                   float
    beta                    float
    sharpe_ratio            float
    sortino_ratio           float
    std_dev_ann_pct         float
    max_drawdown_pct        float   (negative values = drawdown)
    aum_crore               int
    expense_ratio_pct       float
    morningstar_rating      int     1-5
    risk_grade              str
    """
    path = Path(csv_dir) / "07_scheme_performance.csv"
    df = pd.read_csv(path)

    df["amfi_code"] = df["amfi_code"].astype(int)
    df["morningstar_rating"] = df["morningstar_rating"].astype(int)

    # Validate rating range
    bad_rating = ~df["morningstar_rating"].between(1, 5)
    if bad_rating.any():
        log.warning("scheme_performance: %d rows with Morningstar rating outside 1-5",
                    bad_rating.sum())

    # max_drawdown should be ≤ 0
    positive_dd = df["max_drawdown_pct"] > 0
    if positive_dd.any():
        log.warning("scheme_performance: %d rows with positive max_drawdown_pct (expected ≤ 0)",
                    positive_dd.sum())

    log.info("scheme_performance loaded: %d schemes", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 08 · investor_transactions
# ─────────────────────────────────────────────────────────────────────────────
def load_investor_transactions(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    08_investor_transactions.csv
    Individual investor transaction records.

    Columns
    -------
    investor_id             str
    transaction_date        date
    amfi_code               int
    transaction_type        str     SIP | Lumpsum | Redemption | STP | SWP
    amount_inr              int
    state                   str
    city                    str
    city_tier               str     T30 | B30
    age_group               str
    gender                  str
    annual_income_lakh      float
    payment_mode            str
    kyc_status              str
    """
    path = Path(csv_dir) / "08_investor_transactions.csv"
    df = pd.read_csv(path, parse_dates=["transaction_date"])

    df["amfi_code"] = df["amfi_code"].astype(int)
    df["amount_inr"] = pd.to_numeric(df["amount_inr"], errors="coerce")

    # Drop zero / negative amounts
    invalid = df["amount_inr"].isna() | (df["amount_inr"] <= 0)
    if invalid.any():
        log.warning("investor_transactions: dropping %d rows with amount_inr <= 0", invalid.sum())
        df = df[~invalid]

    df["amount_inr"] = df["amount_inr"].astype(int)

    valid_types = {"SIP", "Lumpsum", "Redemption", "STP", "SWP"}
    unknown = ~df["transaction_type"].isin(valid_types)
    if unknown.any():
        log.warning("investor_transactions: %d rows with unrecognised transaction_type",
                    unknown.sum())

    df = df.sort_values("transaction_date").reset_index(drop=True)

    log.info("investor_transactions loaded: %d rows | %d investors | %s – %s",
             len(df), df["investor_id"].nunique(),
             df["transaction_date"].min().date(),
             df["transaction_date"].max().date())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 09 · portfolio_holdings
# ─────────────────────────────────────────────────────────────────────────────
def load_portfolio_holdings(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    09_portfolio_holdings.csv
    Stock-level holdings for each fund at a given portfolio date.

    Columns
    -------
    amfi_code           int
    stock_symbol        str
    stock_name          str
    sector              str
    weight_pct          float
    market_value_cr     float
    current_price_inr   float
    portfolio_date      date
    """
    path = Path(csv_dir) / "09_portfolio_holdings.csv"
    df = pd.read_csv(path, parse_dates=["portfolio_date"])

    df["amfi_code"] = df["amfi_code"].astype(int)

    # Validate weights per fund sum close to 100 %
    weight_sums = df.groupby("amfi_code")["weight_pct"].sum()
    bad = weight_sums[abs(weight_sums - 100) > 2]           # >2 pp deviation
    if not bad.empty:
        log.warning(
            "portfolio_holdings: %d funds with weights not summing to ~100%%: %s",
            len(bad), bad.to_dict()
        )

    log.info("portfolio_holdings loaded: %d holdings | %d funds | %d stocks",
             len(df), df["amfi_code"].nunique(), df["stock_symbol"].nunique())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 10 · benchmark_indices
# ─────────────────────────────────────────────────────────────────────────────
def load_benchmark_indices(csv_dir: str | Path = ".") -> pd.DataFrame:
    """
    10_benchmark_indices.csv
    Daily closing values for benchmark indices.

    Columns
    -------
    date            date
    index_name      str
    close_value     float
    """
    path = Path(csv_dir) / "10_benchmark_indices.csv"
    df = pd.read_csv(path, parse_dates=["date"])

    df["close_value"] = pd.to_numeric(df["close_value"], errors="coerce")

    invalid = df["close_value"].isna() | (df["close_value"] <= 0)
    if invalid.any():
        log.warning("benchmark_indices: dropping %d rows with close_value <= 0", invalid.sum())
        df = df[~invalid]

    df = df.sort_values(["index_name", "date"]).reset_index(drop=True)

    log.info("benchmark_indices loaded: %d rows | %d indices | %s – %s",
             len(df), df["index_name"].nunique(),
             df["date"].min().date(), df["date"].max().date())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Registry (for programmatic iteration)
# ─────────────────────────────────────────────────────────────────────────────
LOADER_REGISTRY: dict[str, callable] = {
    "fund_master":              load_fund_master,
    "nav_history":              load_nav_history,
    "aum_by_fund_house":        load_aum_by_fund_house,
    "monthly_sip_inflows":      load_monthly_sip_inflows,
    "category_inflows":         load_category_inflows,
    "industry_folio_count":     load_industry_folio_count,
    "scheme_performance":       load_scheme_performance,
    "investor_transactions":    load_investor_transactions,
    "portfolio_holdings":       load_portfolio_holdings,
    "benchmark_indices":        load_benchmark_indices,
}


# ─────────────────────────────────────────────────────────────────────────────
# CLI: test a single loader
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Test a single dataset loader")
    parser.add_argument("--dataset", required=True, choices=LOADER_REGISTRY.keys())
    parser.add_argument("--csv-dir", default=".", type=Path)
    parser.add_argument("--head", type=int, default=5)
    args = parser.parse_args()

    loader = LOADER_REGISTRY[args.dataset]
    df = loader(args.csv_dir)

    print(f"\n── {args.dataset} ({len(df)} rows × {len(df.columns)} cols) ──")
    print(df.head(args.head).to_string())
    print("\nDtypes:")
    print(df.dtypes)
    print("\nNull counts:")
    print(df.isnull().sum()[df.isnull().sum() > 0].to_string() or "  (none)")
