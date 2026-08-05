"""SQLAlchemy ORM 模型 —— 干员/武器关系型数据 + 知识向量切片"""
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
    weapon_article_id = Column(String, ForeignKey("weapons.article_id", ondelete="SET NULL"), nullable=True, index=True)

    operator = relationship("Operator", back_populates="weapons")
    weapon = relationship("Weapon", back_populates="operators", foreign_keys=[weapon_article_id])


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


class TermMapping(Base):
    """玩家黑话 → 游戏官方术语映射"""
    __tablename__ = "term_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slang = Column(String, nullable=False, index=True)       # 玩家用语：大招、被动、灼烧
    official = Column(String, nullable=False)                 # 官方术语：终结技、天赋、灼热附着
    category = Column(String, default="general")              # 分类：skill / element / profession / general
    priority = Column(Integer, default=1)                     # 权重，越高越优先匹配


class KnowledgeChunk(Base):
    """知识切片 —— pgvector 语义检索，可归属干员/武器/敌人/装备"""
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.article_id", ondelete="CASCADE"), nullable=True, index=True)
    weapon_id = Column(String, ForeignKey("weapons.article_id", ondelete="CASCADE"), nullable=True, index=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=True, index=True)
    equipment_id = Column(String, ForeignKey("equipments.article_id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_type = Column(String, nullable=False)  # 'bio', 'skill', ..., 'enemy_background', 'enemy_ability', ...
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))  # text-embedding-v4 → 1024 维

    operator = relationship("Operator", back_populates="chunks")
    weapon = relationship("Weapon", back_populates="chunks")
    enemy = relationship("Enemy", back_populates="chunks")
    equipment = relationship("Equipment", back_populates="chunks")


# ======================== 武器相关表 ========================

class Weapon(Base):
    __tablename__ = "weapons"

    article_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    name_en = Column(String)
    rarity = Column(Integer, nullable=False, index=True)
    weapon_type = Column(String, nullable=False, index=True)
    max_lv = Column(Integer)
    description = Column(Text)
    flavor = Column(Text)
    categories = Column(JSON)
    total_level_exp = Column(BigInteger)
    total_level_gold = Column(Integer)
    total_break_gold = Column(Integer)
    background = Column(Text)  # 武器故事
    updated_at = Column(String)

    stages = relationship("WeaponStage", back_populates="weapon", cascade="all, delete-orphan")
    skills = relationship("WeaponSkill", back_populates="weapon", cascade="all, delete-orphan")
    materials = relationship("WeaponMaterial", back_populates="weapon", cascade="all, delete-orphan")
    gems = relationship("WeaponGem", back_populates="weapon", cascade="all, delete-orphan")
    operators = relationship("OperatorWeapon", back_populates="weapon", foreign_keys="OperatorWeapon.weapon_article_id")
    chunks = relationship("KnowledgeChunk", back_populates="weapon", cascade="all, delete-orphan")


class WeaponStage(Base):
    """武器各突破阶段攻击力成长公式"""
    __tablename__ = "weapon_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    weapon_id = Column(String, ForeignKey("weapons.article_id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(Integer, nullable=False)
    level_range = Column(JSON)      # [start_lv, end_lv]
    levels = Column(Integer)
    base_atk = Column(Float)
    slope_atk = Column(Float)
    atk_values = Column(JSON)       # 逐级精确值

    weapon = relationship("Weapon", back_populates="stages")


class WeaponSkill(Base):
    """武器技能（主属性/副属性/武器技）"""
    __tablename__ = "weapon_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    weapon_id = Column(String, ForeignKey("weapons.article_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    skill_id = Column(String)
    type_label = Column(String)     # 潜能技能 或 空（主/副属性）
    description = Column(Text)
    zero_potential_max_level = Column(Integer)
    levels_data = Column(JSON)      # [{level, desc, values}]
    param_table = Column(JSON)      # [{label, values}]

    weapon = relationship("Weapon", back_populates="skills")


class WeaponMaterial(Base):
    """武器突破材料"""
    __tablename__ = "weapon_materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    weapon_id = Column(String, ForeignKey("weapons.article_id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(Integer, nullable=False)
    unlock_lv = Column(Integer)
    gold = Column(Integer)
    items = Column(JSON)            # [{id, name, qty, tier}]

    weapon = relationship("Weapon", back_populates="materials")


class WeaponGem(Base):
    """武器推荐基质（嵌合宝石）"""
    __tablename__ = "weapon_gems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    weapon_id = Column(String, ForeignKey("weapons.article_id", ondelete="CASCADE"), nullable=False, index=True)
    gem_id = Column(String)
    display_name = Column(String)
    tier_name = Column(String)
    rarity = Column(Integer)
    terms = Column(JSON)            # [{label, level, type_label}]
    domains = Column(JSON)          # [{domain_id, domain_name}]
    drop_points = Column(JSON)      # [{name, domain_name, world_level, recommend_lv}]

    weapon = relationship("Weapon", back_populates="gems")


