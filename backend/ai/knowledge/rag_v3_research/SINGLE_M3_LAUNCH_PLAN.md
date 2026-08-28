# 单层切块 + BGE-M3 四步上线执行文档

> 状态：待执行  
> 目标：放弃 leaf-parent 双层切块，以尽可能小的架构改动上线单层动态切块和 BGE-M3 检索。

## 一、方案范围

本次只实施以下方案：

```text
Markdown 原文
  → 单层动态切块（目标800、最大1200 BGE-M3 token）
  → BGE-M3 生成1024维向量
  → BM25 + BGE-M3 Hybrid 检索
  → Top-K chunk 直接提供给 LLM
```

本次不实施：

- JSONML 和钉钉原生 blocks 接入；
- leaf-parent 层级；
- retrieval projection/context 双层索引；
- parent/sibling 扩展；
- Cross-Encoder reranker；
- BGE-small 的1200-token embedding。

## 二、第一步：实现单层动态切块

### 执行内容

1. 增加可配置切块策略：

   ```text
   KB_CHUNK_STRATEGY=single_m3
   ```

2. 实现 `single_m3` 单层 Chunker：

   - 使用 BGE-M3 tokenizer 统计长度；
   - 目标长度800 token；
   - 硬上限1200 token；
   - 同一章节内动态聚合段落；
   - 短文允许只生成一个 chunk；
   - 超长正文依次按章节、段落、换行、句子和 token 边界拆分；
   - 不生成 parent；
   - 不建立 parent-child 关系。

3. 每个 chunk 添加紧凑结构头：

   ```text
   知识库路径：workspace / 最后两到三级文件夹
   文档：文档标题
   本文目录：section_path
   ```

4. 结构保护：

   - 表格拆分后重复表头；
   - 代码拆分后保持围栏完整；
   - fenced code 内的 `#` 不作为 Markdown 标题；
   - 无可靠 heading 时使用文档名，不生成假目录。

5. 为兼容现有数据库和检索 SQL，单层 chunk 暂时统一存储为：

   ```text
   depth=1
   parent_id=NULL
   chunk_type=single
   ```

   此处 `depth=1` 仅表示“可检索 chunk”，不再表示 parent 下的 leaf。

### 主要修改文件

- `backend/ai/knowledge/chunker.py`，或新增独立的 `single_m3_chunker.py`；
- `backend/ai/knowledge/chunk_storage.py`；
- `backend/ai/knowledge/auto_sync.py`；
- 切块相关测试文件。

### 完成标准

- 所有 chunk 不超过1200个 BGE-M3 token；
- 不生成 parent；
- 每个 chunk 包含路径、文档名和本文目录；
- 表格表头和代码围栏完整；
- 相同原文和配置生成稳定、可重复的 chunk 顺序。

## 三、第二步：接入 BGE-M3

### 执行内容

1. 准备完整的 `BAAI/bge-m3` 模型。

   当前本地目录约48 MB，没有完整模型权重，不能直接用于生产，需要重新下载或从已有服务器同步完整模型。

2. 增加 embedding 配置：

   ```text
   KB_EMBEDDING_MODEL=bge-m3
   KB_EMBEDDING_VECTOR_TABLE=chunk_vectors_bgem3
   KB_EMBEDDING_DIMENSION=1024
   ```

3. 修改 embedding 链路：

   - 根据配置加载 BGE-small 或 BGE-M3；
   - BGE-M3 文档向量写入 `chunk_vectors_bgem3`；
   - 批量编码支持断点续跑；
   - 已存在向量默认跳过；
   - 记录编码数量、失败数量和耗时。

4. 修改向量检索链路：

   - 查询向量和文档向量使用同一模型；
   - BGE-M3 查询使用 `chunk_vectors_bgem3`；
   - 启动或查询前校验模型维度与向量表一致；
   - 保留 BGE-small 和 `chunk_vectors` 配置作为回滚入口。

5. 暂不修改 BM25；MySQL FULLTEXT 继续检索 `kb_chunks.content`。

### 主要修改文件

- `backend/ai/knowledge/embedder.py`；
- `backend/ai/knowledge/retriever.py`；
- `backend/ai/knowledge/rag_improve/step06_encode_vectors.py`；
- 模型和检索配置文件；
- embedding/retrieval 测试文件。

### 完成标准

- BGE-M3 能在服务器正常加载；
- 输入超过512、但不超过1200 token 时不会被截断；
- 成功写入和查询1024维向量；
- BGE-small 与 BGE-M3 可以通过配置切换；
- 不允许 BGE-small 查询 BGE-M3 向量表或反向混用。

