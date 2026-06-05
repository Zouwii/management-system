"""Update lock management for task sync operations.

Provides distributed-mutex-style locking via the UpdateLock DB table.
Used by full_update_service and projects.py to prevent concurrent syncs.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from base.db.engine import SessionLocal
from base.db.orm import UpdateLock

DEFAULT_UPDATE_LOCK_TTL_SEC = 60 * 30
DEFAULT_UPDATE_LOCK_KEY = "workhour_update:all"


def _cmp_dt_utc(dt):
    """Normalize a datetime to timezone-aware UTC for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def acquire_update_lock(lock_key: str, owner: str, ttl_sec: int = DEFAULT_UPDATE_LOCK_TTL_SEC) -> Dict[str, Any]:
    """Acquire a distributed mutex lock for a sync operation.

    Args:
        lock_key: Unique lock identifier (e.g., 'workhour_update:all').
        owner: Owner string (typically 'userId@timestamp').
        ttl_sec: Lock time-to-live in seconds. Default 30 minutes.

    Returns:
        Dict with ok=True on success, or ok=False with error on failure.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(int(ttl_sec or 0), 1))
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if row:
            row_exp = _cmp_dt_utc(getattr(row, "expires_at", None))
            if row_exp and row_exp > now and str(getattr(row, "owner", "") or "") != str(owner):
                return {
                    "ok": False,
                    "error": "update is in progress by another user",
                    "lock": {
                        "lock_key": str(lock_key),
                        "owner": str(getattr(row, "owner", "") or ""),
                        "expires_at": row_exp.isoformat(),
                    },
                }
            row.owner = str(owner)
            row.locked_at = now
            row.expires_at = expires
        else:
            sess.add(
                UpdateLock(
                    lock_key=str(lock_key),
                    owner=str(owner),
                    locked_at=now,
                    expires_at=expires,
                )
            )
        sess.commit()
        return {"ok": True, "lock": {"lock_key": str(lock_key), "owner": str(owner), "expires_at": expires.isoformat()}}
    except Exception as e:
        sess.rollback()
        return {"ok": False, "error": str(e), "lock": {"lock_key": str(lock_key), "owner": str(owner)}}
    finally:
        sess.close()


def release_update_lock(lock_key: str, owner: str) -> None:
    """Release a previously acquired update lock.

    Only releases if the current owner matches, preventing accidental unlocks.
    """
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if row and str(getattr(row, "owner", "") or "") == str(owner):
            sess.delete(row)
            sess.commit()
    except Exception:
        sess.rollback()
    finally:
        sess.close()


def get_update_lock_status(lock_key: str = DEFAULT_UPDATE_LOCK_KEY) -> Dict[str, Any]:
    """Check whether a lock is currently held. Cleans up expired locks.

    Returns:
        Dict with locked (bool) and lock details.
    """
    now = datetime.now(timezone.utc)
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if not row:
            return {"locked": False, "lock": {}}
        row_exp = _cmp_dt_utc(getattr(row, "expires_at", None))
        if row_exp and row_exp > now:
            return {
                "locked": True,
                "lock": {
                    "lock_key": str(lock_key),
                    "owner": str(getattr(row, "owner", "") or ""),
                    "expires_at": row_exp.isoformat(),
                },
            }
        # Lock expired: clean up stale row
        sess.delete(row)
        sess.commit()
        return {"locked": False, "lock": {}}
    except Exception as e:
        sess.rollback()
        return {"locked": False, "error": str(e), "lock": {}}
    finally:
        sess.close()


# Backward compatibility: re-export with old private names
_acquire_update_lock = acquire_update_lock
_release_update_lock = release_update_lock
_get_update_lock_status = get_update_lock_status
