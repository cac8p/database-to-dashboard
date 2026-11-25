"""
Run a .sql file against the project's DuckDB database and print the results.

Usage (from the project root):
    python scripts/run_sql.py sql/01_first_look_bronze.sql

Statements are separated by semicolons. Each query's result prints as a table.
Lines starting with  -- show:  are printed as headings, so a SQL file can
explain itself as it runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

DEFAULT_DB = Path.home() / "duckdb" / "database_to_dashboard.duckdb"
DB_PATH = Path(os.environ.get("D2D_DB_PATH", DEFAULT_DB))


def statements(sql_text: str):
    """Split a file into statements, keeping any '-- show:' heading with its query."""
    for chunk in sql_text.split(";"):
        lines = chunk.strip().splitlines()
        heading = next((l.split("-- show:", 1)[1].strip() for l in lines if l.strip().startswith("-- show:")), None)
        code = "\n".join(l for l in lines if not l.strip().startswith("--")).strip()
        if code:
            yield heading, code


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/run_sql.py path/to/file.sql")
    if not DB_PATH.exists():
        raise SystemExit(f"No database at {DB_PATH}. Run:  python scripts/load_bronze.py")

    sql_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for heading, code in statements(sql_text):
        print("\n" + "=" * 70)
        print(heading or code.splitlines()[0])
        print("=" * 70)
        try:
            result = con.sql(code)
            if result is not None:
                result.show(max_rows=40, max_width=160)
        except duckdb.Error as e:
            print(f"ERROR: {e}")
    con.close()


if __name__ == "__main__":
    main()
