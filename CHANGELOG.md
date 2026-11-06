# ai_protection 项目变更记录

> 范围：只记录 `ai_protection/` 下的 `AI-SEC-EVAL v0.1` 子项目。
>
> 最后核验：2026-11-06（Asia/Shanghai）
>
> 根目录 `PROJECT_MEMORY.md` 保存跨项目决策和索引；本文件保存本子项目的文件地图、
> 设计理由、制作状态和逐项变更历史。两者冲突时，以更新时间更晚、证据更直接的记录为准。

## 状态标记

- **用户确认**：用户明确表达或明确要求的内容。
- **已核验**：通过当前文件、源码、数据库只读查询或运行结果确认。
- **已制作，待验收**：代码或文档已经存在，但还没有完成用户验收或端到端运行。
- **AI 建议**：AI 提出但用户尚未确认的方案，不视为项目决定。
- **待确认**：缺少用户选择、外部条件或运行结果，不能写成既定事实。
- **已失效 / 已取代**：旧结论不再代表当前状态，只保留追溯价值。

## 0. 一分钟接手

`ai_protection` 是一个面向**已授权 AI 应用**的安全评测与整改助手。它不直接攻击
目标，而是登记目标、执行固定的受控测试用例、保存目标回答，再由 Judge 结合安全
知识库给出 `PASS / FAIL / UNKNOWN` 判定和证据引用。

当前版本的目标闭环如下；其中 A1 链路已有真实历史验证，A2 新增段已离线验证，
真实 Redis/PostgreSQL 仍待验收：

```text
登记受测目标
  → 创建测试运行
  → SSE 推送进度
  → 逐条执行测试步骤
  → 读取短期事件、上一次摘要和长期目标画像
  → RAG 检索安全知识
  → DeepSeek 结合记忆与安全知识做结构化判定
  → PostgreSQL 保存结果和引用
  → 保存运行摘要并写入长期目标画像
  → 查询运行详情与结果
```

2026-11-05 已完成 A1 可测试性加固：

- 增加 `mock://secure`、`mock://prompt-leaky`、`mock://unsafe-tool` 三种受控目标。
- 目标回答、Judge Prompt 证据和异常消息先做常见凭据脱敏。
- 单条用例目标超时或判定超时后记录 `UNKNOWN`，继续执行后续用例。
- 运行摘要增加 `errors`，状态可区分 `completed` 与 `completed_with_errors`。
- 新增 6 个离线 pytest 测试，覆盖脱敏、三种 mock 和单用例失败恢复。

2026-11-06 用户确认并开始 A2 三段记忆，当前已完成代码接入：

- Redis 保存当前运行的最近事件：`run_started`、`case_started`、`case_result`、
  `error`、`run_completed`；只保留 20 条，TTL 24 小时，不保存目标回答原文。
- PostgreSQL 从同一目标最近一次完成的运行读取 `test_runs.summary`，作为上一次评测
  摘要；Redis 和摘要读取失败时降级为空上下文，不阻断评测。
- pgvector 在运行结束后写入一条 `target_profile` 长期画像，包含目标、模型、覆盖范围、
  判定分布和逐用例结论；后续检索按目标隔离并取余弦 Top-3。
- 三段记忆统一渲染后送入 Judge Prompt；记忆写入前做常见凭据脱敏。
- A2 离线测试通过；当前共 `16 passed`。

当前**没有**完成或无法本轮核验的能力：真实目标鉴权与脱敏、A2 对真实 Redis/PostgreSQL
的端到端验收、报告页面、回归对比、最小前端和正式检索/判定质量评测。

当前数据事实（2026-10-20 只读查询；仅作历史快照）：

| 项目 | 数量 / 状态 | 来源 |
|---|---:|---|
| `targets` | 2 | `ai_protection` 数据库只读查询 |
| `test_cases` | 6 | 同上 |
| `test_runs` | 3 | 同上 |
| `test_results` | 4 | 同上 |
| `knowledge_chunks` | 4 | 同上 |
| `memories` | 0 | 同上；这是 A2 接入前的历史快照 |
| 最近两条结果 | `pb-001`、`pb-002` 均为 `PASS`，各 3 条 references | 同上 |
| 较早两条结果 | `pb-001`、`pb-002` 均为 `PASS`，各 0 条 references | 同上；属于接入 RAG 前的记录 |
| 8001 端口 | 未监听 | 2026-10-20 端口检查；测试后未保持服务运行 |

2026-11-06 复核当前连接：`127.0.0.1:15432` 与 `127.0.0.1:16379` 均未监听，因此本轮
没有执行 PostgreSQL、pgvector 或 Redis 的真实读写；A2 只能确认离线行为，不能写成
“真实三段记忆已验收”。

## 1. 已确认决定

