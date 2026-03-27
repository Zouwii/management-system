from typing import Any, Dict, List

from dingtalk_client import get_config_projectids, get_config_userids


def get_userids_service() -> Dict[str, Any]:
    userids = get_config_userids()
    users: List[Dict[str, str]] = []
    for name, user_id in userids.items():
        users.append({"name": str(name), "userId": str(user_id)})
    return {"success": True, "users": users}


def get_projectids_service() -> Dict[str, Any]:
    projectids = get_config_projectids()
    projects: List[Dict[str, str]] = []
    for name, project_id in projectids.items():
        projects.append({"name": str(name), "projectId": str(project_id)})
    return {"success": True, "projects": projects}

