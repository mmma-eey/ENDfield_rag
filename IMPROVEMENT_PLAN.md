# ENDfield RAG 项目改进方案

> 基于 `OPTIMIZATION.md`（2026-08-05 全代码库评审）与 2026-08-06 代码复读制定。
> 目标：在保持现有「意图路由 + Agent + SQL 层 + 测试体系」优秀架构的前提下，
> 消除已知 Bug、打通性能瓶颈、补齐观测性/安全短板，并为服务化与 Phase 2 功能铺路。

---

## 一、方案总览

### 1.1 现状画像

| 维度 | 现状 | 结论 |
|------|------|------|
| 功能正确性 | 评测 39/40，Q24 列表类失败 | 检索链路基本可用 |
| 性能 | 平均 7.84s/条，多处重复 IO | 主瓶颈在「每次问答重复加载/扫描」 |
| 稳定性 | generator 必崩 Bug + 全链路无超时 | 存在定时炸弹 |
| 可扩展性 | Router 类设计未接入生产路径 | 伪架构，新增流程靠手写 if/elif |
| 可观测性 | 全 print()，无日志/指标 | 线上无法排障 |
| 安全性 | pickle 反序列化 + API Key 无校验 | 服务化前置障碍 |

### 1.2 改进原则

1. **不破坏已验证的检索效果**：RRF 融合（39/40）与 SQL 补全是核心资产，性能优化只改"加载时机与缓存"，不改算法。
2. **先止血再优化**：P0（必崩 Bug / 无超时）优先，性能次之，架构重构最后，避免边改边坏。
3. **小步验证**：每个 Phase 结束都跑单测 + 全量评测，确保 39/40 不退步。
4. **为服务化预留接口**：日志、超时、请求级上下文（contextvars）、pickle 迁移四项是 FastAPI 前置条件。

### 1.3 总体路线图

```
Phase 0 止血（P0）       → Phase 1 性能（P1）    → Phase 2 架构（P1/P2）
→ Phase 3 观测性+安全（P2）→ Phase 4 质量与工程化（P2）→ Phase 5 服务化与长期
```

---

## 二、优化目标

| # | 目标 | 当前 | 目标值 | 对应项 |
|---|------|------|--------|--------|
| G1 | 消除必崩 Bug | `chat_with_history()` 调用即 NameError | 多轮对话入口可用 | 问题 1 |
| G2 | 全链路超时防护 | 所有 LLM 调用可无限挂起 | 统一 30s 超时 + 失败快速回退 | 问题 2/11 |
| G3 | 问答延迟 | 平均 7.84s | ≤ 4s（BM25/实体/枚举缓存后） | 问题 3/4/5 |
| G4 | 评测质量门槛 | `src>0 and kw>0`（Q02 假阳性） | 按类别判定，Q02 类必须命中核心数值 | 问题 7 |
| G5 | 架构一致性 | Router 类未接入 pipeline | pipeline 全量走 Router 分发 | 问题 10 |
| G6 | 可观测性 | 无日志无指标 | logging + LLM 调用/耗时/token 指标 | 问题 12 |
| G7 | 安全基线 | pickle + Key 无校验 | 非 pickle 格式 + 启动配置校验 | 问题 13/14 |
| G8 | 代码整洁 | 死代码/报告堆积/重复逻辑 | 清理 + 实体发现逻辑收敛单点 | 问题 4/8/9 |

---

## 三、技术改进措施

### 3.1 架构设计缺陷修复

