"""
sqlite_store.py — Persist valid items to a SQLite database.

Table schema:
  id           INTEGER PRIMARY KEY AUTOINCREMENT
  title        TEXT NOT NULL
  url          TEXT NOT NULL UNIQUE
  source       TEXT
  collected_at TEXT   (ISO-8601 UTC timestamp)

url is UNIQUE — duplicate URLs are ignored on insert (INSERT OR IGNORE).
"""

import sqlite3
import os
from datetime import datetime, timezone
from src.models import JobContext

EXPORTS_DIR = os.path.join("data", "exports")
DB_PATH = os.path.join(EXPORTS_DIR, "autoscrape.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    source       TEXT,
    collected_at TEXT NOT NULL
);
"""


def run_sqlite_store(ctx: JobContext) -> JobContext:
    """
    Insert ctx.valid_items into the SQLite database.
    Sets ctx.output_paths["sqlite"].
    Appends a decision to ctx.decisions.
    """
    if not ctx.valid_items:
        ctx.decisions.append({
            "layer": "sqlite_store",
            "decision": "skipped",
            "reason": "No valid items to store.",
        })
        return ctx

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    collected_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(CREATE_TABLE_SQL)
        inserted = 0
        for item in ctx.valid_items:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO items (title, url, source, collected_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        item.get("title", ""),
                        item.get("url", ""),
                        item.get("source", ""),
                        collected_at,
                    ),
                )
                if conn.total_changes:
                    inserted += 1
            except sqlite3.Error as exc:
                ctx.warnings.append(f"SQLite insert error for url={item.get('url')}: {exc}")
        conn.commit()

    ctx.output_paths["sqlite"] = DB_PATH
    ctx.decisions.append({
        "layer": "sqlite_store",
        "decision": "stored",
        "reason": (
            f"Inserted {inserted} new item(s) into SQLite at {DB_PATH}. "
            f"Duplicate URLs were ignored (url is UNIQUE)."
        ),
    })
    return ctx
