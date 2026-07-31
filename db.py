"""SQLite 存储:users / subscriptions。"""
import sqlite3
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL DEFAULT 'price',
    asset TEXT NOT NULL,
    op TEXT NOT NULL DEFAULT 'gt',
    threshold REAL NOT NULL,
    filter TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);
"""


class DB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()

    def _migrate(self):
        """旧库迁移:旧表无 filter 列且 op 有 CHECK 限制 → 重建表(保留数据)。"""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(subscriptions)")]
        if "filter" in cols:
            return
        self._conn.executescript(
            """
            ALTER TABLE subscriptions RENAME TO subscriptions_old;
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT 'price',
                asset TEXT NOT NULL,
                op TEXT NOT NULL DEFAULT 'gt',
                threshold REAL NOT NULL,
                filter TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL
            );
            INSERT INTO subscriptions(id, user_id, category, asset, op, threshold, filter, status, created_at)
                SELECT id, user_id, category, asset, op, threshold, '', status, created_at
                FROM subscriptions_old;
            DROP TABLE subscriptions_old;
            CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);
            """
        )
        self._conn.commit()

    def register_user(self, user_id: int, username: str | None) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO users(user_id, username, created_at) VALUES(?,?,?)",
            (user_id, username, int(time.time())),
        )
        self._conn.commit()

    def add_subscription(
        self,
        user_id: int,
        category: str,
        asset: str,
        op: str,
        threshold: float,
        filter: str = "",
    ) -> int:
        # 加密货币资产转大写;RSS 的 asset 是 URL,保持原样
        asset_norm = asset.upper() if category in ("price", "whale") else asset
        cur = self._conn.execute(
            "INSERT INTO subscriptions(user_id, category, asset, op, threshold, filter, status, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, 'active', ?)",
            (user_id, category, asset_norm, op, threshold, filter, int(time.time())),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_subscriptions(self, user_id: int | None = None) -> list[dict]:
        if user_id is None:
            rows = self._conn.execute(
                "SELECT * FROM subscriptions WHERE status='active' ORDER BY id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM subscriptions WHERE status='active' AND user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_subscription(self, sub_id: int, user_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE subscriptions SET status='deleted' WHERE id=? AND user_id=?",
            (sub_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self):
        self._conn.close()