| ID | 决定 | 原因与边界 | 状态 | 来源 |
|---|---|---|---|---|
| A-001 | 业务方向为“AI 应用安全评测与整改助手” | 与用户的信息安全专业方向一致，同时保留 FastAPI、LangChain、RAG、记忆和 SSE 这套基础设施 | 用户确认 | 用户指令 2026-10-19；根 `PROJECT_MEMORY.md` C-014 |
| A-002 | 首版编号为 `AI-SEC-EVAL v0.1`，范围固定为 OpenAI 兼容聊天目标、提示边界、敏感信息保护、工具边界、6 条初始用例、SSE 和结果落库 | 先建立可复现、可审计的最小评测闭环，避免一开始做成泛化的“安全平台” | 用户确认 | 用户指令；根 `PROJECT_MEMORY.md` C-016 |
| A-003 | 使用 PostgreSQL `ai_protection` 库、pgvector、Redis 和 SSH 隧道 | 与旧 `mini_app` 及平行 `soc_agent` 项目隔离，避免表、向量和会话串用 | 用户确认并核验 | 用户指令；根 `PROJECT_MEMORY.md` C-015；数据库检查 |
| A-004 | 对话模型使用 DeepSeek，向量模型使用阿里云 `qwen3.7-text-embedding`，向量维度 1024 | 用户指定供应商；实测模型可用，LangChain 需要关闭默认的上下文长度检查 | 用户确认并实测 | 用户指令；RAG 运行记录 |
| A-005 | Python 环境固定使用 `conda activate voiceagent` | 统一依赖和运行方式，避免不同解释器导致数据库、Embedding 或 LangChain 行为不一致 | 用户确认 | 用户指令 |
| A-006 | 安全测试只作用于用户明确授权的目标，默认不执行破坏性操作、不扫描网络、不获取凭据 | 这是评测系统的产品边界，也是防止工具被误用的最低要求 | 用户确认 | 用户指令；根 `AGENTS.md` |
| A-007 | RAG 知识库服务于 Judge 判定，不把安全知识注入受测目标 | 知识库用于提高判定一致性；向目标注入知识会改变被测系统行为，破坏评测公平性 | 已核验 | `app/services/judge.py`；`app/services/rag.py` |
| A-008 | `ai_protection` 的详细变更记录独立维护在本文件，根 `PROJECT_MEMORY.md` 只保留索引 | 根记忆同时包含 AgentChat、mini_app、ai_protection 和 soc_agent，细节混在一起不便阅读 | 用户确认 | 用户指令 2026-10-20 |
| A-009 | 执行 A2：Redis 短期事件 + PostgreSQL 运行摘要 + pgvector 长期目标画像，并统一注入 Judge | 让后续评测能带上本次进度、上次结论和跨运行的目标历史；所有记忆均为辅助信息，失败、超时或脱敏异常不能阻断正式测试 | 用户确认，离线已制作；真实服务待验收 | 用户指令 2026-11-06；`app/services/memory.py`；`tests/test_memory.py` |

## 2. 文件地图与设计理由

### 2.1 根目录

| 文件 | 作用 | 为什么这样设计 |
|---|---|---|
| `README.md` | 项目入口说明：范围、已验证能力、未完成项、RAG 流程、运行方式 | 让人先知道“这是什么、能做什么、怎么启动”，不把实现细节塞进入口 |
| `pyproject.toml` | 包元数据、Python 版本和依赖声明 | 用标准项目文件固定 FastAPI、SQLAlchemy、asyncpg、pgvector、LangChain、Redis 等依赖；`include = ["app*"]` 让包可以被安装和导入 |
| `.env.example` | 配置模板，只放变量名和占位值 | 说明需要哪些配置，同时避免把真实密码、API Key 写进仓库 |
| `.env` | 本机真实配置 | 只存在本机，已被 `.gitignore` 忽略；不得在日志、文档或对话中打印内容 |
| `.gitignore` | 忽略 `.env`、虚拟环境、缓存、报告和上传文件 | 降低密钥泄露和运行产物污染仓库的风险 |
| `.git` | 独立 Git 仓库 | 当前 `origin` 为 `https://github.com/Ariechovi/ai_protection.git`，主分支提交为 `2e0fc43`（“第一次提交：最小方案”）；根仓库只会把它显示为一个未跟踪目录，检查时必须使用 `git -C ai_protection` |

### 2.2 应用入口、配置与 API 契约

| 文件 | 作用 | 为什么这样设计 |
|---|---|---|
| `app/__init__.py` | Python 包标记 | 让 `app.*` 可以被稳定导入，避免依赖工作目录的隐式包发现 |
| `app/main.py` | FastAPI 应用工厂、生命周期和路由注册；关闭时释放 Redis 和数据库连接 | 把“启动时做什么”和“请求时做什么”分开：`lifespan` 负责建表、灌入测试用例和资源清理，`create_app()` 负责组装路由，便于测试和后续拆分 |
| `app/config.py` | 用 `pydantic-settings` 读取 `.env`，集中管理模型、数据库、Redis、向量维度、测试上限和三类超时 | 避免在业务代码里散落 `os.getenv`；类型校验和默认值集中在一处，配置错误更早暴露 |
| `app/schemas.py` | Pydantic 请求/响应模型 | 把 API 契约和数据库 ORM 分开：输入有长度、枚举和默认值校验，输出可以控制字段，不把数据库内部结构直接暴露给调用方 |

