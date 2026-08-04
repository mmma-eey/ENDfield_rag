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
