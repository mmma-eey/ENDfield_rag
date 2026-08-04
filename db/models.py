"""SQLAlchemy ORM 模型 —— 干员关系型数据 + 知识向量切片"""
from pgvector.sqlalchemy import Vector
from sqlalchemy import (JSON, BigInteger, Boolean, Column, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from db.database import Base


class Operator(Base):
    __tablename__ = "operators"

    article_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    name_en = Column(String)
    rarity = Column(Integer, nullable=False)
    profession = Column(String, nullable=False, index=True)
    sub_profession = Column(String)
    weapon_type = Column(String)
    element = Column(String)
    faction = Column(String)
    tags = Column(JSON)
    categories = Column(JSON)
    description = Column(String)
    bio = Column(Text)
    details = Column(JSON)
    updated_at = Column(String)

    # 关系
    attributes = relationship("OperatorAttribute", back_populates="operator", cascade="all, delete-orphan")
    skills = relationship("OperatorSkill", back_populates="operator", cascade="all, delete-orphan")
    talents = relationship("OperatorTalent", back_populates="operator", cascade="all, delete-orphan")
    logistics = relationship("OperatorLogistic", back_populates="operator", cascade="all, delete-orphan")
    potentials = relationship("OperatorPotential", back_populates="operator", cascade="all, delete-orphan")
    weapons = relationship("OperatorWeapon", back_populates="operator", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="operator", cascade="all, delete-orphan")


class OperatorAttribute(Base):
    __tablename__ = "operator_attributes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    attr_key = Column(String, nullable=False)
    label = Column(String)
    advanced = Column(Boolean, default=False)
    stage = Column(Integer, nullable=False)
    base_val = Column(Float, nullable=False)
    slope = Column(Float, nullable=False)
    values = Column(JSON)

    operator = relationship("Operator", back_populates="attributes")


class OperatorSkill(Base):
    __tablename__ = "operator_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    skill_type = Column(String)
    group_id = Column(String)
    description = Column(Text)
    param_table = Column(JSON)  # [{label, values: [...]}]

    operator = relationship("Operator", back_populates="skills")


class OperatorTalent(Base):
    __tablename__ = "operator_talents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    description = Column(Text)
    unlock_stage = Column(Integer)

    operator = relationship("Operator", back_populates="talents")


class OperatorLogistic(Base):
    __tablename__ = "operator_logistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    room = Column(String)
    unlock_condition = Column(String)

    operator = relationship("Operator", back_populates="logistics")


class OperatorPotential(Base):
    __tablename__ = "operator_potentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    description = Column(Text)

    operator = relationship("Operator", back_populates="potentials")


class OperatorWeapon(Base):
    __tablename__ = "operator_weapons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    rarity = Column(Integer)
    weapon_type = Column(String)
    group_name = Column(String)

    operator = relationship("Operator", back_populates="weapons")


class OperatorMaterialSkill(Base):
    __tablename__ = "operator_materials_skill"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    skill_type = Column(String, nullable=False)
    max_level = Column(Integer)
    gold = Column(Integer)
    items = Column(JSON)


class OperatorMaterialAscension(Base):
    __tablename__ = "operator_materials_ascension"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    subtitle = Column(String)
    credits = Column(Integer)
    items = Column(JSON)


class OperatorMaterialLevelUp(Base):
    __tablename__ = "operator_materials_levelup"

    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), primary_key=True)
    exp = Column(BigInteger)
    gold = Column(Integer)


class KnowledgeChunk(Base):
    """知识切片 —— pgvector 语义检索"""
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_type = Column(String, nullable=False)  # 'bio', 'skill', 'talent', 'archive', 'voice', 'logistic'
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))  # text-embedding-v4 → 1024 维

    operator = relationship("Operator", back_populates="chunks")
