"""
Bronze layer loader
===================

Loads every raw CSV from data/raw/saas/ into a DuckDB database, in a schema
called `bronze`. One bronze table per source file (or file family).

Bronze rules this script follows:
  1. Load data EXACTLY as it arrived: every column is read as text (VARCHAR),
     so nothing gets "helpfully" converted. (Example: the region code "NA"
     stays "NA" instead of becoming NULL.)
  2. Never fix anything here. Cleaning is the silver layer's job.
  3. Add metadata to every row: which file it came from, and when it was loaded.
  4. Keep an audit log of every load run.

This is a FULL REFRESH load: each run rebuilds the bronze tables from the
files. (Incremental loading comes later.)

Run from the project root:
    python scripts/load_bronze.py

Where is the database file?
    By default: <your home folder>/duckdb/database_to_dashboard.duckdb
    (outside OneDrive on purpose: a database file changes constantly while
    in use, and a sync tool can lock or corrupt it).
    Override with an environment variable:  $env:D2D_DB_PATH = "D:\\somewhere\\my.duckdb"
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "saas"
DEFAULT_DB = Path.home() / "duckdb" / "database_to_dashboard.duckdb"
DB_PATH = Path(os.environ.get("D2D_DB_PATH", DEFAULT_DB))

# bronze table name  ->  file (or file pattern) relative to data/raw/saas
# Naming convention: <source system>_<entity>, so you can always tell
# where a table came from.
SOURCES = {
    "crm_accounts":          "crm/accounts.csv",
    "crm_sales_reps":        "crm/sales_reps.csv",
    "billing_products":      "billing/products.csv",
    "billing_subscriptions": "billing/subscriptions.csv",
    "billing_invoices":      "billing/invoices.csv",
    "app_users":             "product_app/users.csv",
    "app_usage_events":      "product_app/usage_events/usage_events_*.csv",   # 46+ monthly files
    "ref_fx_rates_monthly":  "reference/fx_rates_monthly.csv",
}


def load_table(con: duckdb.DuckDBPyConnection, table: str, pattern: str, run_id: str) -> int:
    path = (RAW_ROOT / pattern).as_posix()
    raw_prefix = RAW_ROOT.as_posix() + "/"

    # read_csv options, in plain English:
    #   all_varchar=true    -> every column as text (bronze rule #1)
    #   union_by_name=true  -> combine many files by COLUMN NAME, not position,
    #                          so files that gained a new column still line up
    #                          (older rows just get NULL for it)
    #   filename=true       -> adds a "filename" column saying which file each row came from
    con.execute(f"""
        CREATE OR REPLACE TABLE bronze.{table} AS
        SELECT
            * EXCLUDE (filename),
            replace(filename, '{raw_prefix}', '')  AS _source_file,
            '{run_id}'::VARCHAR                     AS _load_run_id,
            current_timestamp                       AS _loaded_at
        FROM read_csv('{path}',
                      header = true,
                      all_varchar = true,
                      union_by_name = true,
                      filename = true)
    """)
    return con.execute(f"SELECT count(*) FROM bronze.{table}").fetchone()[0]


def main():
    if not RAW_ROOT.exists() or not any(RAW_ROOT.rglob("*.csv")):
        raise SystemExit("No raw CSVs found. Run the generator first:  python generator/generate_saas_data.py")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Database: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))

    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze._load_audit (
            load_run_id   VARCHAR,
            table_name    VARCHAR,
            source_files  VARCHAR,
            row_count     BIGINT,
            seconds       DOUBLE,
            loaded_at     TIMESTAMP
        )
    """)

    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    print(f"Load run: {run_id}\n")
    print(f"  {'bronze table':<24}{'rows':>12}{'files':>8}")
    print(f"  {'-' * 24}{'-' * 12}{'-' * 8}")

    for table, pattern in SOURCES.items():
        start = time.perf_counter()
        rows = load_table(con, table, pattern, run_id)
        secs = time.perf_counter() - start
        n_files = con.execute(f"SELECT count(DISTINCT _source_file) FROM bronze.{table}").fetchone()[0]
        con.execute("INSERT INTO bronze._load_audit VALUES (?, ?, ?, ?, ?, current_timestamp)",
                    [run_id, table, pattern, rows, round(secs, 3)])
        print(f"  {table:<24}{rows:>12,}{n_files:>8}")

    con.close()
    print("\nDone. Bronze layer loaded.")
    print("Next: explore it with   python scripts/run_sql.py sql/01_first_look_bronze.sql")


if __name__ == "__main__":
    main()
