# ENDfield RAG 项目优化清单

> 基于 2026-08-05 全代码库评审。当前架构（意图路由 + Agent + SQL 层 + 测试体系）设计优秀，
> 主要短板集中在工程细节：已知 Bug、无超时、性能瓶颈、观测性缺失。

---

## 一、综合评分

| 维度 | 评分 | 主要短板 |
|------|------|----------|
| 架构演进 | ★★★★☆ | Router 类未接入生产路径（仅测试使用） |
| 可扩展性 | ★★★★☆ | 新增工具/数据源/路由计划都有清晰入口 |
| 可测试性 | ★★★★☆ | 单测覆盖好，但无 CI、评测 pass 阈值过松 |
| 可读性/可维护性 | ★★★☆☆ | 死代码残留、报告文件堆积、import 顺序不规范 |
| 健壮性 | ★★★☆☆ | LLM 调用无超时、异常被静默吞掉 |
| 耦合性 | ★★★☆☆ | 实体发现逻辑重复、DB 连接数密集 |
| 性能 | ★★☆☆☆ | 评测平均 7.84s/条，存在多处重复 IO |
| 安全性 | ★★☆☆☆ | pickle 反序列化、API Key 无启动校验 |
| 可观测性 | ★★☆☆☆ | 全 print()，无日志/指标 |

---

## 二、P0 —— 紧急修复

### 1. generator.py 存在必崩 Bug
- **位置**：`rag/generator.py:48`
- **问题**：`chat_with_history()` 引用未定义的 `SYSTEM_PROMPT`（实际导入的是 `GENERATION_SYSTEM_PROMPT`），调用必然抛 `NameError`
- **影响**：Phase 4 多轮对话的唯一入口，当前是定时炸弹
- **修复**：改为 `GENERATION_SYSTEM_PROMPT`

### 2. 所有 LLM 调用无超时
- **位置**：`intent.py` / `agent.py` / `generator.py` 全部 `chat.completions.create` 调用
- **问题**：未传 `timeout` 参数，外部 API 挂起会无限等待
- **修复**：统一 `timeout=30`（可加入 config）

---

## 三、P1 —— 高优优化

### 3. 性能瓶颈：BM25 索引每次问答都从磁盘加载
- **位置**：`rag/tools.py:64`（`BM25Index.load()`）
- **问题**：每次问答反序列化 pickle，评测平均耗时 7.84s 的主因之一
- **修复**：进程内常驻（模块级单例 + 惰性加载）

### 4. 性能瓶颈：实体发现全表扫描 + 重复开连接
- **位置**：`rag/sql_fallback.py:18-84`（四个 `_find_*` 函数）
- **问题**：每次问答拉取全部干员名/敌人名/装备名/武器切片（4 次全表 + 4 次独立 session）
- **修复**：实体名单缓存为模块级 frozenset；四个查询合并为一个 session 或一次 SQL

### 5. 性能瓶颈：字段枚举每次全表 DISTINCT
- **位置**：`rag/db_query.py:140-143`
- **问题**：`_field_query` 每次问答从 DB 拉取全部阵营/职业/武器类型/装备部位枚举值
- **修复**：缓存到模块级（枚举值在导入后基本不变）

### 6. generator.py 模块级副作用 + import 顺序
- **位置**：`rag/generator.py:6-8`
- **问题**：`client = OpenAI(...)` 在模块导入时执行，API Key 失效即阻塞整个模块导入；`from rag.prompts import ...` 排在 client 之后，风格混乱
- **修复**：改为懒加载单例（与 `intent.py` / `agent.py` 的 `_get_client()` 模式一致）

---

## 四、P2 —— 常规优化

### 7. 评测 pass 阈值过松
- **位置**：`tests/eval.py:81`（`passed = src_rate > 0 and kw_rate > 0`）
- **问题**：Q02「卡缪90级攻击力」来源命中 0.5、关键词 0.5 被判通过，但回答实为"资料未提及"，核心数字 343 缺失
- **修复**：收紧为 `src_rate >= 0.5` 且核心关键词全命中；或按类别自定义判定

### 8. 评测报告文件堆积
- **位置**：`tests/report_*.json`（7 个文件）
- **问题**：实验残留，且 `report_pro.json` 只含 30 条，`eval_queries.json` 已扩到 40 条，数据不同步
- **修复**：只保留最新报告；评测脚本固定输出文件名（如 `report_latest.json`）

### 9. 死代码清理
- **位置**：`rag/prompts.py`（`QUERY_REWRITE_RULES`、`CHAT_WITH_HISTORY_PROMPT`）、`rag/config.py`（`BM25_WEIGHT` 已标废弃）
- **问题**：定义了但从未被调用
- **修复**：接入实际功能，或删除；`BM25_WEIGHT` 确认无人引用后移除

### 10. Router 类未接入生产流程
- **位置**：`rag/router.py:54-74`
- **问题**：`Router` 类设计了可注册处理器模式，但 `pipeline.py` 用手写 if/elif 分发
- **修复**：pipeline 改用 `Router.dispatch()`，或删除 Router 类避免"伪架构"

### 11. 意图识别异常被静默吞掉
- **位置**：`rag/intent.py:108`（`except Exception: pass`）
- **问题**：所有异常（含超时/限流）无差别吞掉，API 持续不可用时每次问答白等重试 N 次
- **修复**：区分网络错误/解析失败，网络错误记录日志并快速回退

### 12. 观测性：print() 全量替换
- **位置**：全项目（pipeline/agent/eval/tools）
- **问题**：无日志级别、无时间戳、无 token 消耗等指标
- **修复**：接入 `logging`；记录 LLM 调用次数、耗时、token 消耗、工具调用链

### 13. 安全：pickle 反序列化风险
- **位置**：`rag/bm25_index.py`（`BM25Index.load()`）
- **问题**：索引文件被替换可执行任意代码，暴露到服务端时是 RCE 入口
- **修复**：服务化前改为非 pickle 格式（JSON/parquet）或加完整性校验

### 14. API Key 无启动校验
- **位置**：`rag/config.py`
- **问题**：`.env` 缺失时 `PG_PASSWORD` 为 `None`，拼接出无效连接串；错误要等第一次调用才暴露
- **修复**：config 加载时断言必填项非空并给出清晰报错

---

## 五、性能优化预期收益

| 优化项 | 当前 | 预期 |
|--------|------|------|
| BM25 索引常驻 | 每次问答磁盘加载 | 仅首问加载 |
| 实体名单缓存 | 每次 4 次全表扫描 | 首次加载后内存匹配 |
| 字段枚举缓存 | 每次 4 次 DISTINCT | 首次加载后内存匹配 |
| 意图 + 生成串行 LLM | 至少 2 次调用 | 可考虑并行意图预判（收益小，优先级低） |

预期平均问答耗时可从 **7.8s 降至 3-4s**。

---

## 六、长期建议

1. **CI 落地**：GitHub Actions 跑 `pytest`，防止回归
2. **评测标准化**：固定评测集版本号 + 自动化跑分报告对比
3. **配置参数化**：`TOP_K_RETRIEVAL` / `TOP_K_RERANK` / `RRF_K` 支持 `.env` 覆盖
4. **服务化前置**：接 FastAPI 前先解决日志、超时、pickle 三项
