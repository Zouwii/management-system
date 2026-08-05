-- ============================================================
-- 知识库数据迁移脚本
-- 将 kb_documents / kb_chunks 从 benti_management 迁移到 kb_storage
--
-- 执行方式：
--   mysql -u root -p < scripts/migrate_kb_storage.sql
--
-- 建议：先在 tmux/screen 中执行，避免网络中断。
-- 迁移完成后保留旧表作为备份，验证通过后再手动删除。
-- ============================================================

-- 1. 创建 kb_storage 数据库
CREATE DATABASE IF NOT EXISTS kb_storage
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 2. 复制 kb_documents 表结构和数据
DROP TABLE IF EXISTS kb_storage.kb_documents;
CREATE TABLE kb_storage.kb_documents LIKE benti_management.kb_documents;
INSERT INTO kb_storage.kb_documents SELECT * FROM benti_management.kb_documents;

-- 3. 复制 kb_chunks 表结构和数据
DROP TABLE IF EXISTS kb_storage.kb_chunks;
CREATE TABLE kb_storage.kb_chunks LIKE benti_management.kb_chunks;
INSERT INTO kb_storage.kb_chunks SELECT * FROM benti_management.kb_chunks;

-- 4. 验证数据完整性
SELECT
  'benti_management' AS source_db,
  (SELECT COUNT(*) FROM benti_management.kb_documents) AS documents,
  (SELECT COUNT(*) FROM benti_management.kb_chunks) AS chunks
UNION ALL
SELECT
  'kb_storage' AS source_db,
  (SELECT COUNT(*) FROM kb_storage.kb_documents) AS documents,
  (SELECT COUNT(*) FROM kb_storage.kb_chunks) AS chunks;

-- 5. 为 kb_storage.kb_chunks 建立 FULLTEXT 索引（MySQL 版）
--    注意：如果 chunks 数据量很大，建索引会比较慢，请耐心等待。
ALTER TABLE kb_storage.kb_chunks
  ADD FULLTEXT INDEX ft_kb_chunks_content (content) WITH PARSER ngram;

-- ============================================================
-- 6. RAG v3.0: 重命名 raw_json -> outline（分级目录）
--    执行方式：
--      mysql -u root -p kb_storage < scripts/migrate_kb_storage.sql
--    或直接在服务器上执行：
--      ALTER TABLE kb_documents RENAME COLUMN raw_json TO outline;
-- ============================================================
ALTER TABLE kb_storage.kb_documents RENAME COLUMN raw_json TO outline;

-- ============================================================
-- 迁移完成后，重启 Flask 服务即可使用新库。
-- 验证通过后，可以手动删除旧表：
--   DROP TABLE benti_management.kb_documents;
--   DROP TABLE benti_management.kb_chunks;
--   DROP TABLE IF EXISTS benti_management.kb_chunks_fts;  -- SQLite FTS 遗留
-- ============================================================