`main.py` 的启动顺序是：

```text
读取 Settings
  → 如果配置了 DATABASE_URL
  → init_db()：导入模型并 create_all()
  → seed_test_cases()：表为空时写入 6 条固定用例
  → 应用开始接收请求
  → 关闭时依次释放 Redis client 和数据库 engine
```

### 2.3 API 层

| 文件 | 作用 | 为什么这样设计 |
|---|---|---|
| `app/api/health.py` | `GET /health`，返回应用名和是否配置数据库 | 作为轻量存活检查；它**不探测数据库**，所以 `/health` 为 200 不代表数据库可用 |
| `app/api/targets.py` | `POST /api/v1/targets` 登记目标；`GET /api/v1/targets` 列出目标 | 先登记目标和授权状态，运行测试时才能做授权门禁；当前没有更新、删除和分页 |
| `app/api/test_cases.py` | `GET /api/v1/test-cases`，支持按 `category` 过滤 | 测试集是产品数据，放在数据库而不是写死在代码里，便于后续扩充和启停 |
| `app/api/runs.py` | `POST /api/v1/runs` 创建运行并返回 SSE；`GET /runs/{id}` 查运行；`GET /runs/{id}/results` 查逐条结果 | 运行创建和流式执行分开：先落一条 `pending` 运行记录，再把同一个 `run_id` 交给 `run_stream`，浏览器断开后仍能通过数据库查结果 |
| `app/api/knowledge.py` | `POST /knowledge/ingest` 上传并入库；`GET /knowledge/search` 检索 | 提供知识库运维入口；当前没有鉴权、文件类型限制和大小限制，不能直接暴露到公网 |
| `app/api/mock_target.py` | 本地 OpenAI 兼容的 `/mock-target/chat/completions` | 提供一个确定性的本地目标，避免服务自己调用自己导致 502；它只返回固定安全话术，不能替代真实目标测试 |

### 2.4 数据库层

| 文件 | 作用 | 为什么这样设计 |
|---|---|---|
| `app/db/base.py` | 定义 SQLAlchemy `DeclarativeBase` | 让所有模型共享一份 metadata，`create_all()` 才能统一建表 |
| `app/db/engine.py` | 创建 async engine、session factory；`init_db()`、`get_session()`、`close_db()` | 使用异步驱动匹配 FastAPI 和 async SQLAlchemy；`init_db()` 里显式导入 `models`，避免模型未注册导致建表为空 |
| `app/db/models.py` | 定义目标、测试用例、运行、结果、知识片段和记忆六张表 | 按“目标 → 运行 → 结果”拆分，保证一次评测可以追溯；知识片段独立存向量；记忆表保存长期目标画像 |
| `app/db/seed.py` | 表为空时读取 `app/data/test_cases.json` 并灌入 | 幂等初始化：已有数据就不重复插入，避免每次启动产生重复用例 |

六张表的职责：

| 表 | 关键字段 | 职责 |
|---|---|---|
| `targets` | `id`、`endpoint`、`model`、`authorized`、`allowed_categories`、`status` | 记录受测应用、模型、鉴权变量名和授权类别 |
| `test_cases` | `id`、`category`、`severity`、`steps`、`expected_behavior`、`enabled` | 固定、可复现的测试集 |
| `test_runs` | `target_id`、`status`、`summary`、`started_at`、`finished_at` | 一次评测任务及汇总；`summary` 同时承担“上一次运行摘要”的读取来源 |
| `test_results` | `run_id`、`case_id`、`verdict`、`confidence`、`reason`、`evidence`、`latency_ms` | 单条用例的判定和证据；`evidence.references` 保存知识引用 |
| `knowledge_chunks` | `title`、`category`、`content`、`embedding`、`source_ref` | RAG 的切块、来源和 1024 维向量 |
| `memories` | `target_id`、`memory_type`、`content`、`embedding`、`metadata` | 保存 `target_profile` 长期目标画像；按目标和 1024 维向量隔离检索 |

### 2.5 服务层