#### A. Generator 必崩 Bug（P0，问题 1）
- **现状**：[generator.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/generator.py#L40-L58) `chat_with_history()` 引用未定义的 `SYSTEM_PROMPT`，应改为 `GENERATION_SYSTEM_PROMPT`（模块已导入）。
- **措施**：替换为 `GENERATION_SYSTEM_PROMPT`，并补一条单元测试覆盖该函数（mock client），防止回归。

#### B. Router 接入生产路径（P1，问题 10）
- **现状**：[pipeline.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/pipeline.py#L107-L112) 用 if/elif 分发三种 plan，[router.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/router.py#L54-L74) 的 `Router` 类只被测试使用。
- **措施**：pipeline 初始化一个 `Router` 实例，注册三个 handler：
  - `PLAN_VECTOR → _run_vector_flow`
  - `PLAN_DATABASE → _run_database_flow`
  - `PLAN_HYBRID → agent_query`（包装返回结构对齐）
  `query()` 内改为 `router.dispatch(intents, question, verbose=...)`。新增流程（如未来的 "list" 计划）只需 `register()`，不再改 query() 主体。

#### C. 实体发现逻辑收敛（P2，问题 4）
- **现状**：实体发现与格式化散落两处 —— [sql_fallback.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/sql_fallback.py#L18-L84) 四个 `_find_*` + 四个 `_format_*`，[db_query.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/db_query.py#L105-L112) 再包一层。二者互相 import，职责重叠。
- **措施**：新建 `rag/entity_service.py`（单一数据访问入口），暴露：
  - `find_entities(texts) -> Dict[str, List[str]]`（内部用缓存实体名单）
  - `format_entity(entity_type, name) -> str`
  - `field_query(question) -> List[str]`
  sql_fallback.py / db_query.py 改为薄封装调用它，保证"实体名单加载"与"格式化"各只有一份实现。**本轮不删旧函数**，先收敛调用点，评测通过后再清理。

### 3.2 性能瓶颈优化

| 瓶颈 | 位置 | 现状 | 方案 |
|------|------|------|------|
| BM25 索引每次加载 | [tools.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/tools.py#L64) `BM25Index.load()` | 每次问答反序列化 pickle | 模块级惰性单例 `_get_bm25()`，进程内常驻；`build_index.py` 重建后置空缓存 |
| 实体名单每次全表 | [sql_fallback.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/sql_fallback.py#L18-L84) | 4 次全表扫描 + 4 个独立 session | 模块级 `frozenset` 缓存干员/敌人/装备名；武器名单改由 `_find_weapons` 的正则结果缓存 |
| 字段枚举每次 DISTINCT | [db_query.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/db_query.py#L140-L143) | 每次 4 次 DISTINCT | 缓存到模块级 dict（阵营/职业/武器类型/装备部位），首次加载后纯内存匹配 |
| 连接数密集 | 全链路 | 一次问答可开 4~8 个 session | 实体名单/枚举缓存后，DB 连接数降为 2 次以内（向量检索 1 + 格式化 1） |
| 来源名解析 4 次查询 | [retriever.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/retriever.py#L100-L129) | 每类实体单独查名字映射 | 合并为一次 `id IN (...)` 查询（SQLAlchemy 已支持多实体表，一次查询 4 张表）或按 source_type 分组后最多 4 次但复用 session |

> 说明：实体名单缓存在数据重新导入后可能过期。方案：提供 `invalidate_cache()`，由 `db/import_*.py` 在导入完成后调用；初期可接受"重启进程生效"，但保留刷新入口。

### 3.3 可扩展性

- **新工具接入**：`TOOLS` 注册表已是唯一入口（[tools.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/tools.py#L110)）。补充约定：每个工具必须将检索来源写入 `ToolRuntime`，否则评测来源命中失效。
- **新意图接入**：目前意图只有 vector/database 两类，新增意图需改 intent.py + router.py + pipeline.py 三处。**措施**：将「意图集合 → plan → handler」的关系表化，`Router.register()` 已天然支持；意图分类提示词只需在 [prompts.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/prompts.py#L4-L21) 追加类别描述。
- **配置参数化**：`TOP_K_RETRIEVAL / TOP_K_RERANK / RRF_K` 改为 `.env` 可覆盖（参考 `MAX_AGENT_ITERATIONS` 的写法），支持调参实验。
- **多轮对话（Phase 4 前置）**：`chat_with_history()` 修复后，补会话记忆存储接口（内存 dict → Redis/SQLite），本轮先保证函数可用。

### 3.4 代码质量

- **评测阈值收紧（P2，问题 7）**：[eval.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/tests/eval.py#L81) `passed = src_rate > 0 and kw_rate > 0` 改为：
  - 数值类问题（operator_stat 等）：要求 `src_rate >= 0.5` 且 `expected_keywords` 全部命中；
  - 文本/对比类：`src_rate >= 0.5` 且 `kw_rate >= 0.5`；
  - 支持 query 级自定义 `strict_keywords` 字段（核心数字/名称必须出现）。
- **评测集版本化（长期，问题 8）**：`eval_queries.json` 增加 `version` 字段；报告固定输出 `report_latest.json`，删除 7 个历史 report 文件。
- **死代码清理（P2，问题 9）**：
  - [prompts.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/prompts.py#L77-L98)：`CHAT_WITH_HISTORY_PROMPT` 与 `QUERY_REWRITE_RULES` 或接入（Phase 2 查询预处理时启用 `QUERY_REWRITE_RULES`）或删除；
  - [config.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/config.py#L24) `BM25_WEIGHT`：确认无引用后删除。
- **import 规范**：generator.py 的 `from rag.prompts import ...` 提到文件顶部；`import time` 移到模块级；`eval.py:11` 改为 `from rag.config import LLM_MODEL`（不再从 generator 导入 `client`，避免触发模块级副作用）。
- **generator 懒加载（P1，问题 6）**：模块级 `client = OpenAI(...)` 改为 `_get_client()` 惰性单例，与 intent.py/agent.py 一致；配合 config 启动校验后，API Key 缺失时在调用点报错而非阻塞 import。

### 3.5 安全性

- **API Key 启动校验（P2，问题 14）**：[config.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/config.py#L8-L9) 加载后断言 `DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY` / `PG_PASSWORD` 非空，缺失时抛出带指引的 `RuntimeError`（"请复制 .env.example 为 .env 并填入密钥"）。
- **pickle 迁移（P2，问题 13）**：BM25 索引改为持久化「chunk_ids + 每文档分词（token lists）」为 JSON/gzip 格式（6061 条 token 序列体积可控），加载时逐行构建 BM25Okapi；或在服务化前保留 pickle 但增加 SHA-256 完整性校验文件。**推荐前者**，一次性成本低。
- **`.env` 管理**：确认 `.gitignore` 覆盖 `.env`（已覆盖），并在 README 强调密钥勿提交。

### 3.6 可观测性

- **logging 替换 print（P2，问题 12）**：新增 `rag/logging_setup.py`，配置 `root logger`（INFO，格式化含时间戳/模块/级别）。pipeline/agent/tools/eval 的 `print` 改为 `logger.info/debug`。
- **指标采集**：在 `agent.py` 的 LLM 调用处（[L94](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/agent.py#L94)）与 `intent.py` / `generator.py` 记录：调用次数、耗时、token 消耗（从 response.usage 读取）、工具调用链（已有 `used_tools`）。初期以结构化日志输出，服务化后接 Prometheus。
- **请求级上下文（服务化前置）**：`ToolRuntime` 目前是模块级单例（[tools.py](file:///c:/Users/lenovo/Desktop/ENDfield_rag/rag/tools.py#L35)），并发请求会互相污染。**措施**：改用 `contextvars.ContextVar` 存储 runtime，`reset_runtime()` 改为在当前 context 中重置，为 FastAPI 多请求并发做准备（本轮改造成本低）。

---

## 四、实施步骤

### Phase 0 —— 止血（P0）
| 步骤 | 内容 | 验收 |
|------|------|------|
| 0.1 | 修复 generator.py `SYSTEM_PROMPT` → `GENERATION_SYSTEM_PROMPT` | `chat_with_history` 单测通过 |
| 0.2 | 全部 `chat.completions.create` 加 `timeout=30`（intent/agent/generator）；dashscope 调用加 `timeout` 参数（TextReRank/TextEmbedding 支持） | 单测 + 手动调用不挂起 |
| 0.3 | config 启动校验必填 Key | 无 .env 时启动即清晰报错 |
| 0.4 | `intent.py` 异常分支区分网络错误（记日志、快速回退）与解析失败 | 日志可区分两类失败 |

### Phase 1 —— 性能（P1）
| 步骤 | 内容 | 验收 |
|------|------|------|
| 1.1 | BM25 索引模块级惰性单例 | 两次问答只加载一次（日志/计时验证） |
| 1.2 | 实体名单缓存为 frozenset（干员/敌人/装备），武器名正则结果缓存 | 连续两次问答 DB 查询次数下降 |
| 1.3 | 字段枚举缓存（faction/profession/weapon_type/slot_type） | 二次问答无 DISTINCT 查询 |
| 1.4 | generator 懒加载 client + import 顺序修正 | 导入模块不联网 |
| 1.5 | retriever 来源名解析合并查询 | 全量评测 avg_time ≤ 4s |

### Phase 2 —— 架构（P1/P2）
| 步骤 | 内容 | 验收 |
|------|------|------|
| 2.1 | 新建 `rag/entity_service.py`，收敛实体发现与格式化 | 单测覆盖，评测不回归 |
| 2.2 | pipeline 接入 `Router` 注册分发 | pipeline 测试通过，全量评测 39/40 |
| 2.3 | 检索参数 `.env` 参数化 | 改 .env 数值即可生效 |
| 2.4 | 请求级 contextvars 改造 ToolRuntime | 并发模拟（threading）不串数据 |

### Phase 3 —— 观测性 + 安全（P2）
| 步骤 | 内容 | 验收 |
|------|------|------|
| 3.1 | 接入 logging，替换 print | 日志含时间戳/模块/级别 |
| 3.2 | LLM 调用指标（次数/耗时/token/工具链）落日志 | 一次问答可见完整调用链 |
| 3.3 | BM25 索引改为 JSON/gzip 格式 | 加载结果与 pickle 一致，构建脚本可用 |
| 3.4 | `invalidate_cache()` 供导入脚本调用 | 重导入后缓存自动失效 |

### Phase 4 —— 质量与工程化（P2）
| 步骤 | 内容 | 验收 |
|------|------|------|
| 4.1 | 评测判定按类别收紧 + `strict_keywords` | Q02 假阳性被拦截 |
| 4.2 | 评测集版本号 + 固定输出 `report_latest.json`，清理历史 report | 目录只留最新报告 |
| 4.3 | 死代码清理（prompts/config/eval import） | 无未使用定义 |
| 4.4 | CI：GitHub Actions 跑 pytest（mock 不联网）+ 每日评测 job（API 子集） | PR 自动跑单测 |

### Phase 5 —— 长期（排期）
| 步骤 | 内容 |
|------|------|
| 5.1 | FastAPI 服务化（uvicorn + 每请求 context 已就绪） |
| 5.2 | 查询预处理（启用 QUERY_REWRITE_RULES）+ 列表类意图（Q24 修复） |
| 5.3 | 多轮对话记忆落地（chat_with_history 已修复的基础） |
| 5.4 | 评测集基准化：版本号 + 历史跑分对比看板 |

---

## 五、资源需求评估

| 类别 | 需求 | 说明 |
|------|------|------|
| 人力 | 1 名熟悉 Python / SQLAlchemy / LLM API 的工程师 | 全程 5 个 Phase 可一人承担，或拆分并行（Phase 1 性能 与 Phase 2 架构有重叠文件，建议串行） |
| 时间 | Phase 0~4 核心交付 | 不预估工期；按依赖关系 Phase 0→1→2 串行，3/4 可并行 |
| 环境 | 现有 `llm_dev` conda 环境即可 | 无需新增依赖（logging 内置；json/gzip 内置）；CI 用 GitHub Actions 免费额度 |
| API 费用 | DeepSeek + DashScope 按次计费 | 单轮全量评测（40 题）约 80+ 次 LLM 调用，日常调试建议用子集（10 题） |
| 数据风险 | 无（仅读数据 + 重建 BM25 索引一次） | BM25 格式迁移需重新 build 一次索引（1 分钟级） |

### 风险与对策
| 风险 | 对策 |
|------|------|
| 缓存引入脏数据（重导入后名单过时） | `invalidate_cache()` 接入 import_*.py |
| Router 重构影响现有 39/40 | 每个 Phase 结束全量评测回归，失败立即回滚该步 |
| pickle 迁移期间索引不可用 | 保留 `load()` 兼容旧 pkl，新格式就绪后再切换 |
| API Key 校验误伤测试环境 | 校验函数支持 `allow_missing=True` 参数，pytest conftest 关闭校验 |

---

## 六、预期效果

| 指标 | 当前 | Phase 1 后 | 全部落地后 |
|------|------|-----------|-----------|
| 评测通过率 | 39/40 | 39/40（不回归） | ≥39/40，Q24 解决后 40/40 |
| 平均问答耗时 | 7.84s | ≤ 4s | 3~4s |
| BM25 索引加载 | 每次问答 1 次 | 仅首问 1 次 | 仅首问 1 次 |
| DB 连接数/问答 | 4~8 次 | ≤ 3 次 | ≤ 2 次 |
| LLM 调用挂起 | 无限 | 30s 超时 | 30s 超时 + 快速回退 |
| 多轮对话入口 | 必崩 | 可用 | 可用 + 记忆 |
| 并发安全 | 模块级单例（串数据） | — | contextvars 请求隔离 |
| 排障手段 | print 无级别 | 结构化日志 + 调用链 | + token/耗时指标 |
| 服务化前置项 | 3 项不满足 | — | 全部满足 |

---

## 七、验证方法

### 7.1 单元测试（不联网，CI 可跑）
- 现有 `tests/`：test_agent / test_intent / test_router / test_pipeline / test_tools / test_db_query，全部 mock。
- **新增**：
  - `test_generator.py`：`chat_with_history` 正常/空返回重试/超时参数断言；
  - `test_entity_service.py`：缓存命中、invalidate 后刷新、格式化正确；
  - `test_config.py`：Key 缺失抛错、`allow_missing` 放行；
  - `test_router_dispatch.py`：Router 注册分发全 plan 覆盖。

### 7.2 评测回归（联网，Phase 每步后执行）
- 命令：`python tests/eval.py --output tests/report_latest.json`
- 标准：通过率 ≥ 39/40；`avg_time ≤ 4s`（Phase 1 后）；Q02 判定为严格模式。

### 7.3 性能基准（Phase 1 验收）
- 写 `tests/bench.py`：同一 10 题子集跑两遍，输出单条耗时、DB 查询次数（SQLAlchemy event 监听）、BM25 加载次数。
- 对比基线：Phase 1 前后同题耗时差，验证 7.8s → ≤4s。

### 7.4 集成与并发验证
- 超时验证：临时把 `timeout` 设 1s + 不可达 base_url，确认快速失败不挂起。
- 并发验证：`threading.Thread` 并发 8 路调用 `query()`，断言各线程来源互不串扰（contextvars 改造后）。
- 索引迁移验证：新旧格式加载结果抽样比对（Top10 候选 chunk_id 一致）。

### 7.5 CI 流水线（Phase 4）
- GitHub Actions：`pytest tests/`（无 API）；每日定时 job 跑 10 题评测子集并上报通过率，防止 API 侧/数据侧回归。

---

## 八、优先级总表（对应 OPTIMIZATION.md 全部 14 项）

| 优先级 | 项目 | 对应阶段 |
|--------|------|----------|
| P0 | 1. generator 必崩 Bug；2. 全链路超时 | Phase 0 |
| P1 | 3. BM25 常驻；4. 实体名单缓存；5. 字段枚举缓存；6. generator 懒加载 | Phase 1 |
| P1/P2 | 10. Router 接入；12. logging+指标 | Phase 2 / 3 |
| P2 | 7. 评测阈值；8. 报告清理；9. 死代码；11. 意图异常；13. pickle；14. Key 校验 | Phase 0 / 3 / 4 |
| 长期 | CI、评测标准化、配置参数化、服务化前置 | Phase 4 / 5 |
