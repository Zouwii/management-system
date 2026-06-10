"""
HTTP API 分组注册（类似 Go 里按模块 init 注册路由）。

在 api.py 末尾调用 register_all_routes(api_bp, _ok, _fail) 完成挂载。

分组一览：
- base/health    健康检查、钉钉代理、gettoken
- base/auth      钉钉 OAuth / 免登 / 会话
- base/projects  项目任务列表、搜索、用户任务
- base/config    配置（userid、时间范围、工时系数等）
- ai             AI 任务助手 / 任务创建 / 交互终端 / 知识库
- base/sync      数据同步（全量/时间段/A表/B表/批量）
- performance    绩效 fill / calculate
- base/stats     统计汇总
- workhour/costhour  工作日耗时统计（项目类型、车型、任务类型维度）
"""

from base.health.routes import register as register_health_proxy
from base.auth.routes import register as register_auth
from base.sync.routes import register as register_sync
from base.projects.routes import register as register_projects
from base.config.routes import register as register_config
from performance.routes import register as register_perf
from base.stats.routes import register as register_stats
from workhour.costhour.routes import register as register_costhour

# AI routes now centralized in the ai/ package
from ai import register_all_routes as register_ai_routes


def register_all_routes(bp, ok, fail):
    register_health_proxy(bp, ok, fail)
    register_auth(bp, ok, fail)
    register_sync(bp, ok, fail)
    register_projects(bp, ok, fail)
    register_config(bp, ok, fail)
    register_ai_routes(bp, ok, fail)
    register_perf(bp, ok, fail)
    register_stats(bp, ok, fail)
    register_costhour(bp, ok, fail)
