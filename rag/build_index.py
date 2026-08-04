"""
一次性构建索引：Embedding 全部切片 + 构建 BM25 索引。
运行方式: python -m rag.build_index
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from rag.bm25_index import build_bm25
from rag.embedder import populate_embeddings


def main():
    session = SessionLocal()
    try:
        print("=" * 50)
        print("Phase 1/2: Embedding 向量化 ...")
        print("=" * 50)
        populate_embeddings(session)

        print("\n" + "=" * 50)
        print("Phase 2/2: BM25 索引构建 ...")
        print("=" * 50)
        build_bm25(session)

        print("\n索引构建全部完成!")
    finally:
        session.close()


if __name__ == "__main__":
    main()
