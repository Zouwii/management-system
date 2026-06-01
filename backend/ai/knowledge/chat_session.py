"""In-memory chat session store with TTL-based expiry."""

from __future__ import annotations

import time
import uuid
from typing import Dict, List

# {session_id: {"messages": [...], "created_at": ts, "last_access": ts}}
_SESSIONS: Dict[str, dict] = {}
_TTL_SECONDS = 30 * 60  # 30 minutes
_MAX_ROUNDS = 5  # max conversation rounds to keep per session


def create_session() -> str:
    """Create a new session, return its id."""
    _expire_sessions()
    sid = uuid.uuid4().hex[:16]
    _SESSIONS[sid] = {"messages": [], "created_at": time.time(), "last_access": time.time()}
    return sid


def get_history(session_id: str) -> List[dict]:
    """Return recent conversation history (user + assistant messages)."""
    _expire_sessions()
    s = _SESSIONS.get(session_id)
    if not s:
        return []
    s["last_access"] = time.time()
    return s["messages"][-(_MAX_ROUNDS * 2):]


def add_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Record a user/assistant message pair."""
    _expire_sessions()
    s = _SESSIONS.get(session_id)
    if not s:
        return
    s["messages"].append({"role": "user", "content": user_msg})
    s["messages"].append({"role": "assistant", "content": assistant_msg})
    s["last_access"] = time.time()
    # Trim to max rounds
    s["messages"] = s["messages"][-(_MAX_ROUNDS * 2):]


def _expire_sessions() -> None:
    now = time.time()
    expired = [sid for sid, s in _SESSIONS.items() if now - s["last_access"] > _TTL_SECONDS]
    for sid in expired:
        del _SESSIONS[sid]
