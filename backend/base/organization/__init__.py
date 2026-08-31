"""Organization, role and business-roster primitives."""

from .service import (
    RosterService,
    is_person_in_scope,
    list_all_members,
    list_scope_member_ids,
    list_scope_members,
    list_scope_teams,
    resolve_sync_operator_id,
)

__all__ = [
    "is_person_in_scope",
    "list_all_members",
    "RosterService",
    "list_scope_member_ids",
    "list_scope_members",
    "list_scope_teams",
    "resolve_sync_operator_id",
]
