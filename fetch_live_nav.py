"""
fetch_live_nav.py
=================
Fetches live NAV data from mfapi.in API for 5 selected mutual fund schemes.

API used  : https://api.mfapi.in  (free, no auth required)
Endpoints :
    GET /mf/{scheme_code}/latest  → latest NAV only
    GET /mf/{scheme_code}         → full NAV history + scheme meta

Output:
    - Prints live NAV summary table to console
    - Saves results to  live_nav_latest.csv   (latest NAV)
    - Saves results to  live_nav_history.csv  (30-day history)
    - Saves results to  live_nav.db           (SQLite)

Run:
    python fetch_live_nav.py
"""

import sqlite3
import time
import urllib.request
import urllib.error
import json
from datetime import datetime, timedelta
from pathlib import Path

# ── 5 Selected Schemes (from your fund_master dataset) ───────────────────────
# Format: (amfi_code / scheme_code, friendly label)
SCHEMES = [
    (119551, "SBI Bluechip Fund - Regular - Growth"),
    (119552, "SBI Bluechip Fund - Direct - Growth"),
    (119598, "SBI Small Cap Fund - Regular - Growth"),
    (120503, "Axis Flexi Cap Fund - Direct - Growth"),
    (125497, "HDFC Top 100 Fund - Direct - Growth"),
]

BASE_URL = "https://api.mfapi.in/mf"
OUTPUT_DIR = Path(__file__).parent          # same folder as this script


# ── HTTP helper (uses stdlib only — no requests needed) ──────────────────────
def fetch_json(url: str, retries: int = 3, delay: float = 2.0) -> dict:
    """GET a URL and return parsed JSON. Retries on network errors."""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MF-NAV-Fetcher/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} on {url}  (attempt {attempt}/{retries})")
        except urllib.error.URLError as e:
            print(f"  Network error: {e.reason}  (attempt {attempt}/{retries})")
        except Exception as e:
            print(f"  Unexpected error: {e}  (attempt {attempt}/{retries})")

        if attempt < retries:
            time.sleep(delay)

    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


# ── Fetch latest NAV for one scheme ──────────────────────────────────────────
def fetch_latest_nav(scheme_code: int, label: str) -> dict:
    url = f"{BASE_URL}/{scheme_code}/latest"
    print(f"  Fetching latest NAV → {url}")
    data = fetch_json(url)

    meta = data.get("meta", {})
    nav_entry = data.get("data", [{}])[0]

    return {
        "scheme_code":      scheme_code,
        "label":            label,
        "fund_house":       meta.get("fund_house", ""),
        "scheme_name":      meta.get("scheme_name", ""),
        "scheme_category":  meta.get("scheme_category", ""),
        "nav_date":         nav_entry.get("date", ""),
        "nav":              float(nav_entry.get("nav", 0)),
        "fetched_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Fetch NAV history for one scheme (last N days) ───────────────────────────
def fetch_nav_history(scheme_code: int, label: str, days: int = 30) -> list[dict]:
    url = f"{BASE_URL}/{scheme_code}"
    print(f"  Fetching NAV history → {url}")
    data = fetch_json(url)

    meta     = data.get("meta", {})
    all_nav  = data.get("data", [])

    # Filter to last `days` calendar days
    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    for entry in all_nav:
        try:
            nav_date = datetime.strptime(entry["date"], "%d-%m-%Y")
        except ValueError:
            continue
        if nav_date >= cutoff:
            rows.append({
                "scheme_code":  scheme_code,
                "label":        label,
                "fund_house":   meta.get("fund_house", ""),
                "scheme_name":  meta.get("scheme_name", ""),
                "date":         nav_date.strftime("%Y-%m-%d"),
                "nav":          float(entry["nav"]),
            })

    # Sort oldest → newest
    rows.sort(key=lambda r: r["date"])
    return rows


# ── Save to CSV (stdlib only) ─────────────────────────────────────────────────
def save_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        print(f"  No data to save → {path}")
        return
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} rows → {path.name}")


# ── Save to SQLite ────────────────────────────────────────────────────────────
def save_to_db(latest_rows: list[dict], history_rows: list[dict], db_path: Path) -> None:
    conn = sqlite3.connect(db_path)

    # Latest NAV table
    conn.execute("DROP TABLE IF EXISTS live_nav_latest")
    conn.execute("""
        CREATE TABLE live_nav_latest (
            scheme_code     INTEGER,
            label           TEXT,
            fund_house      TEXT,
            scheme_name     TEXT,
            scheme_category TEXT,
            nav_date        TEXT,
            nav             REAL,
            fetched_at      TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO live_nav_latest VALUES (:scheme_code,:label,:fund_house,"
        ":scheme_name,:scheme_category,:nav_date,:nav,:fetched_at)",
        latest_rows
    )

    # History table
    conn.execute("DROP TABLE IF EXISTS live_nav_history")
    conn.execute("""
        CREATE TABLE live_nav_history (
            scheme_code INTEGER,
            label       TEXT,
            fund_house  TEXT,
            scheme_name TEXT,
            date        TEXT,
            nav         REAL
        )
    """)
    conn.executemany(
        "INSERT INTO live_nav_history VALUES "
        "(:scheme_code,:label,:fund_house,:scheme_name,:date,:nav)",
        history_rows
    )

    conn.commit()
    conn.close()
    print(f"  Saved to SQLite → {db_path.name}")


# ── Pretty print summary table ────────────────────────────────────────────────
def print_summary(latest_rows: list[dict]) -> None:
    print("\n" + "=" * 72)
    print(f"  LIVE NAV SUMMARY  —  fetched at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)
    print(f"  {'SCHEME':<42} {'NAV DATE':<12} {'NAV (₹)':>10}")
    print("  " + "-" * 68)
    for r in latest_rows:
        name = r["scheme_name"][:42]
        print(f"  {name:<42} {r['nav_date']:<12} {r['nav']:>10.4f}")
    print("=" * 72)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'─'*60}")
    print("  mfapi.in Live NAV Fetcher")
    print(f"  Fetching data for {len(SCHEMES)} schemes")
    print(f"{'─'*60}\n")

    latest_rows  = []
    history_rows = []
    errors       = []

    for scheme_code, label in SCHEMES:
        print(f"\n[{scheme_code}] {label}")
        try:
            # Latest NAV
            latest = fetch_latest_nav(scheme_code, label)
            latest_rows.append(latest)

            # 30-day history
            history = fetch_nav_history(scheme_code, label, days=30)
            history_rows.extend(history)
            print(f"  ✓ NAV: ₹{latest['nav']:.4f}  |  Date: {latest['nav_date']}"
                  f"  |  History: {len(history)} days")

            time.sleep(0.5)   # be polite to the free API

        except Exception as e:
            print(f"  ✗ Error: {e}")
            errors.append((scheme_code, label, str(e)))

    # ── Save outputs ──────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  Saving outputs...")

    save_csv(latest_rows,  OUTPUT_DIR / "live_nav_latest.csv")
    save_csv(history_rows, OUTPUT_DIR / "live_nav_history.csv")
    save_to_db(latest_rows, history_rows, OUTPUT_DIR / "live_nav.db")

    # ── Print summary ─────────────────────────────────────────────────────────
    print_summary(latest_rows)

    if errors:
        print(f"\n⚠  {len(errors)} scheme(s) failed:")
        for code, label, err in errors:
            print(f"   [{code}] {label} — {err}")
    else:
        print(f"\n✅  All {len(SCHEMES)} schemes fetched successfully!")
        print(f"    Output files saved to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
