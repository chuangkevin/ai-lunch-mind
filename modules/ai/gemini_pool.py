# modules/ai/gemini_pool.py
"""
Gemini API Key Pool Manager - SQLite-based key rotation with cooldown and usage tracking.

Features:
1. SQLite-based API key storage (shares cache.db with existing cache manager)
2. Random key selection from active, non-cooldown keys
3. Automatic 429/ResourceExhausted retry with key rotation
4. Bad key cooldown (default 2 minutes)
5. Per-key usage tracking (suffix only for security)
6. Thread-safe for concurrent search threads
7. auto_retry decorator for transparent key management
"""

import functools
import logging
import os
import random
import re
import sqlite3
import threading
import time
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Default database path (same as existing cache manager)
DB_PATH = os.environ.get("CACHE_DB_PATH", "cache.db")

# Key validation constants
KEY_PREFIX = "AIza"
KEY_MIN_LENGTH = 20

# Default cooldown for rate-limited keys
DEFAULT_COOLDOWN_SECONDS = 120


class GeminiPoolExhausted(Exception):
    """Raised when all API keys in the pool have been exhausted (rate-limited or unavailable)."""
    pass


class GeminiKeyPool:
    """Thread-safe Gemini API key pool with SQLite storage, random selection, and cooldown."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    # ------------------------------------------------------------------
    # Database initialisation
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new SQLite connection (check_same_thread=False for thread safety)."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_database(self):
        """Create tables if they do not exist."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        api_key TEXT NOT NULL UNIQUE,
                        status TEXT DEFAULT 'active',
                        cooldown_until REAL DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS api_key_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key_suffix TEXT NOT NULL,
                        model TEXT,
                        call_type TEXT,
                        prompt_tokens INTEGER DEFAULT 0,
                        completion_tokens INTEGER DEFAULT 0,
                        total_tokens INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_api_key_usage_suffix
                    ON api_key_usage(key_suffix)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_api_key_usage_created
                    ON api_key_usage(created_at)
                """)
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Key selection
    # ------------------------------------------------------------------

    def _available_keys_query(
        self,
        exclude_key: Optional[str] = None,
        exclude_keys: Optional[Set[str]] = None,
    ) -> tuple:
        """Build query and params for selecting available keys."""
        now = time.time()
        conditions = ["status = 'active'", "cooldown_until < ?"]
        params: list = [now]

        if exclude_key:
            conditions.append("api_key != ?")
            params.append(exclude_key)

        if exclude_keys:
            placeholders = ",".join("?" for _ in exclude_keys)
            conditions.append(f"api_key NOT IN ({placeholders})")
            params.extend(exclude_keys)

        sql = "SELECT api_key FROM api_keys WHERE " + " AND ".join(conditions)
        return sql, tuple(params)

    def get_key(self) -> Optional[str]:
        """Randomly select an active, non-cooldown key. Returns None if none available."""
        with self._lock:
            conn = self._get_conn()
            try:
                sql, params = self._available_keys_query()
                rows = conn.execute(sql, params).fetchall()
                if not rows:
                    logger.warning("GeminiKeyPool: 沒有可用的 API key")
                    return None
                chosen = random.choice(rows)["api_key"]
                logger.debug("GeminiKeyPool: 選擇 key ...%s", chosen[-4:])
                return chosen
            finally:
                conn.close()

    def get_key_excluding(self, failed_key: str) -> Optional[str]:
        """Randomly select an active key, excluding *failed_key*."""
        with self._lock:
            conn = self._get_conn()
            try:
                sql, params = self._available_keys_query(exclude_key=failed_key)
                rows = conn.execute(sql, params).fetchall()
                if not rows:
                    logger.warning("GeminiKeyPool: 排除 ...%s 後沒有可用 key", failed_key[-4:])
                    return None
                chosen = random.choice(rows)["api_key"]
                logger.debug("GeminiKeyPool: 替換為 key ...%s", chosen[-4:])
                return chosen
            finally:
                conn.close()

    def get_key_excluding_all(self, tried_keys: Set[str]) -> Optional[str]:
        """Randomly select an active key, excluding ALL keys in *tried_keys*. Thread-safe."""
        with self._lock:
            conn = self._get_conn()
            try:
                sql, params = self._available_keys_query(exclude_keys=tried_keys)
                rows = conn.execute(sql, params).fetchall()
                if not rows:
                    logger.warning(
                        "GeminiKeyPool: 排除 %d 個已嘗試 key 後沒有可用 key",
                        len(tried_keys),
                    )
                    return None
                chosen = random.choice(rows)["api_key"]
                logger.debug("GeminiKeyPool: 選擇 key ...%s (已排除 %d 個)", chosen[-4:], len(tried_keys))
                return chosen
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Cooldown / mark bad
    # ------------------------------------------------------------------

    def mark_bad(self, key: str, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        """Put a key into cooldown for *cooldown_seconds*."""
        until = time.time() + cooldown_seconds
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE api_keys SET cooldown_until = ? WHERE api_key = ?",
                    (until, key),
                )
                conn.commit()
                logger.info(
                    "GeminiKeyPool: key ...%s 冷卻 %ds",
                    key[-4:],
                    cooldown_seconds,
                )
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def add_keys(self, keys_text: str, validate: bool = True) -> Dict[str, int]:
        """Parse multiline text, validate, and insert keys.

        Args:
            keys_text: Multiline text with one API key per line.
            validate: If True, call validate_key() for each key before inserting.

        Returns {"added": N, "duplicates": N, "invalid": N, "validated": N, "validation_failed": N}.
        """
        lines = [line.strip() for line in keys_text.splitlines()]
        lines = [line for line in lines if line]  # drop blanks

        added = 0
        duplicates = 0
        invalid = 0
        validated = 0
        validation_failed = 0

        with self._lock:
            conn = self._get_conn()
            try:
                for raw_key in lines:
                    if not raw_key.startswith(KEY_PREFIX) or len(raw_key) < KEY_MIN_LENGTH:
                        invalid += 1
                        logger.debug("GeminiKeyPool: 無效 key 格式: ...%s", raw_key[-4:] if len(raw_key) >= 4 else raw_key)
                        continue

                    if validate:
                        # Release lock during validation (network call)
                        # We must release and re-acquire to avoid blocking other threads
                        pass  # validation done outside lock below

                    try:
                        conn.execute(
                            "INSERT INTO api_keys (api_key) VALUES (?)",
                            (raw_key,),
                        )
                        added += 1
                        logger.info("GeminiKeyPool: 新增 key ...%s", raw_key[-4:])
                    except sqlite3.IntegrityError:
                        duplicates += 1
                        logger.debug("GeminiKeyPool: 重複 key ...%s", raw_key[-4:])
                conn.commit()
            finally:
                conn.close()

        # Validate keys outside the lock (network I/O should not hold the lock)
        if validate and added > 0:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT api_key FROM api_keys WHERE status = 'active'").fetchall()
                keys_to_validate = []
                for row in rows:
                    # Only validate newly added keys (check against the lines we just processed)
                    if row["api_key"] in lines:
                        keys_to_validate.append(row["api_key"])
            finally:
                conn.close()

            for key in keys_to_validate:
                if self.validate_key(key):
                    validated += 1
                else:
                    validation_failed += 1
                    # Deactivate invalid keys
                    with self._lock:
                        conn = self._get_conn()
                        try:
                            conn.execute(
                                "UPDATE api_keys SET status = 'invalid' WHERE api_key = ?",
                                (key,),
                            )
                            conn.commit()
                            logger.warning("GeminiKeyPool: key ...%s 驗證失敗，已停用", key[-4:])
                        finally:
                            conn.close()

        result = {
            "added": added,
            "duplicates": duplicates,
            "invalid": invalid,
            "validated": validated,
            "validation_failed": validation_failed,
        }
        logger.info("GeminiKeyPool: add_keys 結果 %s", result)
        return result

    def remove_key(self, suffix: str):
        """Delete a key by its suffix.

        If multiple keys share the same suffix, raises ValueError asking for a more
        specific suffix instead of silently deleting all matches.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                # Find keys whose suffix matches
                rows = conn.execute(
                    "SELECT api_key FROM api_keys WHERE api_key LIKE ?",
                    (f"%{suffix}",),
                ).fetchall()
                if not rows:
                    logger.warning("GeminiKeyPool: 找不到後綴為 %s 的 key", suffix)
                    return
                if len(rows) > 1:
                    logger.warning(
                        "GeminiKeyPool: 後綴 %s 匹配到 %d 個 key，請提供更長的後綴以避免誤刪",
                        suffix,
                        len(rows),
                    )
                    raise ValueError(
                        f"後綴 '{suffix}' 匹配到 {len(rows)} 個 key，請提供更具體的後綴"
                    )
                conn.execute("DELETE FROM api_keys WHERE api_key = ?", (rows[0]["api_key"],))
                logger.info("GeminiKeyPool: 移除 key ...%s", rows[0]["api_key"][-4:])
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Status / stats
    # ------------------------------------------------------------------

    def get_key_status(self) -> List[Dict]:
        """Return status for every key: suffix, status, cooldown remaining, today's usage."""
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT api_key, status, cooldown_until FROM api_keys ORDER BY id"
                ).fetchall()

                result = []
                for row in rows:
                    suffix = row["api_key"][-4:]
                    cooldown_remaining = max(0, row["cooldown_until"] - now)

                    # Today's usage count
                    usage_row = conn.execute(
                        """
                        SELECT COUNT(*) as cnt FROM api_key_usage
                        WHERE key_suffix = ? AND date(created_at) = date('now')
                        """,
                        (suffix,),
                    ).fetchone()
                    usage_today = usage_row["cnt"] if usage_row else 0

                    result.append({
                        "suffix": suffix,
                        "status": row["status"],
                        "cooldown_remaining": round(cooldown_remaining, 1),
                        "usage_today": usage_today,
                    })
                return result
            finally:
                conn.close()

    def get_usage_stats(self) -> Dict:
        """Aggregated usage counts for today, last 7 days, and last 30 days."""
        with self._lock:
            conn = self._get_conn()
            try:
                def _count(days: int) -> int:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) as cnt FROM api_key_usage
                        WHERE created_at >= datetime('now', ?)
                        """,
                        (f"-{days} days",),
                    ).fetchone()
                    return row["cnt"] if row else 0

                today = conn.execute(
                    "SELECT COUNT(*) as cnt FROM api_key_usage WHERE date(created_at) = date('now')"
                ).fetchone()

                # Token totals
                token_row = conn.execute(
                    """
                    SELECT
                        COALESCE(SUM(prompt_tokens), 0) as prompt,
                        COALESCE(SUM(completion_tokens), 0) as completion,
                        COALESCE(SUM(total_tokens), 0) as total
                    FROM api_key_usage
                    WHERE date(created_at) = date('now')
                    """
                ).fetchone()

                return {
                    "today": today["cnt"] if today else 0,
                    "last_7_days": _count(7),
                    "last_30_days": _count(30),
                    "today_tokens": {
                        "prompt": token_row["prompt"],
                        "completion": token_row["completion"],
                        "total": token_row["total"],
                    },
                }
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def track_usage(
        self,
        key: str,
        model: Optional[str] = None,
        call_type: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ):
        """Insert a usage record. Only stores the key suffix for security."""
        suffix = key[-4:] if key else "????"
        total_tokens = prompt_tokens + completion_tokens

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO api_key_usage
                        (key_suffix, model, call_type, prompt_tokens, completion_tokens, total_tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (suffix, model, call_type, prompt_tokens, completion_tokens, total_tokens),
                )
                conn.commit()
                logger.debug(
                    "GeminiKeyPool: 記錄用量 ...%s model=%s tokens=%d",
                    suffix, model, total_tokens,
                )
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Key validation
    # ------------------------------------------------------------------

    def validate_key(self, key: str) -> bool:
        """Make a tiny test call to the Gemini API to verify the key works.

        Uses per-request api_key parameter to avoid global state pollution.
        Returns True if the key is valid, False otherwise.
        """
        try:
            from google import genai

            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents="test",
            )
            logger.info("GeminiKeyPool: key ...%s 驗證成功", key[-4:])
            return True
        except Exception as e:
            logger.warning("GeminiKeyPool: key ...%s 驗證失敗: %s", key[-4:], e)
            return False

    # ------------------------------------------------------------------
    # auto_retry decorator
    # ------------------------------------------------------------------

    def auto_retry(self, func: Optional[Callable] = None):
        """Decorator that injects ``api_key`` kwarg and retries on 429 / ResourceExhausted.

        Usage::

            @gemini_pool.auto_retry
            def call_gemini(prompt, *, api_key=None):
                genai.configure(api_key=api_key)
                ...

        The decorator will:
        1. Pick an available key and pass it as ``api_key``.
        2. On 429 or ResourceExhausted, mark the key bad, pick another, retry.
        3. Loop until no new key can be obtained.
        4. Raise GeminiPoolExhausted if all keys are exhausted.
        """
        # Support both @auto_retry and @auto_retry() syntax
        if func is None:
            return self.auto_retry  # called as @auto_retry() — return self

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tried_keys: Set[str] = set()

            while True:
                key = self.get_key_excluding_all(tried_keys)
                if key is None:
                    raise GeminiPoolExhausted(
                        f"GeminiKeyPool: 所有 API key 都已耗盡 (已嘗試 {len(tried_keys)} 個)"
                    )
                tried_keys.add(key)

                kwargs["api_key"] = key
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not self._is_rate_limit_error(exc):
                        raise
                    logger.warning(
                        "GeminiKeyPool: key ...%s 遭遇 429/ResourceExhausted (已嘗試 %d 個 key)",
                        key[-4:],
                        len(tried_keys),
                    )
                    self.mark_bad(key)
                    continue

        return wrapper

    # Pattern for matching HTTP 429 in error strings — must appear in a
    # recognisable context, not just any occurrence of the digits "429".
    _RATE_LIMIT_PATTERN = re.compile(
        r"(?:status|HTTP|code[:\s])\s*429"
        r"|Resource has been exhausted"
        r"|quota",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """Check if an exception is a 429 / ResourceExhausted error."""
        # google.api_core.exceptions.ResourceExhausted
        exc_type_name = type(exc).__name__
        if exc_type_name == "ResourceExhausted":
            return True

        # Check for google.api_core.exceptions hierarchy
        try:
            from google.api_core.exceptions import ResourceExhausted
            if isinstance(exc, ResourceExhausted):
                return True
        except ImportError:
            pass

        # Check HTTP status code attribute (e.g. google-api-core exceptions have .code)
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code == 429:
            return True

        # String-based matching with precise patterns
        exc_str = str(exc)
        if GeminiKeyPool._RATE_LIMIT_PATTERN.search(exc_str):
            return True

        return False


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
gemini_pool = GeminiKeyPool()
