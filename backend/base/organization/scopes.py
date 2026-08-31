"""Central business-roster policies.

Keep this module free of database imports so policy behavior can be tested
without starting Flask or opening a database connection.
"""

from typing import Dict, Tuple

from .constants import SCOPE_POLICIES


def get_scope_policy(scope_code: str) -> Dict[str, Tuple[str, ...]]:
    key = str(scope_code or "").strip().upper()
    try:
        return SCOPE_POLICIES[key]
    except KeyError as exc:
        raise ValueError("unknown organization scope: {}".format(scope_code)) from exc
