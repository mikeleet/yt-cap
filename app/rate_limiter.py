import time
import asyncio
import threading
from app.db import get_setting


class RateLimiter:
    def __init__(self):
        self._semaphore = threading.Semaphore(1)
        self._last_request = 0.0
        self._hour_window: list[float] = []
        self._day_window: list[float] = []
        self._lock = threading.Lock()

    def _get_concurrency(self) -> int:
        try:
            return int(get_setting("max_concurrent_fetches") or "1")
        except (ValueError, TypeError):
            return 1

    def _get_interval(self) -> float:
        try:
            return float(get_setting("min_interval_seconds") or "10")
        except (ValueError, TypeError):
            return 10.0

    def _get_max_hour(self) -> int:
        try:
            return int(get_setting("max_per_hour") or "200")
        except (ValueError, TypeError):
            return 200

    def _get_max_day(self) -> int:
        try:
            return int(get_setting("max_per_day") or "5000")
        except (ValueError, TypeError):
            return 5000

    def acquire(self):
        interval = self._get_interval()
        max_hour = self._get_max_hour()
        max_day = self._get_max_day()

        with self._lock:
            elapsed = time.time() - self._last_request
            if elapsed < interval:
                time.sleep(interval - elapsed)

            now = time.time()
            self._hour_window = [t for t in self._hour_window if now - t < 3600]
            self._day_window = [t for t in self._day_window if now - t < 86400]

            while len(self._hour_window) >= max_hour:
                sleep_for = 3600 - (now - self._hour_window[0]) + 0.1
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                self._hour_window = [t for t in self._hour_window if now - t < 3600]

            while len(self._day_window) >= max_day:
                sleep_for = 86400 - (now - self._day_window[0]) + 0.1
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                self._day_window = [t for t in self._day_window if now - t < 86400]

            self._hour_window.append(now)
            self._day_window.append(now)
            self._last_request = now

    async def async_acquire(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.acquire)


rate_limiter = RateLimiter()