| 文件 | 作用 | 为什么这样设计 |
|---|---|---|
| `app/services/llm.py` | 构造 `ChatOpenAI` 和 `OpenAIEmbeddings` | 所有模型客户端集中构造，切换供应商只需改配置；Embedding 关闭 `check_embedding_ctx_length` 以兼容 DashScope 的 OpenAI 兼容接口 |
| `app/services/rag.py` | 文本清洗、切块、Embedding、入库、pgvector 检索 | RAG 的核心边界集中在一个服务里；`chunk_text` 保持纯函数，便于单独测试；`ingest_text` 按 `source_ref` 先删后插，重复入库不会无限累积 |
| `app/services/memory.py` | Redis 短期事件、PostgreSQL 上次摘要、pgvector 长期画像、上下文渲染和写入 | 三段记忆共用一个服务，编排层只处理统一 `MemoryContext`；所有记忆故障降级为空上下文或只记录日志 |
| `app/services/target_adapter.py` | 用统一 `Transcript` 表示目标对话；支持 `mock://` 和 HTTP OpenAI 兼容目标 | 把“怎么调用目标”从测试编排中隔离；以后接不同协议只需新增适配器，不必改 `test_runner` |
| `app/services/judge.py` | 检索安全知识，把三段记忆加入 Judge Prompt，解析结构化 JSON，失败时返回 `UNKNOWN` | 判定必须基于测试用例、预期行为、历史上下文和目标回答；检索失败不应掩盖测试证据；解析失败时 fail-closed，避免误报为 PASS |
| `app/services/test_runner.py` | 读取运行和目标、筛选用例、加载记忆、执行步骤、调用 Judge、写结果、保存摘要、写长期画像并发送 SSE | 这是评测编排层：把数据库、目标适配器、三段记忆、Judge 和 SSE 串起来；记忆有超时和降级，不会替代正式测试证据 |

### 2.6 数据、知识与脚本

| 文件 / 目录 | 作用 | 为什么这样设计 |
|---|---|---|
| `app/data/test_cases.json` | 6 条固定用例，覆盖 `prompt_boundary`、`data_protection`、`tool_boundary` | 数据驱动，便于审查、扩充和版本化；每条都有步骤、预期行为和来源 |
| `knowledge/prompt_boundary.md` | 提示边界与角色保护知识 | 为 Judge 提供判定依据 |
| `knowledge/data_protection.md` | 敏感信息与数据最小化知识 | 同上 |
| `knowledge/tool_boundary.md` | 工具调用与代理边界知识 | 同上 |
| `knowledge/evaluation_policy.md` | 评测原则、判定规则、报告要求 | 统一 PASS/FAIL/UNKNOWN 的判定口径 |
| `knowledge/uploads/` | API 上传文件的运行目录 | 运行时创建，已被 `.gitignore` 忽略；当前没有清理策略 |
| `app/scripts/ingest_knowledge.py` | 批量把 4 份内置知识文档入库 | 把“初始化知识库”做成可重复执行的管理脚本，不依赖启动流程 |
| `tests/` | 16 个离线 pytest 测试 | 覆盖脱敏、mock 目标、单用例恢复、三段记忆渲染、读写降级和 Judge 记忆传递；不依赖真实 Redis/PostgreSQL |

### 2.7 为什么这样分层

这套分层不是为了让目录看起来完整，而是为了把变化点隔开：

1. 换模型供应商：改 `config.py` 和 `llm.py`，不动 API 和数据库。
2. 换受测目标协议：扩展 `target_adapter.py`，不动测试编排。
3. 换切块或检索策略：改 `rag.py`，Judge 只依赖 `search_knowledge` 的返回结构。
4. 换记忆策略：改 `memory.py`，运行编排仍只消费 `MemoryContext`。
5. 换判定规则：改 `judge.py` 和知识文档，运行记录仍然保留。
6. 换存储或前端：API 契约在 `schemas.py`，数据库细节在 `models.py`，不会互相污染。

## 3. 主数据流

### 3.1 评测请求链路

1. 客户端调用 `POST /api/v1/targets` 登记目标，写入 `targets`。
2. 客户端调用 `POST /api/v1/runs`，传入 `target_id` 和可选 `categories`。
3. `runs.py` 先查目标；目标不存在返回 404，`authorized=false` 返回 403。
4. 创建一条 `test_runs` 记录，状态为 `pending`。
5. 返回 `StreamingResponse`，媒体类型为 `text/event-stream`。
6. `run_stream()` 读取目标和启用的测试用例；按 `categories` 过滤，并受 `MAX_TEST_CASES` 限制。
7. 运行状态改为 `running`，发送 `run_started`。
8. 对每条用例依次：
   - 发送 `case_started`；
   - 从 Redis、最近一次运行摘要和 pgvector 目标画像加载三段记忆；
   - 把记忆渲染成受控文本，随测试用例一起传入 Judge；
   - `TargetAdapter.run_steps()` 逐步发送用户消息，保存目标回答；
   - `judge_case()` 检索安全知识并调用 DeepSeek；
   - 写入 `test_results`，包括 `verdict`、`reason`、`latency_ms` 和 `evidence`；
   - 发送 `case_result`。
9. 全部完成后写入 `summary`，状态改为 `completed` 或 `completed_with_errors`；
   再把本次目标画像写入 pgvector 长期记忆，发送 `run_completed`。
