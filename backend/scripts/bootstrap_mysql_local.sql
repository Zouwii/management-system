-- 可选：建库 + 应用账号（MySQL 5.7 / 8.0 通用写法）
-- mysql -u root -p < scripts/bootstrap_mysql_local.sql
-- 生产环境请改掉默认密码 tb_tool_bt_local_dev

CREATE DATABASE IF NOT EXISTS tb_tool_bt
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON tb_tool_bt.* TO 'tb_tool_app'@'localhost' IDENTIFIED BY 'tb_tool_bt_local_dev';
GRANT ALL PRIVILEGES ON tb_tool_bt.* TO 'tb_tool_app'@'127.0.0.1' IDENTIFIED BY 'tb_tool_bt_local_dev';
FLUSH PRIVILEGES;
