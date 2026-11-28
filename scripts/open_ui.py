"""
Open the project database in the DuckDB UI (a notebook-style SQL editor
that runs in your web browser, on your own computer).

Usage (from the project root):
    python scripts/open_ui.py

Your browser opens at http://localhost:4213 with the database attached.
Browse schemas and tables on the left, and write SQL in the cells.

IMPORTANT: while the UI is open, the database is LOCKED for other programs.
`dbt build` and `load_bronze.py` will fail with a lock error until you
come back to this terminal and press Enter to close the UI.

The first run downloads the UI extension, so it needs an internet connection.
"""

import os
from pathlib import Path

import duckdb

DEFAULT_DB = Path.home() / "duckdb" / "database_to_dashboard.duckdb"
DB_PATH = Path(os.environ.get("D2D_DB_PATH", DEFAULT_DB))

if not DB_PATH.exists():
    raise SystemExit(f"No database at {DB_PATH}. Run:  python scripts/load_bronze.py")

con = duckdb.connect(str(DB_PATH))
con.sql("CALL start_ui()")
print(f"DuckDB UI is open in your browser (http://localhost:4213) on:\n  {DB_PATH}")
input("\nPress Enter here to close the UI and unlock the database... ")
con.sql("CALL stop_ui_server()")
con.close()
print("Closed. The database is unlocked.")
