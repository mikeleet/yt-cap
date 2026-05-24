import sqlite3
import os
import threading

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "ytcap.db")

_local = threading.local()
_write_lock = threading.Lock()

_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE")


def _is_write(sql: str) -> bool:
    s = sql.strip().upper()
    return any(s.startswith(kw) for kw in _WRITE_PREFIXES)


class _SafeConn:
    """Thread-local SQLite connection. close() is a no-op.
    Writes are serialized through a global lock — only 1 writer at a time."""

    def __init__(self):
        os.makedirs(DB_DIR, exist_ok=True)
        self._raw = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        self._raw.row_factory = sqlite3.Row
        self._raw.execute("PRAGMA journal_mode=WAL")
        self._raw.execute("PRAGMA busy_timeout=5000")

    def execute(self, sql, params=None):
        if _is_write(sql):
            with _write_lock:
                if params:
                    return self._raw.execute(sql, params)
                return self._raw.execute(sql)
        else:
            if params:
                return self._raw.execute(sql, params)
            return self._raw.execute(sql)

    def executescript(self, sql):
        return self._raw.executescript(sql)

    def commit(self):
        self._raw.commit()

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._raw, name)


def get_db() -> _SafeConn:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _SafeConn()
        _local.conn = conn
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id      TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            handle          TEXT,
            thumbnail_url   TEXT,
            auto_update     INTEGER DEFAULT 1,
            update_interval INTEGER DEFAULT 43200,
            total_videos    INTEGER DEFAULT 0,
            captions_ok     INTEGER DEFAULT 0,
            captions_failed INTEGER DEFAULT 0,
            last_scan_at    TEXT,
            last_download_at TEXT,
            last_sync_at    TEXT,
            sync_status     TEXT DEFAULT 'idle',
            error_message   TEXT,
            current_video_id TEXT,
            current_video_title TEXT,
            progress_done   INTEGER DEFAULT 0,
            progress_total  INTEGER DEFAULT 0,
            current_phase   TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS videos (
            video_id        TEXT PRIMARY KEY,
            channel_id      TEXT NOT NULL,
            title           TEXT,
            url             TEXT,
            thumbnail_url   TEXT,
            duration_sec    INTEGER,
            publish_date    TEXT,
            caption_status  TEXT DEFAULT 'none',
            caption_lang    TEXT,
            caption_text    TEXT,
            caption_chars   INTEGER,
            never_download  INTEGER DEFAULT 0,
            retry_count     INTEGER DEFAULT 0,
            last_error      TEXT,
            first_seen_at   TEXT DEFAULT (datetime('now')),
            caption_at      TEXT,
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
        CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(caption_status);
    """)

    defaults = {
        "max_concurrent_fetches": "1",
        "min_interval_seconds": "10",
        "max_per_hour": "200",
        "max_per_day": "5000",
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", [k, v]
        )


def get_setting(key: str) -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", [key]).fetchone()
    return row[0] if row else ""


def set_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", [key, value]
    )
