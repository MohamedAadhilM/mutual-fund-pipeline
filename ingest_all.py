"""
data_ingestion.py
=============
Ingests all 10 Mutual Fund CSV datasets into a single SQLite database.

Usage:
    python ingest_all.py                      # uses default paths
    python ingest_all.py --csv-dir ./data --db mf.db

Output:
    mutual_fund.db  (SQLite) with 10 tables + row-count summary
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Per-dataset configuration ────────────────────────────────────────────────
# Each entry defines:
#   file        : CSV filename
#   table       : target SQLite table name
#   date_cols   : columns to parse as dates
#   dtype       : explicit dtypes for pandas (avoids mis-detection)
#   pk          : primary-key column(s) for the CREATE TABLE index hint
DATASETS = [
    {
        "file": "01_fund_master.csv",
        "table": "fund_master",
        "date_cols": ["launch_date"],
        "dtype": {"amfi_code": int, "sebi_category_code": str},
        "pk": ["amfi_code"],
    },
    {
        "file": "02_nav_history.csv",
        "table": "nav_history",
        "date_cols": ["date"],
        "dtype": {"amfi_code": int},
        "pk": ["amfi_code", "date"],
    },
    {
        "file": "03_aum_by_fund_house.csv",
        "table": "aum_by_fund_house",
        "date_cols": ["date"],
        "dtype": {},
        "pk": ["date", "fund_house"],
    },
    {
        "file": "04_monthly_sip_inflows.csv",
        "table": "monthly_sip_inflows",
        "date_cols": [],           # 'month' is YYYY-MM string; keep as text
        "dtype": {},
        "pk": ["month"],
    },
    {
        "file": "05_category_inflows.csv",
        "table": "category_inflows",
        "date_cols": [],           # 'month' is YYYY-MM string
        "dtype": {},
        "pk": ["month", "category"],
    },
    {
        "file": "06_industry_folio_count.csv",
        "table": "industry_folio_count",
        "date_cols": [],           # 'month' is YYYY-MM string
        "dtype": {},
        "pk": ["month"],
    },
    {
        "file": "07_scheme_performance.csv",
        "table": "scheme_performance",
        "date_cols": [],
        "dtype": {"amfi_code": int},
        "pk": ["amfi_code"],
    },
    {
        "file": "08_investor_transactions.csv",
        "table": "investor_transactions",
        "date_cols": ["transaction_date"],
        "dtype": {"amfi_code": int},
        "pk": [],                  # no natural single PK; row-id is implicit
    },
    {
        "file": "09_portfolio_holdings.csv",
        "table": "portfolio_holdings",
        "date_cols": ["portfolio_date"],
        "dtype": {"amfi_code": int},
        "pk": ["amfi_code", "stock_symbol"],
    },
    {
        "file": "10_benchmark_indices.csv",
        "table": "benchmark_indices",
        "date_cols": ["date"],
        "dtype": {},
        "pk": ["date", "index_name"],
    },
]


# ── Validation helpers ────────────────────────────────────────────────────────
def validate_fund_master(df: pd.DataFrame) -> pd.DataFrame:
    """Business-rule checks for fund_master."""
    bad_expense = df[df["expense_ratio_pct"] < 0]
    if not bad_expense.empty:
        log.warning("fund_master: %d rows with negative expense_ratio_pct", len(bad_expense))

    bad_exit = df[df["exit_load_pct"] < 0]
    if not bad_exit.empty:
        log.warning("fund_master: %d rows with negative exit_load_pct", len(bad_exit))

    dupes = df[df.duplicated("amfi_code")]
    if not dupes.empty:
        log.warning("fund_master: %d duplicate amfi_code rows – keeping first", len(dupes))
        df = df.drop_duplicates("amfi_code", keep="first")

    return df


def validate_nav_history(df: pd.DataFrame) -> pd.DataFrame:
    bad_nav = df[df["nav"] <= 0]
    if not bad_nav.empty:
        log.warning("nav_history: %d rows with nav <= 0 – dropping", len(bad_nav))
        df = df[df["nav"] > 0]
    return df


def validate_investor_transactions(df: pd.DataFrame) -> pd.DataFrame:
    bad_amt = df[df["amount_inr"] <= 0]
    if not bad_amt.empty:
        log.warning(
            "investor_transactions: %d rows with amount_inr <= 0 – dropping", len(bad_amt)
        )
        df = df[df["amount_inr"] > 0]

    valid_types = {"SIP", "Lumpsum", "Redemption", "STP", "SWP"}
    unknown = df[~df["transaction_type"].isin(valid_types)]
    if not unknown.empty:
        log.warning(
            "investor_transactions: %d rows with unknown transaction_type: %s",
            len(unknown),
            unknown["transaction_type"].unique().tolist(),
        )
    return df


VALIDATORS = {
    "fund_master": validate_fund_master,
    "nav_history": validate_nav_history,
    "investor_transactions": validate_investor_transactions,
}


# ── Core ingestion ────────────────────────────────────────────────────────────
def load_csv(cfg: dict, csv_dir: Path) -> pd.DataFrame:
    """Read one CSV with schema-aware settings."""
    path = csv_dir / cfg["file"]
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(
        path,
        dtype=cfg.get("dtype") or None,
        parse_dates=cfg["date_cols"] if cfg["date_cols"] else False,
    )

    # Normalise column names: strip whitespace, lowercase
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Strip leading/trailing whitespace from string columns
    str_cols = df.select_dtypes(include="object").columns
    df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())

    log.info("  Loaded %s  →  %d rows × %d cols", cfg["file"], *df.shape)
    return df


def write_to_db(df: pd.DataFrame, table: str, conn: sqlite3.Connection) -> int:
    """Write DataFrame to SQLite, replacing any existing table."""
    df.to_sql(table, conn, if_exists="replace", index=False)
    n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    return n


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create useful indexes after all tables are loaded."""
    indexes = [
        ("idx_nav_amfi_date",   "nav_history",           "amfi_code, date"),
        ("idx_nav_date",        "nav_history",           "date"),
        ("idx_txn_amfi",        "investor_transactions", "amfi_code"),
        ("idx_txn_date",        "investor_transactions", "transaction_date"),
        ("idx_txn_investor",    "investor_transactions", "investor_id"),
        ("idx_holdings_amfi",   "portfolio_holdings",    "amfi_code"),
        ("idx_bench_name_date", "benchmark_indices",     "index_name, date"),
        ("idx_aum_date",        "aum_by_fund_house",     "date"),
        ("idx_perf_amfi",       "scheme_performance",    "amfi_code"),
    ]
    for idx_name, table, cols in indexes:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON [{table}] ({cols})"
        )
    conn.commit()
    log.info("Indexes created.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main(csv_dir: Path, db_path: Path) -> None:
    log.info("CSV source : %s", csv_dir.resolve())
    log.info("Database   : %s", db_path.resolve())

    conn = sqlite3.connect(db_path)
    summary = []
    errors  = []

    for cfg in DATASETS:
        table = cfg["table"]
        log.info("── %s ──", cfg["file"])
        try:
            df = load_csv(cfg, csv_dir)

            # Run validator if one is registered
            if table in VALIDATORS:
                df = VALIDATORS[table](df)

            # Null audit
            null_counts = df.isnull().sum()
            cols_with_nulls = null_counts[null_counts > 0]
            if not cols_with_nulls.empty:
                log.warning(
                    "  %s: nulls found → %s",
                    table,
                    cols_with_nulls.to_dict(),
                )

            rows = write_to_db(df, table, conn)
            log.info("  ✓ %s: %d rows written", table, rows)
            summary.append((table, rows, "OK"))

        except Exception as exc:
            log.error("  ✗ %s: %s", table, exc)
            summary.append((table, 0, f"ERROR: {exc}"))
            errors.append((table, exc))

    create_indexes(conn)
    conn.close()

    # ── Summary report ────────────────────────────────────────────────────────
    print("\n" + "=" * 58)
    print(f"{'TABLE':<30} {'ROWS':>8}  STATUS")
    print("=" * 58)
    for table, rows, status in summary:
        print(f"{table:<30} {rows:>8}  {status}")
    print("=" * 58)

    if errors:
        print(f"\n⚠  {len(errors)} dataset(s) failed. Check logs above.")
        sys.exit(1)
    else:
        print(f"\n✅  All 10 datasets ingested → {db_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest mutual fund CSVs into SQLite")
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("."),
        help="Directory containing the 10 CSV files (default: current dir)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("mutual_fund.db"),
        help="Output SQLite database path (default: mutual_fund.db)",
    )
    args = parser.parse_args()
    main(args.csv_dir, args.db)
