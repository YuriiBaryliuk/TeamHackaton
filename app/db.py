"""SQLite connection, schema and small read helpers.

We use the standard-library sqlite3 module: no ORM, the SQL is right here.
Every request opens its own short-lived connection (cheap for SQLite),
which avoids sharing one connection across FastAPI's worker threads.
"""
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("KROPKA_DB", BASE_DIR / "data" / "kropka.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS points (
  id            TEXT PRIMARY KEY,        -- short slug, e.g. 'krk-0001' (used in the QR URL)
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL,           -- city_toilet | partner | pink_box | school | university | pharmacy | shop
  lat           REAL NOT NULL,
  lon           REAL NOT NULL,
  address       TEXT,
  access        TEXT NOT NULL,           -- open | ask_staff | students_only
  entry_fee_pln REAL DEFAULT 0,
  opening_hours TEXT NOT NULL,           -- JSON, see urgent.parse_opening_hours
  wheelchair    INTEGER DEFAULT 0,
  has_products  INTEGER DEFAULT 0,       -- 1 if known to host a box
  has_qr        INTEGER DEFAULT 0,
  city          TEXT NOT NULL DEFAULT 'krakow',
  is_demo       INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  point_id    TEXT NOT NULL REFERENCES points(id),
  type        TEXT NOT NULL,             -- took | empty | refilled
  source      TEXT NOT NULL,             -- qr | geo | steward | partner
  device_hash TEXT NOT NULL,             -- salted hash of an anonymous cookie id, for rate limiting only
  created_at  TEXT NOT NULL,             -- ISO 8601 UTC
  is_demo     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS urgent_searches (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  lat_r       REAL NOT NULL,             -- rounded to 3 decimals (~100 m) for privacy
  lon_r       REAL NOT NULL,
  found       INTEGER NOT NULL,          -- 1 if a fresh in-stock point was within 10 min walk
  nearest_min REAL,
  created_at  TEXT NOT NULL,
  is_demo     INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_point_time ON events(point_id, created_at);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """All timestamps are stored as ISO 8601 UTC strings, e.g. 2026-10-03T14:00:00+00:00.
    Same format everywhere means string order equals time order."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection. Rows behave like dicts (row["name"])."""
    target = str(path) if path is not None else str(DB_PATH)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist yet. Safe to call on every start."""
    conn.executescript(SCHEMA)
    conn.commit()


def fetch_points(conn: sqlite3.Connection, city: str = "krakow") -> list[dict]:
    rows = conn.execute("SELECT * FROM points WHERE city = ? ORDER BY id", (city,))
    return [dict(r) for r in rows]


def fetch_point(conn: sqlite3.Connection, point_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM points WHERE id = ?", (point_id,)).fetchone()
    return dict(row) if row else None


def fetch_events(conn: sqlite3.Connection, point_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT type, source, created_at FROM events WHERE point_id = ? ORDER BY created_at", (point_id,)
    )
    return [dict(r) for r in rows]


def insert_event(conn: sqlite3.Connection, point_id: str, type_: str, source: str, device_hash: str,
                 created_at: datetime) -> None:
    conn.execute(
        "INSERT INTO events (point_id, type, source, device_hash, created_at, is_demo) VALUES (?, ?, ?, ?, ?, 0)",
        (point_id, type_, source, device_hash, to_iso(created_at)),
    )
    conn.commit()


def fetch_events_by_point(conn: sqlite3.Connection, city: str = "krakow") -> dict[str, list[dict]]:
    """All events of a city's points, grouped by point id, oldest first."""
    rows = conn.execute(
        """SELECT e.point_id, e.type, e.source, e.created_at
           FROM events e JOIN points p ON p.id = e.point_id
           WHERE p.city = ?
           ORDER BY e.point_id, e.created_at""",
        (city,),
    )
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["point_id"]].append(dict(r))
    return grouped
