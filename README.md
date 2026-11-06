# ai_protection

`AI-SEC-EVAL v0.1`：面向已授权 AI 应用的安全评测与整改助手。

项目文件地图、设计理由、验收状态和逐项变更历史见
[`CHANGELOG.md`](CHANGELOG.md)。

## 当前范围

- 登记受测应用与授权边界
- 从固定安全测试集执行受控测试
- 记录目标回答、耗时、工具调用和判定证据
- 使用 DeepSeek 进行结构化安全判定
- 通过 SSE 推送测试进度
- 保存测试运行和结果到 PostgreSQL
- 使用 Redis 短期事件、上一次运行摘要和 pgvector 长期目标画像辅助 Judge

当前已验证：

- `ai_protection` 数据库可连接，pgvector 0.8.2 已启用。
- 服务启动后自动建表并灌入 6 条安全测试用例。
- `/health` 和 `/api/v1/test-cases` 已通过烟雾检查。
- 使用本地 `mock://secure` 目标跑通 2 条提示边界用例：SSE 返回 2 个 PASS，
  判定结果和证据已从 PostgreSQL 结果接口读回。
- 已入库 4 份安全知识文档，pgvector 相似度检索正常；Judge 结果中已保存
  `references`（标题、来源、分类和相似度分数）。
- A1 已完成：支持 `mock://secure`、`mock://prompt-leaky`、`mock://unsafe-tool`
  三种受控目标；目标回答先脱敏，单条用例超时/失败记录 `UNKNOWN` 后继续运行。
- A2 已完成离线代码接入：Redis 保存当前运行事件，PostgreSQL 提供上一次摘要，
  pgvector 保存跨运行目标画像；记忆统一加入 Judge Prompt。
- A2 记忆故障按辅助功能降级：Redis socket 超时 2 秒，单次记忆加载/写入默认最多
  15 秒，不阻断正式目标测试和结果落库。
- A1/A2 离线测试：`16 passed`。

2026-11-06 检查时本地端口 15432 和 16379 均未监听，因此上述 A2 结论仅代表离线
代码与单测通过；真实 Redis/PostgreSQL/pgvector 端到端验收仍待隧道恢复。

## 暂未完成

- A2 对真实 Redis、PostgreSQL 和 pgvector 的端到端验收
- 报告页面和回归对比
- 真实目标适配器的完整鉴权与脱敏
- 最小前端和 30–50 条测试集的正式评测

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

## 三段记忆

```text
每条用例执行前
  → Redis：当前 run_id 的最近 10 条紧凑事件
  → PostgreSQL：同一目标最近一次完成运行的 summary
  → pgvector：按当前用例检索目标历史画像 Top-3
  → 统一渲染为“历史评测上下文”
  → 与 RAG 知识、测试用例和目标回答一起交给 DeepSeek Judge

运行结束后
  → PostgreSQL 保存本次 summary
  → pgvector 追加一条 target_profile 长期画像
```

短期事件最多保留 20 条，TTL 24 小时，不保存目标回答原文。记忆内容写入前会做常见
凭据脱敏。长期画像当前按每次运行追加，尚未实现合并、去重、失效或清理策略。

## 技术栈

FastAPI、LangChain、DeepSeek、PostgreSQL、pgvector、Redis、SSE。

## 运行

1. 建立 SSH 隧道并用 `conda activate voiceagent`。
2. 复制 `.env.example` 为 `.env`，填写数据库密码、Redis 密码和模型 Key；
   可按需调整目标、Judge 和记忆超时。
3. 安装：`uv sync` 或 `pip install -e .`。
4. 启动：`uvicorn app.main:app --reload --port 8001`。

跨项目决策见根目录 `PROJECT_MEMORY.md`；本子项目的详细记录以
[`CHANGELOG.md`](CHANGELOG.md) 为准。

