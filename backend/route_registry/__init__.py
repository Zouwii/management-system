"""
HTTP API 分组注册（类似 Go 里按模块 init 注册路由）。

在 api.py 末尾调用 register_all_routes(api_bp, _ok, _fail) 完成挂载。

分组一览：
- health_proxy   健康检查、钉钉代理、gettoken
- auth          钉钉 OAuth / 免登 / 会话
- projects      项目任务列表、搜索、用户任务
- config_api    配置（userid、时间范围、工时系数等）
- db_sync       A/B 表同步、全量下载
- perf          绩效 fill / calculate
- stats         统计汇总
"""

from .health_proxy import register as register_health_proxy
from .auth import register as register_auth
from .updates import register as register_updates
from .projects import register as register_projects
from .config_routes import register as register_config
from .db_sync import register as register_db_sync
from .perf import register as register_perf
from .stats import register as register_stats


def register_all_routes(bp, ok, fail):
    register_health_proxy(bp, ok, fail)
    register_auth(bp, ok, fail)
    register_updates(bp, ok, fail)
    register_projects(bp, ok, fail)
    register_config(bp, ok, fail)
    register_db_sync(bp, ok, fail)
    register_perf(bp, ok, fail)
    register_stats(bp, ok, fail)
