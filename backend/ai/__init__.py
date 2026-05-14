"""AI module for the management system.

Sub-modules:
  tbcreate/         - Teambition task creation (ttyd Claude CLI → draft.json → polling)
  mission/          - Teambition task ticket creation (draft → DingTalk API)
  terminal/         - Interactive AI terminal (ttyd + Claude CLI)

Usage:
  from ai import register_all_routes
  register_all_routes(bp, ok, fail)
"""

from ai.tbcreate.routes import register as _register_tbcreate
from ai.mission.routes import register as _register_mission
from ai.terminal.routes import register as _register_terminal


def register_all_routes(bp, ok, fail):
    """Register all AI-related HTTP routes on the given Flask Blueprint.

    Args:
        bp: Flask Blueprint (api_bp, prefix /api/bt).
        ok: Response helper for successful JSON responses.
        fail: Response helper for error JSON responses.
    """
    _register_tbcreate(bp, ok, fail)
    _register_mission(bp, ok, fail)
    _register_terminal(bp, ok, fail)
