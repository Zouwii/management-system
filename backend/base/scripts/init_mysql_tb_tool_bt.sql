-- 本地 MySQL：创建业务库（执行一次即可）
-- mysql -u root -p < scripts/init_mysql_tb_tool_bt.sql

CREATE DATABASE IF NOT EXISTS benti_management
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
