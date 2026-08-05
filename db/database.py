"""数据库连接管理"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from rag.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_size=5, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表"""
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("所有表创建完成")


def seed_terms():
    """初始化玩家黑话 → 官方术语映射"""
    from db.seed_terms import SEED_TERMS
    from db.models import TermMapping

    db = SessionLocal()
    existing = db.query(TermMapping).count()
    if existing > 0:
        print(f"term_mappings 已有 {existing} 条数据，跳过种子写入")
        db.close()
        return

    for t in SEED_TERMS:
        db.add(TermMapping(**t))
    db.commit()
    print(f"term_mappings 写入 {len(SEED_TERMS)} 条种子数据")
    db.close()
