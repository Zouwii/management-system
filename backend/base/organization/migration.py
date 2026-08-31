"""One-shot migration from ``ids.json`` into the roster table.

The application deliberately does not import ``ids.json`` during normal
startup.  Run this module when an existing deployment needs to bootstrap or
reconcile ``user_character``; subsequent roster changes are database changes.
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, Iterable, List, Mapping, Optional

from base.db.engine import SessionLocal
from base.db.orm import UserCharacter

from .constants import normalize_role_code, normalize_team_code


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _migration_codes(meta: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Resolve stable codes, including the ambiguous historical team_id=3.

    Numeric team_id=3 represented the old application-team experiment and
    therefore migrates to NAV + APPLICATION_ENGINEER. A real APP_THREE member
    must be marked explicitly with team_code=APP_THREE.
    """
    explicit_team = normalize_team_code(meta.get("team_code"))
    legacy_team = str(meta.get("team_id") if meta.get("team_id") is not None else "").strip()
    explicit_role = normalize_role_code(meta.get("job_role_code"))
    if explicit_team:
        team_code = explicit_team
    elif legacy_team == "3":
        team_code = "NAV"
    else:
        team_code = normalize_team_code(legacy_team)
    if legacy_team == "3" and not explicit_team:
        role_code = "APPLICATION_ENGINEER"
    elif explicit_role:
        role_code = explicit_role
    else:
        role_code = normalize_role_code(meta.get("character"))
    return team_code or None, role_code or None


def build_migration_plan(
    source: Mapping[str, Mapping[str, Any]],
    existing: Iterable[Any],
) -> List[Dict[str, Any]]:
    """Build deterministic insert/update actions without touching a database.

    Existing non-empty stable codes are never overwritten.  This makes the
    command safe to rerun after an operator has corrected a roster record.
    """
    existing_by_id = {
        str(getattr(row, "user_id", "") or "").strip(): row
        for row in existing
        if str(getattr(row, "user_id", "") or "").strip()
    }
    actions: List[Dict[str, Any]] = []
    processed_ids = set()
    for name, raw in sorted((source or {}).items(), key=lambda item: str(item[0])):
        meta = raw if isinstance(raw, Mapping) else {}
        user_id = str(meta.get("userId") or meta.get("user_id") or "").strip()
        if not user_id:
            continue
        processed_ids.add(user_id)
        team_code, role_code = _migration_codes(meta)
        values = {
            "name": str(name or user_id).strip() or user_id,
            "team_code": team_code or None,
            "job_role_code": role_code or None,
            "character": _as_int(meta.get("character"), 0),
            "team_id": str(meta.get("team_id")).strip() if meta.get("team_id") is not None else None,
            "is_nav_lead": bool(meta.get("is_nav_lead", False)),
            "is_servo_lead": bool(meta.get("is_servo_lead", False)),
            "is_p3_lead": bool(meta.get("is_p3_lead", False)),
        }
        row = existing_by_id.get(user_id)
        if row is None:
            actions.append({"action": "insert", "user_id": user_id, **values})
            continue
        changes: Dict[str, Any] = {}
        # Only fill newly introduced fields when they are blank.  Legacy
        # fields and manually curated lead flags are intentionally preserved.
        unresolved_legacy_application = (
            not normalize_team_code(getattr(row, "team_code", None))
            and str(getattr(row, "team_id", "") or "").strip() == "3"
        )
        if not normalize_team_code(getattr(row, "team_code", None)) and values["team_code"]:
            changes["team_code"] = values["team_code"]
        if (
            not normalize_role_code(getattr(row, "job_role_code", None))
            or unresolved_legacy_application
        ) and values["job_role_code"]:
            changes["job_role_code"] = values["job_role_code"]
        if changes:
            actions.append({"action": "update", "user_id": user_id, "changes": changes})
        else:
            actions.append({"action": "unchanged", "user_id": user_id})

    # Also reconcile database-only rows. ids.json is only a migration source;
    # a person must not be omitted merely because the legacy file no longer
    # contains them.
    for user_id, row in sorted(existing_by_id.items()):
        if user_id in processed_ids:
            continue
        team_code, role_code = _migration_codes({
            "team_code": getattr(row, "team_code", None),
            "team_id": getattr(row, "team_id", None),
            "job_role_code": getattr(row, "job_role_code", None),
            "character": getattr(row, "character", None),
        })
        unresolved_legacy_application = (
            not normalize_team_code(getattr(row, "team_code", None))
            and str(getattr(row, "team_id", "") or "").strip() == "3"
        )
        changes: Dict[str, Any] = {}
        if not normalize_team_code(getattr(row, "team_code", None)) and team_code:
            changes["team_code"] = team_code
        if (
            not normalize_role_code(getattr(row, "job_role_code", None))
            or unresolved_legacy_application
        ) and role_code:
            changes["job_role_code"] = role_code
        if changes:
            actions.append({"action": "update", "user_id": user_id, "changes": changes})
    return actions


def migrate_from_ids(
    *,
    source: Optional[Mapping[str, Mapping[str, Any]]] = None,
    session_factory=SessionLocal,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply the explicit ids-to-database migration and return an audit report."""
    if source is None:
        from base.dingtalk_client import get_config_user_meta

        source = get_config_user_meta()
    session = session_factory()
    try:
        existing_rows = session.query(UserCharacter).all()
        actions = build_migration_plan(source, existing_rows)
        source_ids = {
            str((meta or {}).get("userId") or (meta or {}).get("user_id") or "").strip()
            for meta in (source or {}).values()
            if isinstance(meta, Mapping)
        }
        database_only = sorted(
            str(getattr(row, "user_id", "") or "").strip()
            for row in existing_rows
            if str(getattr(row, "user_id", "") or "").strip() not in source_ids
        )
        if not dry_run:
            for action in actions:
                if action["action"] == "insert":
                    values = dict(action)
                    values.pop("action", None)
                    session.add(UserCharacter(**values))
                elif action["action"] == "update":
                    row = session.get(UserCharacter, action["user_id"])
                    if row is not None:
                        for key, value in action["changes"].items():
                            setattr(row, key, value)
            session.commit()
        counts = {key: sum(1 for item in actions if item["action"] == key) for key in ("insert", "update", "unchanged")}
        return {
            "dryRun": dry_run,
            "sourceCount": len(source or {}),
            "actions": actions,
            "counts": counts,
            # Informational only: database-only rows are never deleted.
            "databaseOnly": database_only,
            # The database is authoritative after migration, so records that
            # were added later and are absent from ids.json are informational,
            # not a failed check.
            "reconciled": not (counts["insert"] or counts["update"]),
        }
    finally:
        session.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Import ids.json roster into user_character")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="apply the migration plan")
    action.add_argument("--dry-run", action="store_true", help="print the plan without writing (default)")
    action.add_argument("--check", action="store_true", help="audit drift and return 1 when changes are needed")
    parser.add_argument("--verify", action="store_true", help="print member counts for every business Scope")
    args = parser.parse_args(argv)
    report = migrate_from_ids(dry_run=not args.apply)
    print("roster migration: {}".format(report["counts"]))
    if report["databaseOnly"]:
        print("database-only records (kept): {}".format(", ".join(report["databaseOnly"])))
    for action in report["actions"]:
        if action["action"] != "unchanged":
            print(action)
    if args.verify:
        from .constants import SCOPE_POLICIES
        from .service import list_scope_members

        for scope_code in SCOPE_POLICIES:
            members = list_scope_members(scope_code)
            print("scope {}: {} member(s)".format(scope_code, len(members)))
    return 1 if args.check and not report["reconciled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
