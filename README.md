# ENDfield RAG —— 明日方舟：终末地 智能问答系统

基于 RAG (Retrieval-Augmented Generation) 技术，为《明日方舟：终末地》玩家提供精确的游戏数据问答服务。

> 数据来源：[fz.wiki](https://www.fz.wiki) | 基于 PostgreSQL + pgvector | Python 3.11+

---

## v0.1.0 — 纯 RAG Demo

**实现功能**

- 干员数据爬取与结构化（30 位干员，来源 `api.fz.wiki`）
- PostgreSQL + pgvector 混合存储（关系表 + 向量表）
- 文本切片与向量化（text-embedding-v4，2982 条切片）
- BM25 + Cosine 混合检索
- Qwen3 Reranker 重排序
- DeepSeek 生成回答
- CLI 交互式问答

**技术栈**

| 层 | 组件 |
|---|------|
| 爬虫 | Python requests |
| 数据库 | PostgreSQL 18.4 + pgvector |
| Embedding | DashScope text-embedding-v4 (1024d) |
| 重排序 | DashScope qwen3-rerank |
| 生成 | DeepSeek Chat |
| 分词 | jieba + rank-bm25 |

---

## 快速开始

### 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd ENDfield_rag

# 创建虚拟环境（Python 3.11+）
conda create -n llm_dev python=3.11
conda activate llm_dev
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key 和数据库密码
```

### 数据库初始化

```bash
# 确保 PostgreSQL 已安装 pgvector 扩展
# 创建数据库
createdb endfield_rag

# 建表 + 导入数据
python -m db.import_data
```

### 构建索引

```bash
# 向量化所有切片 + 生成 BM25 索引
python -m rag.build_index
```

### 运行问答

```bash
python -m rag.pipeline "卡缪的战技是什么，有什么效果"
```

---

## 项目结构

```
ENDfield_rag/
├── crawler/                    # 数据爬取
│   ├── fetch_operators.py      # 批量拉取 API
│   └── processor.py            # JSON 结构化
├── db/                         # 数据库
│   ├── database.py             # 连接管理
│   ├── models.py               # ORM（11 张表）
│   └── import_data.py          # JSON → PG
├── rag/                        # RAG 引擎
│   ├── config.py               # 配置（从 .env 读取）
│   ├── prompts.py              # 提示词管理
│   ├── embedder.py             # 文本向量化
│   ├── bm25_index.py           # BM25 关键词索引
│   ├── retriever.py            # 混合检索
│   ├── reranker.py             # 重排序
│   ├── generator.py            # LLM 生成
│   ├── pipeline.py             # 完整问答流程
│   └── build_index.py          # 一次性索引构建
├── data_main/                  # 本地数据（不入库）
│   └── operator_data/          # 30 份干员 JSON
├── operator.json               # 干员名单
├── .env.example                # 环境变量模板
├── requirements.txt
└── .gitignore
```

---

## 开发路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| v0.1.0 | 干员数据爬取 + 纯 RAG Demo | 完成 |
| v0.2.0 | SQL fallback + 查询预处理 | 计划中 |
| v0.3.0 | FastAPI 后端 + Vue3 前端 | 计划中 |
| v1.0.0 | Docker 部署 + 多源扩展 | 计划中 |

---

## License

MIT
