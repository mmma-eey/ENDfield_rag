"""RAG 模块配置 —— 全部从 .env 读取"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---- API Keys ----
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# ---- 模型名称 ----
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "qwen3-rerank")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# ---- 检索参数 ----
TOP_K_RETRIEVAL = 30        # 混合检索召回数
TOP_K_RERANK = 5            # Reranker 重排后保留数
BM25_WEIGHT = 0.5           # [已弃用] 加权融合权重，RRF 融合后不再使用
RRF_K = 60                  # RRF 平滑常数（k，排名越靠前权重越高）
EMBEDDING_DIM = 1024        # 向量维度（text-embedding-v4 → 1024 维）

# ---- 数据库连接 ----
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_DATABASE = os.getenv("PG_DATABASE", "endfield_rag")

DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