10. 客户端通过 `GET /runs/{id}` 和 `GET /runs/{id}/results` 回查持久化结果。

### 3.2 RAG 入库链路

```text
知识文件 / 上传文件
  → 读取 UTF-8 文本
  → 统一换行并去掉行尾空白
  → 按 800 字符切块，块间重叠 100 字符
  → 尽量在换行边界截断
  → 调用 qwen3.7-text-embedding 生成 1024 维向量
  → 按 source_ref 删除旧块
  → 写入 knowledge_chunks
```

`title` 会加 `#序号`，例如 `prompt_boundary #1`，便于定位具体块。

### 3.3 RAG 检索与判定链路

```text
测试用例的名称 + 描述 + 预期行为
  → 拼接为查询
  → 查询向量化
  → pgvector cosine distance 排序
  → 取 Top-K（当前默认 3）
  → 把命中的知识片段拼进 Judge Prompt
  → DeepSeek 返回 JSON
  → 解析 verdict / severity / confidence / reason
  → references 写入 test_results.evidence
```

相似度分数计算为 `1 - cosine_distance`。分数只用于排序和展示，当前没有最低阈值，
也没有因为分数低而拒绝检索结果；这是后续需要补的评测点。

### 3.4 RAG 在系统中的位置

这是理解本项目最重要的一点：

- RAG 发生在 **Judge 侧**，不是被测目标侧。
- 安全知识用于帮助 Judge 判断“目标回答是否符合预期”，不会作为对话上下文发给目标。
- 因此，RAG 不会改变被测系统的行为，也不会把本项目知识库变成目标的提示词。
- 当前 RAG 是“单路向量召回 + 直接拼接”，没有 Rerank、关键词混合检索、父子分段或知识图谱。
- 当前引用保存在评测结果中，不是目标回答中的引用。

### 3.5 三段记忆

| 层 | 存储位置 | 写入内容 | 读取时机 | 降级行为 |
|---|---|---|---|---|
| 短期记忆 | Redis `ai_protection:run:{run_id}:context` | 运行开始、用例开始、单条结果、错误和运行完成事件；最多 20 条，TTL 24 小时 | 每条用例执行前读取最近 10 条 | Redis 连接或解析失败时返回空列表 |
| 对话摘要记忆 | PostgreSQL `test_runs.summary` | 总数、PASS/FAIL/UNKNOWN、执行错误、覆盖类别、失败用例和安全结论文本 | 查询同一目标最近一次 `completed` / `completed_with_errors` 的运行 | 数据库查询失败时摘要为空 |
| 长期目标画像 | PostgreSQL `memories` + pgvector | 目标、模型、历史判定分布、逐用例结论和原因，类型为 `target_profile` | 用当前用例构造查询，按目标过滤后取余弦 Top-3 | Embedding 或数据库失败时返回空列表 |

`MemoryContext.render()` 把三层组合成 Judge 的“历史评测上下文”。三类记忆都只是判定
辅助信息：单次加载最多受 `MEMORY_TIMEOUT_SECONDS` 约束；超时、连接失败或写入失败只记录
日志，正式目标测试、结果落库和 SSE 完成事件仍继续。Redis 事件不保存目标回答原文，
Redis 事件和长期画像在写入前会做常见凭据脱敏。

当前限制：

- 短期的“当前会话”范围是一次 `run_id`，不是跨用户或跨聊天窗口的通用会话。
- 摘要只取最近一次完成的运行，尚未做多次运行趋势或回归差异计算。
- 每次运行都会追加一条长期画像；当前没有去重、合并、失效和容量回收策略。
- 每条用例都会为长期检索调用一次 Embedding，测试集扩大后需要评估成本和时延。

### 3.6 SSE 事件

| 事件 | 触发时机 | 主要字段 |
|---|---|---|
| `run_started` | 运行开始 | `run_id`、`target`、`count` |
| `case_started` | 单条用例开始 | `case_id`、`name` |
| `case_result` | 单条用例判定完成 | `case_id`、`verdict`、`severity`、`confidence`、`reason`、`latency_ms` |
| `error` | 目标或判定阶段异常 | `case_id`、`message` |
| `run_completed` | 全部用例完成 | `run_id`、`summary` |

## 4. 制作与验收状态

