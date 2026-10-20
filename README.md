# ai_protection

`AI-SEC-EVAL v0.1`：面向已授权 AI 应用的安全评测与整改助手。

## 当前范围

- 登记受测应用与授权边界
- 从固定安全测试集执行受控测试
- 记录目标回答、耗时、工具调用和判定证据
- 使用 DeepSeek 进行结构化安全判定
- 通过 SSE 推送测试进度
- 保存测试运行和结果到 PostgreSQL

当前已验证：

- `ai_protection` 数据库可连接，pgvector 0.8.2 已启用。
- 服务启动后自动建表并灌入 6 条安全测试用例。
- `/health` 和 `/api/v1/test-cases` 已通过烟雾检查。
- 使用本地 `mock://secure` 目标跑通 2 条提示边界用例：SSE 返回 2 个 PASS，
  判定结果和证据已从 PostgreSQL 结果接口读回。
- 已入库 4 份安全知识文档，pgvector 相似度检索正常；Judge 结果中已保存
  `references`（标题、来源、分类和相似度分数）。

## 暂未完成

- Redis 短期记忆、摘要记忆和长期目标画像
- 报告页面和回归对比
- 真实目标适配器的完整鉴权与脱敏

## RAG 流程

```text
知识文件
  → 文本清洗
  → 按字符边界切块（默认 800 字符，100 字符重叠）
  → qwen3.7-text-embedding（1024 维）
  → pgvector knowledge_chunks

测试判定
  → 用测试用例描述构造查询
  → 问题向量化
  → pgvector cosine distance 召回 Top-K
  → 把知识片段加入 Judge Prompt
  → 保存判定、引用和证据
```

当前内置知识文件：

- `knowledge/prompt_boundary.md`
- `knowledge/data_protection.md`
- `knowledge/tool_boundary.md`
- `knowledge/evaluation_policy.md`

手动入库：`conda run -n voiceagent python -m app.scripts.ingest_knowledge`。

## 技术栈

FastAPI、LangChain、DeepSeek、PostgreSQL、pgvector、Redis、SSE。

## 运行

1. 建立 SSH 隧道并用 `conda activate voiceagent`。
2. 复制 `.env.example` 为 `.env`，填写数据库密码、Redis 密码和模型 Key。
3. 安装：`uv sync` 或 `pip install -e .`。
4. 启动：`uvicorn app.main:app --reload --port 8001`。

详细方案见根目录 `PROJECT_MEMORY.md` 的安全评测方向记录。