## 四、第三步：六篇文档小范围验证

### 执行内容

1. 使用现有六篇本地样本运行 `single_m3`：

   - 速度仲裁；
   - 故障诊断三期需求分解方案；
   - 低代码算子字典；
   - 驱动相关ROS接口；
   - AGV硬件维护指导书V1.7；
   - 仿真平台http接口文档。

2. 输出每篇文档的：

   - chunk 数量；
   - token min/mean/p95/max；
   - 路径和目录覆盖率；
   - 超限数量；
   - 表格表头异常数量；
   - 代码围栏异常数量。

3. 人工检查典型结果：

   - 短文是否保持完整；
   - ROS 表格是否保留表头；
   - 仿真 HTTP 代码是否完整；
   - AGV 文档是否避免生成假目录；
   - 长文是否出现大量过小或重复 chunk。

4. 使用 BGE-M3 对六篇文档建立本地向量，运行内容型和层级型测试问题。

5. 与当前 BGE-small leaf 基线比较：

   - 文档 Hit@1/3/5；
   - MRR；
   - 查询平均和P95延迟；
   - Top-K重复率；
   - 人工答案完整性和引用正确性。

### 主要修改文件

- `backend/ai/knowledge/rag_v3_research/` 下新增单层 M3 测试脚本；
- 复用 `sample_manifest.json` 和 `sample_queries.json`；
- 测试生成的正文和向量文件必须保持 Git Ignore。

### 完成标准

- 六篇文档全部成功切块和编码；
- 无超过1200 token 的 chunk；
- 无明显表格、代码结构损坏；
- BGE-M3 延迟满足上线要求；
- 检索结果不低于当前基线，且层级型查询有明确改善；
- 未通过时停止，不执行全量重建。

## 五、第四步：服务器全量重建并上线

### 4.1 数据库处理原则

必须保留：

- `kb_nodes`：知识库目录与 breadcrumb；
- `kb_documents`：Markdown 原文、标题和 outline；
- 其他业务数据库表。

需要重建：

- `kb_chunks`：替换为新的单层 chunk；
- `chunk_vectors_bgem3`：根据新 chunk ID 全量生成。

上线初期必须保留用于回滚：

- 当前 BGE-small `kb_chunks` 的完整备份；
- 当前 `chunk_vectors`。

### 4.2 执行内容

1. 创建当前 `kb_chunks` 的完整备份，例如：

   ```text
   kb_chunks_bge_small_backup
   ```

2. 清理或重建 `chunk_vectors_bgem3`，避免旧 chunk ID 残留。

3. 使用 `single_m3` 对所有有正文的 `kb_documents` 分批切块。

4. 分批生成 BGE-M3 向量：

   - 支持断点续跑；
   - 失败文档或 chunk 可单独重试；
   - 不因单批失败破坏已完成批次。

5. 完成一致性检查：

   - 每篇有正文文档至少有一个 chunk；
   - 每个生产 chunk 有且只有一个 BGE-M3 向量；
   - 没有孤儿向量；
   - 没有超过1200 token 的 chunk；
   - 没有异常长文只有一个超大 chunk；
   - 失败文档数量为0，或有明确排除清单。

6. 用服务器数据重新运行检索和人工问答验证。

7. 通过配置将生产查询切到：

   ```text
   KB_CHUNK_STRATEGY=single_m3
   KB_EMBEDDING_MODEL=bge-m3
   KB_EMBEDDING_VECTOR_TABLE=chunk_vectors_bgem3
   ```

8. 观察错误率、空召回率、检索延迟和引用正确性。

### 4.3 回滚

如果上线异常：

1. 停止写入新的单层 chunk；
2. 恢复 `kb_chunks_bge_small_backup` 为生产 `kb_chunks`；
3. 将 embedding 配置切回 BGE-small；
4. 将向量表切回 `chunk_vectors`；
5. 验证旧 chunk ID 与旧向量重新对应。

旧 chunk 和 BGE-small 向量至少保留一到两周，稳定后再决定是否删除。

### 完成标准

- 全量 chunk、向量和文档数量一致；
- 生产检索只使用 BGE-M3 和新单层 chunk；
- 线上延迟和错误率可接受；
- 旧索引仍可完整回滚；
- 自动同步后新增或变更文档继续使用 `single_m3`。

## 六、最终交付物

完成四步后应交付：

1. 单层 BGE-M3 Chunker；
2. 可配置的 BGE-small/BGE-M3 embedding 与 retrieval；
3. 六篇文档的切块和检索对比报告；
4. 可断点续跑的全量重建脚本；
5. 数据一致性检查结果；
6. 上线配置与回滚说明。