| ID | 成果 | 状态 | 已有证据 | 尚缺什么 |
|---|---|---|---|---|
| V-001 | 目标登记与列表 API | 已制作，待完整验收 | `app/api/targets.py`；数据库有 2 条目标 | 目标更新、删除、分页和权限控制 |
| V-002 | 固定测试集与初始化 | 已核验 | 数据库 `test_cases=6`；`app/data/test_cases.json` | 扩充到 30–50 条并做覆盖度评估 |
| V-003 | SSE 测试运行 | 已核验 | 历史运行返回 `run_started`、`case_result`、`run_completed` | 断线重连、取消、恢复和并发控制 |
| V-004 | `mock://` 目标 | A1 已核验 | 支持 secure、prompt-leaky、unsafe-tool 三种确定性目标；测试覆盖 PASS 和失败路径 | 它只验证编排和判定链路，不能证明真实模型安全 |
| V-005 | DeepSeek Judge | 已核验 | 结果表有 4 条判定，最近两条带 references | JSON Schema 校验、重试、低置信度人工复核 |
| V-006 | RAG 入库与检索 | 已核验 | `knowledge_chunks=4`；最近两条结果各 3 条 references | 文档扩充、召回评估、阈值、Rerank |
| V-007 | 知识上传 API | 已制作，待验收 | `app/api/knowledge.py` 已实现 | 尚未用真实上传文件走通；缺文件类型、大小和鉴权限制 |
| V-008 | 真实目标适配 | 已制作，部分加固，未验收 | `TargetAdapter` 支持 OpenAI 兼容 HTTP；已加入可配置超时和响应脱敏 | 仍需授权真实目标、鉴权配置和网络异常验证 |
| V-009 | Redis 短期记忆 | 已制作，离线和故障降级已测试；真实 Redis 待验收 | 保存 5 类紧凑事件，20 条上限、24 小时 TTL，不写目标回答原文 | 恢复 16379 隧道后验证写入、读取、TTL 和重启降级 |
| V-010 | PostgreSQL 摘要记忆 | 已制作，离线已测试；真实 PostgreSQL 待验收 | 运行 `summary` 增加覆盖类别、错误、失败用例和摘要文本；读取同目标最近一次完成运行 | 恢复 15432 后验证查询顺序、JSONB 和多次运行 |
| V-011 | pgvector 长期目标画像 | 已制作，离线已测试；真实 pgvector 待验收 | 运行结束写入 `target_profile`，包含目标、模型、判定和原因；按目标取 Top-3 | 验证 1024 维写入、余弦检索、脱敏和重复运行累积 |
| V-012 | 报告与回归对比 | 未实现 | 无 | 通过率、失败证据、OWASP/MITRE 映射、整改建议、前后差异 |
| V-013 | 最小前端 | 未实现 | 无 | 目标列表、测试集、运行进度和结果详情 |
| V-014 | 自动化测试 | A1/A2 离线测试已建立 | `16 passed`；覆盖脱敏、mock、单用例恢复、记忆渲染/读写降级和 Judge 记忆传递 | 仍需 API、真实数据库/Redis、RAG 质量和回归基线 |
| V-015 | A2 三段记忆接入 | 已制作，待真实环境端到端验收 | `memory.py`、`test_runner.py`、`judge.py` 已串联，`tests/test_memory.py` 离线覆盖 | 当前 15432/16379 未监听，缺少真实写入与回读证据 |

## 5. 变更历史

| 日期 | 变更 | 证据 / 结果 | 状态 |
|---|---|---|---|
| 2026-10-19 | 用户确认从“企业技术支持助手”转向“AI 应用安全评测与整改助手”，创建 `ai_protection` 目录和数据库 | 根 `PROJECT_MEMORY.md` C-014、C-015、C-016 | 用户确认，已执行 |
| 2026-10-19 | 创建安全评测骨架：配置、FastAPI 入口、目标、测试用例、SSE 运行和结果模型 | `/health`、`/api/v1/test-cases` 通过烟雾检查 | 已制作，待端到端验收 |
| 2026-10-19 | 使用 `mock://secure` 执行 2 条提示边界用例 | SSE 返回 2 个 PASS；Judge 和 PostgreSQL 结果接口可读回 | 核心链路已核验 |
| 2026-10-20 | 实现 RAG：切块、Embedding、pgvector 入库、Top-K 检索、Judge 引用 | 4 份知识文档各 1 个 chunk；2 条结果携带 references | 已核验 |
| 2026-10-20 | 只读复核数据库状态 | `targets=2`、`test_cases=6`、`test_runs=3`、`test_results=4`、`knowledge_chunks=4`、`memories=0`；最近两条结果各 3 条 references | 已核验 |
| 2026-10-20 | 建立独立变更记录 | 新增本文件；根 `PROJECT_MEMORY.md`、`AGENTS.md` 和 `README.md` 增加索引 | 已制作，待用户验收 |
| 2026-11-05 | 完成 A1 可测试性加固 | 增加三种 mock、凭据脱敏、目标/判定超时、逐用例失败继续和 6 个离线测试；`6 passed` | 已核验 |
| 2026-11-06 | 用户确认执行 A2，完成三段记忆代码接入 | Redis 运行事件、PostgreSQL 上次摘要、pgvector 目标画像和 Judge Prompt 已串联；记忆有超时/降级和脱敏；`16 passed` | 离线已核验；真实 Redis/PostgreSQL 待验收 |
| 2026-11-06 | 复核 A2 当前外部条件 | `127.0.0.1:15432` 与 `127.0.0.1:16379` 均未监听；未执行真实数据库或 Redis 写入 | 待隧道恢复后验收 |

