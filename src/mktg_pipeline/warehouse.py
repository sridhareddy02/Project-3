"""Build the SQLite warehouse (staging, core, mart) by running the SQL files in order."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .generate import END, EXTRACT_DATE, START
from .ingest import Staging

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def _iso(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in columns:
        out[c] = out[c].dt.strftime("%Y-%m-%d %H:%M:%S" if c == "created_at" else "%Y-%m-%d")
    return out


def render(sql: str, start: str, end: str, extract_date: str) -> str:
    return sql.replace("{{start}}", start).replace("{{end}}", end).replace("{{extract_date}}", extract_date)


def build(stg: Staging, db_path: str | Path = ":memory:", start: str = START, end: str = END,
          extract_date: str = EXTRACT_DATE) -> sqlite3.Connection:
    """Load staging tables, then run ``10_core.sql`` and ``20_mart.sql``."""
    con = sqlite3.connect(str(db_path))
    for name, df, date_cols in (
        ("stg_ads", stg.ads, ["date"]),
        ("stg_web", stg.web, ["date"]),
        ("stg_leads", stg.leads, ["created_at", "created_date"]),
        ("stg_orders", stg.orders, ["order_date"]),
    ):
        _iso(df, date_cols).to_sql(name, con, index=False, if_exists="replace")
    for f in ("10_core.sql", "20_mart.sql"):
        con.executescript(render((SQL_DIR / f).read_text(), start, end, extract_date))
    con.commit()
    return con


def dashboard_extract(con: sqlite3.Connection, faulty: bool) -> pd.DataFrame:
    """Revenue by channel as the dashboard would see it (correct or with the join fan-out bug)."""
    name = "30_dashboard_faulty.sql" if faulty else "30_dashboard_correct.sql"
    return pd.read_sql_query((SQL_DIR / name).read_text(), con)


def read_table(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {name}", con)
