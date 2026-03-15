"""Repository for NMCK calculation history stored in SQLite."""

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    region TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in_progress',
    total_nmck REAL DEFAULT 0,
    items_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    cte_name TEXT NOT NULL,
    cte_category TEXT DEFAULT '',
    cte_id INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'in_progress',
    current_step TEXT DEFAULT 'init',

    -- Results
    nmck_per_unit REAL,
    total_nmck REAL,
    coefficient_of_variation REAL,
    is_homogeneous INTEGER,
    median_price REAL,
    weighted_average_price REAL,
    price_range_min REAL,
    price_range_max REAL,
    num_prices_used INTEGER,

    -- User decisions (JSON)
    approved_analog_ids TEXT DEFAULT '[]',
    selected_units TEXT DEFAULT '[]',
    manual_cte_ids TEXT DEFAULT '[]',
    manual_prices TEXT DEFAULT '[]',
    approved_price_indices TEXT DEFAULT '[]',

    -- Document
    document_path TEXT,

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,

    FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
);
"""


class HistoryRepository:
    _db_path: Path | None = None

    @classmethod
    def init(cls, db_path: Path) -> None:
        cls._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = cls._connect()
        conn.executescript(_CREATE_TABLES)
        conn.close()
        logger.info("History DB initialized at %s", db_path)

    @classmethod
    def _connect(cls) -> sqlite3.Connection:
        conn = sqlite3.connect(str(cls._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── Purchases ──

    @classmethod
    def create_purchase(cls, region: str, items_count: int) -> int:
        conn = cls._connect()
        cur = conn.execute(
            "INSERT INTO purchases (region, items_count) VALUES (?, ?)",
            (region, items_count),
        )
        pid = cur.lastrowid
        conn.commit()
        conn.close()
        return pid

    @classmethod
    def list_purchases(
        cls, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> tuple[list[dict], int]:
        conn = cls._connect()
        where = ""
        params: list = []
        if status:
            where = "WHERE p.status = ?"
            params.append(status)

        total = conn.execute(
            f"SELECT COUNT(*) FROM purchases p {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT p.* FROM purchases p
            {where}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        purchases = []
        for row in rows:
            p = dict(row)
            calcs = conn.execute(
                "SELECT * FROM calculations WHERE purchase_id = ? ORDER BY id",
                (p["id"],),
            ).fetchall()
            p["calculations"] = [cls._calc_to_dict(c) for c in calcs]
            purchases.append(p)

        conn.close()
        return purchases, total

    @classmethod
    def get_purchase(cls, purchase_id: int) -> dict | None:
        conn = cls._connect()
        row = conn.execute(
            "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        p = dict(row)
        calcs = conn.execute(
            "SELECT * FROM calculations WHERE purchase_id = ? ORDER BY id",
            (purchase_id,),
        ).fetchall()
        p["calculations"] = [cls._calc_to_dict(c) for c in calcs]
        conn.close()
        return p

    @classmethod
    def delete_purchase(cls, purchase_id: int) -> bool:
        conn = cls._connect()
        cur = conn.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted

    @classmethod
    def get_recent(cls, limit: int = 3) -> list[dict]:
        purchases, _ = cls.list_purchases(limit=limit, offset=0)
        return purchases

    # ── Calculations ──

    @classmethod
    def create_calculation(
        cls,
        purchase_id: int,
        session_id: str,
        cte_name: str,
        cte_category: str,
        cte_id: int,
    ) -> int:
        conn = cls._connect()
        cur = conn.execute(
            """INSERT INTO calculations
               (purchase_id, session_id, cte_name, cte_category, cte_id)
               VALUES (?, ?, ?, ?, ?)""",
            (purchase_id, session_id, cte_name, cte_category, cte_id),
        )
        calc_id = cur.lastrowid
        conn.commit()
        conn.close()
        return calc_id

    @classmethod
    def update_step(cls, session_id: str, step: str) -> None:
        conn = cls._connect()
        conn.execute(
            "UPDATE calculations SET current_step = ? WHERE session_id = ?",
            (step, session_id),
        )
        conn.commit()
        conn.close()

    @classmethod
    def save_decisions(cls, session_id: str, decisions: dict) -> None:
        conn = cls._connect()
        sets = []
        params = []
        for key in (
            "approved_analog_ids",
            "selected_units",
            "manual_cte_ids",
            "manual_prices",
            "approved_price_indices",
        ):
            if key in decisions:
                sets.append(f"{key} = ?")
                params.append(json.dumps(decisions[key], ensure_ascii=False))
        if sets:
            params.append(session_id)
            conn.execute(
                f"UPDATE calculations SET {', '.join(sets)} WHERE session_id = ?",
                params,
            )
            conn.commit()
        conn.close()

    @classmethod
    def complete_calculation(cls, session_id: str, result: dict) -> None:
        conn = cls._connect()
        conn.execute(
            """UPDATE calculations SET
                status = 'completed',
                current_step = 'document_generated',
                nmck_per_unit = ?,
                total_nmck = ?,
                coefficient_of_variation = ?,
                is_homogeneous = ?,
                median_price = ?,
                weighted_average_price = ?,
                price_range_min = ?,
                price_range_max = ?,
                num_prices_used = ?,
                document_path = ?,
                completed_at = datetime('now')
            WHERE session_id = ?""",
            (
                result.get("nmck_per_unit"),
                result.get("total_nmck"),
                result.get("coefficient_of_variation"),
                1 if result.get("is_homogeneous") else 0,
                result.get("median_price"),
                result.get("weighted_average_price"),
                result.get("price_range_min"),
                result.get("price_range_max"),
                result.get("num_prices_used"),
                result.get("document_path"),
                session_id,
            ),
        )

        # Update parent purchase totals
        row = conn.execute(
            "SELECT purchase_id FROM calculations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            pid = row["purchase_id"]
            stats = conn.execute(
                """SELECT
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as done,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN total_nmck ELSE 0 END), 0) as total
                FROM calculations WHERE purchase_id = ?""",
                (pid,),
            ).fetchone()
            done = stats["done"]
            total = stats["total"]
            items = conn.execute(
                "SELECT items_count FROM purchases WHERE id = ?", (pid,)
            ).fetchone()
            new_status = (
                "completed" if items and done >= items["items_count"] else "in_progress"
            )
            conn.execute(
                """UPDATE purchases SET
                    completed_count = ?, total_nmck = ?, status = ?
                WHERE id = ?""",
                (done, total, new_status, pid),
            )

        conn.commit()
        conn.close()

    @classmethod
    def _calc_to_dict(cls, row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in (
            "approved_analog_ids",
            "selected_units",
            "manual_cte_ids",
            "manual_prices",
            "approved_price_indices",
        ):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
            else:
                d[key] = []
        d["is_homogeneous"] = bool(d.get("is_homogeneous"))
        return d
