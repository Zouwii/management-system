import hashlib
from unittest.mock import Mock, patch

import pytest

from ai.terminal import session as terminal


def _state(owner_key, pid, rss_kb=0, purpose=""):
    proc = Mock()
    proc.pid = pid
    proc.poll.return_value = None
    return {
        "owner_key": owner_key,
        "owner_safe": terminal.safe_owner_key(owner_key),
        "purpose": purpose,
        "proc": proc,
        "rss_kb": rss_kb,
    }


def test_authenticated_identity_cannot_be_overridden_by_payload():
    assert terminal.resolve_owner_key(
        {"ownerKey": "victim"}, {"user_id": "signed-in-user", "name": "甲"}
    ) == "signed-in-user"


def test_missing_or_unstable_identity_is_rejected():
    with pytest.raises(ValueError, match="missing authenticated"):
        terminal.resolve_owner_key({}, {})
    with pytest.raises(ValueError, match="stable user_id"):
        terminal.resolve_owner_key(
            {"ownerKey": "victim"}, {"name": "只有姓名"}
        )
    with pytest.raises(ValueError, match="stable user_id"):
        terminal.safe_owner_key("")


def test_internal_owner_key_compatibility_remains_deterministic():
    owner = terminal.resolve_owner_key({"ownerKey": "internal-user"}, {})
    expected = hashlib.sha256(b"internal-user").hexdigest()[:24]
    assert terminal.safe_owner_key(owner) == expected


def test_process_tree_rss_only_sums_the_selected_tree():
    table = {10: (1, 100), 11: (10, 200), 12: (11, 300), 20: (1, 999)}
    assert terminal.process_tree_rss_kb(10, table) == 600


def test_user_memory_limit_sums_multiple_purposes(monkeypatch):
    first = _state("user-a", 10, purpose="default")
    second = _state("user-a", 20, purpose="knowledge")
    terminal._TTYD_SESSIONS.clear()
    terminal._TTYD_SESSIONS.update({"user-a": first, "user-a::knowledge": second})
    monkeypatch.setenv("AI_TTYD_USER_MEMORY_MB", "128")
    monkeypatch.setenv("AI_TTYD_TOTAL_MEMORY_MB", "1024")
    table = {10: (1, 70 * 1024), 20: (1, 70 * 1024)}
    try:
        with patch.object(terminal, "_process_table", return_value=table), patch.object(
            terminal, "_terminate_ttyd_locked"
        ) as terminate:
            terminal._enforce_resource_limits_locked()
        assert len(terminal._TTYD_SESSIONS) == 1
        terminate.assert_called_once()
        assert terminate.call_args.kwargs["reason"] == "user_memory_limit"
    finally:
        terminal._TTYD_SESSIONS.clear()


def test_total_memory_limit_is_hard_even_for_different_users(monkeypatch):
    first = _state("user-a", 10)
    second = _state("user-b", 20)
    terminal._TTYD_SESSIONS.clear()
    terminal._TTYD_SESSIONS.update({"user-a": first, "user-b": second})
    monkeypatch.setenv("AI_TTYD_USER_MEMORY_MB", "1024")
    monkeypatch.setenv("AI_TTYD_TOTAL_MEMORY_MB", "128")
    table = {10: (1, 60 * 1024), 20: (1, 90 * 1024)}
    try:
        with patch.object(terminal, "_process_table", return_value=table), patch.object(
            terminal, "_terminate_ttyd_locked"
        ) as terminate:
            terminal._enforce_resource_limits_locked()
        assert "user-a" in terminal._TTYD_SESSIONS
        assert "user-b" not in terminal._TTYD_SESSIONS
        assert terminate.call_args.kwargs["reason"] == "total_memory_limit"
    finally:
        terminal._TTYD_SESSIONS.clear()


def test_make_env_uses_private_home_and_claude_config(tmp_path, monkeypatch):
    users_root = tmp_path / "users"
    monkeypatch.setattr(terminal, "_USERS_ROOT", users_root)
    monkeypatch.setenv("HOME", "/runtime/deploy-user")
    with patch.object(
        terminal,
        "load_ai_config",
        return_value={"api_key": "test", "base_url": "http://gateway"},
    ):
        env = terminal.make_env("user-a", "甲", "test-model")
    safe = terminal.safe_owner_key("user-a")
    assert env["HOME"] == str(users_root / safe / "home")
    assert env["CLAUDE_CONFIG_DIR"] == str(users_root / safe / ".claude")
    assert env["AI_RUNTIME_HOME"] == "/runtime/deploy-user"