# ======================== 敌人相关表 ========================

class Enemy(Base):
    __tablename__ = "enemies"

    article_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    nickname = Column(String)
    display_type = Column(String)       # Normal / Elite / Boss ...
    is_dangerous = Column(Boolean, default=False)
    background = Column(Text)           # 档案描述
    level_curve = Column(JSON)          # {"1": {"hp":.., "atk":.., "def":..}, ...}
    updated_at = Column(String)

    attributes = relationship("EnemyAttribute", back_populates="enemy", cascade="all, delete-orphan")
    resistances = relationship("EnemyResistance", back_populates="enemy", cascade="all, delete-orphan")
    abilities = relationship("EnemyAbility", back_populates="enemy", cascade="all, delete-orphan")
    drops = relationship("EnemyDrop", back_populates="enemy", cascade="all, delete-orphan")
    variants = relationship("EnemyVariant", back_populates="enemy", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="enemy", cascade="all, delete-orphan")


class EnemyAttribute(Base):
    """敌人战斗属性（普攻距离/重量/失衡值/抗打断/韧性等）"""
    __tablename__ = "enemy_attributes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=False, index=True)
    group_key = Column(String)          # basic / poise / superarmor / resilience / misc
    group_label = Column(String)        # 基础战斗 / 失衡 / 抗打断 ...
    label = Column(String, nullable=False)
    value = Column(Float)
    format = Column(String)             # scalar / int / percent / multiplier / seconds
    attr_type = Column(String)          # 内部属性类型（Weight 等）

    enemy = relationship("Enemy", back_populates="attributes")


class EnemyResistance(Base):
    """敌人元素抗性"""
    __tablename__ = "enemy_resistances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=False, index=True)
    element = Column(String, nullable=False)        # Physical / Fire / Pulse ...
    element_label = Column(String)                   # 物理 / 灼热 / 电磁 ...
    percent = Column(Float)                          # 抗性百分比 100 表示无减免
    scalar = Column(Float)                           # 伤害系数

    enemy = relationship("Enemy", back_populates="resistances")


class EnemyAbility(Base):
    """敌人技能"""
    __tablename__ = "enemy_abilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal = Column(Integer)
    ability_id = Column(String)
    description = Column(Text)

    enemy = relationship("Enemy", back_populates="abilities")


class EnemyDrop(Base):
    """敌人掉落物"""
    __tablename__ = "enemy_drops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String, nullable=False)
    item_id = Column(String)
    rarity = Column(Integer)

    enemy = relationship("Enemy", back_populates="drops")


class EnemyVariant(Base):
    """敌人变体（如 仿生翅天使α），数值由主形态曲线 + modifiers 派生"""
    __tablename__ = "enemy_variants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enemy_id = Column(String, ForeignKey("enemies.article_id", ondelete="CASCADE"), nullable=False, index=True)
    variant_enemy_id = Column(String)               # eny_xxx_reaper 等内部 id
    is_dangerous = Column(Boolean, default=False)
    modifiers = Column(JSON)                        # [{text, label, attr_type}]
    level_curve = Column(JSON)                      # 变体自己的等级曲线

    enemy = relationship("Enemy", back_populates="variants")


# ======================== 装备相关表 ========================

class Equipment(Base):
    """装备（护甲/护手/配件）"""
    __tablename__ = "equipments"

    article_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    rarity = Column(Integer, nullable=False, index=True)
    part_type = Column(String)                      # Body / Hand / EDC
    slot_type = Column(String, nullable=False, index=True)  # 护甲/护手/配件
    group_name = Column(String, index=True)         # 装备组
    suit_name = Column(String)
    description = Column(Text)
    flavor = Column(Text)
    icon_url = Column(String)
    categories = Column(JSON)
    unlock_type = Column(String)                    # EquipFormulaChest / AdventureLevel / DomainShop / StarShop / DefaultUnlock
    unlock_key = Column(String)
    suit_piece_count = Column(Integer)              # 套装件数
    suit_self_equip_id = Column(String)
    suit_bonus = Column(JSON)
    suit_pieces = Column(JSON)                      # [{name, rarity, part_type, slot_type, equip_id}]
    updated_at = Column(String)

    stats = relationship("EquipmentStat", back_populates="equipment", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="equipment", cascade="all, delete-orphan")


class EquipmentStat(Base):
    """装备属性（强化 0~3 级数值）"""
    __tablename__ = "equipment_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(String, ForeignKey("equipments.article_id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String, nullable=False)
    attr_type = Column(String)
    is_base = Column(Boolean, default=False)        # 基础属性（强化不提升）
    is_percent = Column(Boolean, default=False)
    enhances = Column(Boolean, default=False)       # 是否随强化提升
    values = Column(JSON)                           # [0级, 1级, 2级, 3级]
    modifier_type = Column(String)
    composite_attr = Column(String)

    equipment = relationship("Equipment", back_populates="stats")
