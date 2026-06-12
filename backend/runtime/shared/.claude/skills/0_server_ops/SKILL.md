# Server Operations — 服务器运维操作

当用户说 "连接服务器" / "查看日志" / "查数据库" / "重启服务" 时使用。

## 服务器信息

| 项目 | 值 |
|------|-----|
| 主机 | 172.19.3.79 |
| 用户 | jz |
| 密码 | 1 |
| 应用路径 | /home/jz/zhr/tb_tool_bt/ |
| MySQL | mysql -u root -p123456 tb_management |
| 服务端口 | 5002 |
| API 前缀 | http://172.19.3.79:5002/api/bt |

## 连接方式

```bash
# 方式 1: sshpass (推荐，免交互)
sshpass -p '1' ssh -o StrictHostKeyChecking=no jz@172.19.3.79

# 方式 2: 手动输入密码
ssh jz@172.19.3.79
# 密码: 1
```

## 查看服务状态

```bash
sshpass -p '1' ssh jz@172.19.3.79 "ps aux | grep python"
```

## 实时日志

```bash
sshpass -p '1' ssh jz@172.19.3.79 "tail -f /home/jz/zhr/tb_tool_bt/backend/runtime/tb_tool_bt_daemon.log"
```

## 查询数据库

```bash
# 表列表
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SHOW TABLES;'"

# API 调用量
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SELECT COUNT(*) FROM api_call_logs;'"

# 按日统计
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e \"
SELECT DATE(created_at) day, endpoint, source, COUNT(*) calls,
  SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) errors
FROM api_call_logs GROUP BY day, endpoint, source ORDER BY day DESC LIMIT 20;\""

# 最近 50 条调用
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SELECT endpoint,status,latency_ms,created_at FROM api_call_logs ORDER BY id DESC LIMIT 50;'"
```

## API 监控

```bash
# 当天统计
curl -s http://172.19.3.79:5002/api/bt/monitor/api-stats | python3 -m json.tool

# 指定日期
curl -s "http://172.19.3.79:5002/api/bt/monitor/api-stats?day=2026-06-11" | python3 -m json.tool
```

## 服务管理

```bash
# 重启
sshpass -p '1' ssh jz@172.19.3.79 "cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh restart"

# 查看当前 daemon 状态
sshpass -p '1' ssh jz@172.19.3.79 "cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh status"
```

## 同步控制

```bash
# 禁用同步
sshpass -p '1' ssh jz@172.19.3.79 "touch /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled"

# 恢复同步
sshpass -p '1' ssh jz@172.19.3.79 "rm /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled && cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh restart"

# 检查是否禁用
sshpass -p '1' ssh jz@172.19.3.79 "test -f /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled && echo DISABLED || echo ENABLED"
```