### 文件级变更摘要

| 文件 | 变更 |
|---|---|
| `CHANGELOG.md` | 新建；保存本子项目的文件地图、设计理由、数据流、验收状态和变更历史 |
| `README.md` | 增加本文件入口和相关说明 |
| 根 `PROJECT_MEMORY.md` | 增加独立变更记录的索引，避免把本子项目细节继续堆在根记忆里 |
| 根 `AGENTS.md` | 在新对话入口和关键目录中增加 `ai_protection/CHANGELOG.md` |
| `app/services/redaction.py` | 新增常见 API Key、Bearer Token、密码和 Authorization 脱敏 |
| `app/services/target_adapter.py` | 支持三种 mock 目标；真实目标响应先脱敏，超时可配置 |
| `app/services/test_runner.py` | A1 单用例失败不终止整次运行；A2 每条用例加载三段记忆、保存扩展摘要并写入长期画像，记忆操作超时降级 |
| `app/config.py` | 新增目标、Judge 和记忆超时配置 |
| `tests/test_redaction.py`、`tests/test_target_adapter.py`、`tests/test_test_runner.py` | 覆盖脱敏、mock、单用例失败恢复和 Judge 记忆传递 |
| `app/services/memory.py` | 新增 Redis 短期事件、PostgreSQL 上次摘要、pgvector 长期画像、统一渲染和写入 |
| `app/services/judge.py` | Judge Prompt 增加“历史评测上下文” |
| `app/main.py` | 应用关闭时释放 Redis client，再释放数据库 engine |
| `.env.example` | 增加目标、Judge 和记忆超时配置模板 |
| `tests/test_memory.py` | 三段记忆渲染、Redis 脱敏、PostgreSQL 摘要、长期写入和失败降级测试 |

## 6. 踩过的坑与已知风险

| ID | 问题 | 当前结论 | 状态 / 来源 |
|---|---|---|---|
| X-A01 | `init_db()` 没有导入模型时，`Base.metadata` 为空，启动后可能不建表 | `engine.py` 在 `create_all()` 前显式导入 `app.db.models` | 已核验；`app/db/engine.py` |
| X-A02 | DashScope 的 OpenAI 兼容 Embedding 会因 LangChain 默认上下文长度检查被拒绝 | 使用 `check_embedding_ctx_length=False`；实测输出 1024 维 | 已解决；`app/services/llm.py` |
| X-A03 | 服务内部通过 HTTP 调用自己的 mock 目标会 502 | 增加 `mock://` 分支，直接返回本地固定回答 | 已解决；`target_adapter.py` |
| X-A04 | `/health` 不检查数据库 | 隧道断开时仍可能返回 200；排障要单独测 15432 或查询接口 | 已知限制；`health.py` |
| X-A05 | RAG 检索异常被 Judge 捕获后静默降级 | 判定仍可继续，但 references 为空；需要日志和可观测性 | 已知风险；`judge.py` |
| X-A06 | Judge 直接 `json.loads` 模型输出 | 模型返回非 JSON 时判为 UNKNOWN；缺少 Schema 校验和重试 | 已知风险；`judge.py` |
| X-A07 | 当前 4 份知识每份只有 1 个 chunk | 切块和召回策略还没有被真实长文档检验 | 已知限制；数据库计数 |
| X-A08 | 检索没有最低相似度阈值 | 低分片段也可能进入 Judge Prompt | 已知风险；`rag.py`、`judge.py` |
| X-A09 | 知识上传和搜索接口没有鉴权 | 不能直接暴露到公网；需要登录、权限和速率限制 | 已知风险；`api/knowledge.py` |
| X-A10 | 结果证据保存了目标对话原文 | A1 已对 transcript 和 Judge 证据中的常见凭据脱敏；仍未覆盖所有业务敏感字段 | 部分解决；`redaction.py` |
| X-A11 | `MAX_TEST_CASES=6` 与分类过滤叠加 | 先按类别过滤再 `limit(6)`，当前刚好覆盖 6 条；扩充测试集后可能截断 | 已知限制；`test_runner.py` |
| X-A12 | 只用 `create_all()`，没有迁移工具 | 表结构变化后不会自动修改已有表；需要引入 Alembic 或明确重建流程 | 已知风险 |
| X-A13 | `ai_protection` 是嵌套 Git 仓库 | 根仓库不能直接看到其内部改动；检查时必须执行 `git -C ai_protection status` | 已核验 |
| X-A14 | 自动化测试覆盖有限 | A1/A2 已有 16 个离线测试并通过；API、真实 PostgreSQL/Redis、RAG 质量和回归集成仍未建立 | 部分解决 |
| X-A15 | A2 的真实依赖当前不可用 | 2026-11-06 端口检查显示 15432、16379 均未监听，不能验证实际 JSONB、pgvector 和 Redis 行为 | 待隧道恢复；不写成已验收 |
| X-A16 | 记忆服务异常可能增加时延 | Redis 设置 2 秒 socket 超时；每次上下文加载和长期写入由 `MEMORY_TIMEOUT_SECONDS=15` 限制；失败后继续正式评测 | 已制作，待真实故障演练 |
| X-A17 | 长期记忆会逐运行增长 | 当前每次运行写入一条 `target_profile`，检索取 Top-3；没有合并、去重、失效或清理 | 已知限制；需要用户确认保留策略 |
| X-A18 | 每条用例都会做一次长期检索 Embedding | 当前最多 6 条用例，成本可接受；扩到 30–50 条后需改成运行级缓存或混合检索 | 已知成本风险 |
| X-A19 | 三段记忆的敏感字段覆盖仍有限 | 通用 API Key、Bearer、password/secret、Authorization 已脱敏；业务身份证、手机号、内部主机名等尚未覆盖 | 已知风险；需按真实目标扩展脱敏规则 |

