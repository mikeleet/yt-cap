import time
import threading

_cooldown_until: float = 0.0
_lock = threading.Lock()


def can_proceed() -> bool:
    """Returns True if no active cooldown. Call before ANY API operation."""
    global _cooldown_until
    with _lock:
        if _cooldown_until == 0:
            return True
        if time.time() >= _cooldown_until:
            _cooldown_until = 0
            return True
        return False


def set_cooldown(seconds: int):
    """Block all API operations for the given number of seconds."""
    global _cooldown_until
    with _lock:
        _cooldown_until = time.time() + seconds


def cooldown_remaining() -> int:
    """Seconds remaining in current cooldown. 0 if none."""
    global _cooldown_until
    with _lock:
        if _cooldown_until == 0:
            return 0
        r = int(_cooldown_until - time.time())
        if r <= 0:
            _cooldown_until = 0
            return 0
        return r


def clear():
    """Force-clear any active cooldown."""
    global _cooldown_until
    with _lock:
        _cooldown_until = 0