## 7. 下一步边界

以下顺序是 **AI 建议**。A1 已完成；A2 已由用户确认并完成离线实现，当前首先补齐
真实依赖验收：

1. 恢复 SSH 隧道后，用 `mock://secure` 连续运行两次，验证 Redis 事件、上一次摘要、
   pgvector 长期画像和第二次运行的记忆注入。
2. 用三种 mock 目标各跑一次，验证脱敏、`completed_with_errors`、长期画像内容和目标隔离。
3. 做报告与回归对比：通过率、失败证据、OWASP/MITRE 映射、整改建议、前后差异。
4. 补最小前端：目标列表、测试集、运行进度、结果详情和记忆使用情况。
5. 把测试集从 6 条扩到 30–50 条，并建立 RAG 召回和判定一致性评测。
6. 在真实目标明确后，补充鉴权、业务敏感字段脱敏、超时和失败演练。

在这些工作开始前，应保持以下边界：

- 只测试用户明确授权的目标。
- 不执行破坏性操作、不扫描网络、不获取凭据。
- 真实响应中的敏感内容先脱敏，再写入证据。
- 不修改 `mini_app/`、`soc_agent/` 或 `AgentChat/`，除非用户明确要求。
- 不把“已制作”写成“已验收”，不把历史运行结果写成当前服务状态。

## 8. 仍待确认

| ID | 问题 | 为什么重要 | 状态 |
|---|---|---|---|
| Q-A01 | 第一个真实受测目标是什么？使用什么接口、模型和鉴权方式？ | 决定真实适配、脱敏和验收数据 | 待确认 |
| Q-A02 | 知识库首批要覆盖哪些安全规范或内部标准？ | 当前只有 4 份概念性文档，召回质量不足以支撑正式评测 | 待确认 |
| Q-A03 | PASS/FAIL/UNKNOWN 的置信度阈值和人工复核规则是什么？ | 当前没有阈值，低置信度结果也可能直接展示 | 待确认 |
| Q-A04 | 是否确定采用 Redis 短期记忆 + PostgreSQL 摘要 + pgvector 长期画像？ | 这是下一步最大的一块范围，影响表结构和接口 | 已被用户确认：2026-11-06 执行 A2；离线已制作 |
| Q-A05 | 是否需要报告页面、最小前端和导出功能？ | 影响交付形态和简历展示效果 | 待确认 |
| Q-A06 | `ai_protection` 与 `soc_agent` 的优先级如何安排？ | 根 `PROJECT_MEMORY.md` 已确认 `ai_protection` 为当前主线；两者仍不能混用数据或代码 | 已确认：当前优先 `ai_protection` |
| Q-A07 | 是否需要把当前成果提交到 `origin/main`？ | 当前 `CHANGELOG.md` 尚未提交；提交属于版本库写操作 | 待确认 |
| Q-A08 | 长期目标画像按每次运行追加，还是按目标合并为一份持续画像？ | 追加便于追溯但会持续增长；合并节省检索空间但需要定义更新和失效规则 | 待确认；当前实现为每次运行追加 |

## 9. 维护规则

- 任何 `ai_protection` 的范围、接口、表结构、模型、RAG、记忆或验收状态变化，先更新本文件。
- 根 `PROJECT_MEMORY.md` 只增加跨项目决策和本文件索引，不再复制本子项目的逐文件细节。
- 新结论覆盖旧结论时，保留旧记录并标记“已失效”或“已取代”，同时写明新证据。
- 运行过什么就写什么；没有运行的测试、没有接通的真实目标、没有验收的前端，不能写成“已完成”。
- 记录真实 API Key、数据库密码、完整敏感对话或个人信息时，必须脱敏或只写变量名。
