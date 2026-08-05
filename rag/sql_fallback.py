"""SQL Fallback —— RAG 召回后，自动从 SQL 表补充实体结构化数据"""
import re
from typing import List

from db.database import SessionLocal
from db.models import Enemy, Equipment, KnowledgeChunk, Operator

# 装备获取方式中文映射（与 import_equipments 保持一致）
UNLOCK_LABELS = {
    "EquipFormulaChest": "装备图纸箱",
    "AdventureLevel": "冒险等级解锁",
    "DomainShop": "域商店",
    "StarShop": "星商店",
    "DefaultUnlock": "默认解锁",
}


def _find_operators(texts: List[str]) -> List[str]:
    """从文本列表中提取已知干员名"""
    db = SessionLocal()
    known = set(row[0] for row in db.query(Operator.name).all())
    db.close()
    found = set()
    for t in texts:
        for name in known:
            if name in t:
                found.add(name)
    return list(found)


def _find_weapons(texts: List[str]) -> List[str]:
    """从文本列表中提取武器名（基于 weapon_skill 切片的命名规则）"""
    db = SessionLocal()
    chunks = (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.chunk_type.in_(
                ["weapon_skill", "weapon_flavor", "weapon_background", "weapon_recommend"]
            )
        )
        .all()
    )
    db.close()

    # 从切片内容中提取武器名：模式 "武器名 - 技能名" 或 "武器名：描述"
    weapon_names = set()
    for c in chunks:
        # 匹配 "XXX - " 或 "武器XXX" 开头
        m = re.match(r"^(?:武器)?(.+?)(?:\s*[-：:])", c.content)
        if m:
            weapon_names.add(m.group(1).strip())

    found = set()
    for t in texts:
        for w in weapon_names:
            if w in t:
                found.add(w)
    return list(found)


def _find_enemies(texts: List[str]) -> List[str]:
    """从文本列表中提取已知敌人名"""
    db = SessionLocal()
    known = set(row[0] for row in db.query(Enemy.name).all())
    db.close()
    found = set()
    for t in texts:
        for name in known:
            if name in t:
                found.add(name)
    return list(found)


def _find_equipments(texts: List[str]) -> List[str]:
    """从文本列表中提取已知装备名"""
    db = SessionLocal()
    known = set(row[0] for row in db.query(Equipment.name).all())
    db.close()
    found = set()
    for t in texts:
        for name in known:
            if name in t:
                found.add(name)
    return list(found)


def _format_operator(name: str) -> str:
    """查询操作员基本信息，返回格式化文本"""
    db = SessionLocal()
    op = db.query(Operator).filter(Operator.name == name).first()
    if not op:
        db.close()
        return ""

    details = op.details or {}
    main_attr = details.get("主属性", "")
    sub_attr = details.get("副属性", "")

    parts = [
        f"[{op.name}][basic]",
        f"{op.name}，{op.rarity}星{op.profession}",
    ]
    if op.sub_profession:
        parts[1] += f"·{op.sub_profession}"
    if op.element:
        parts.append(f" 元素：{op.element}")
    if op.weapon_type:
        parts.append(f" 武器类型：{op.weapon_type}")
    if main_attr:
        parts.append(f" 主属性：{main_attr}")
    if sub_attr:
        parts.append(f" 副属性：{sub_attr}")
    if op.faction:
        parts.append(f" 所属：{op.faction}")
    if op.skills:
        parts.append(" 技能：" + "、".join(
            f"{s.name}（{s.skill_type}）" for s in op.skills if s.name
        ))
    if op.talents:
        parts.append(" 天赋：" + "、".join(t.name for t in op.talents if t.name))

    db.close()
    return "；".join(parts)


def _format_weapon_chunks(name: str, already_retrieved: set) -> List[str]:
    """查询某武器的所有 skill 切片，去重"""
    db = SessionLocal()
    # 武器名在内容开头的四种模式
    patterns = [
        f"{name} -%", f"{name}：%", f"{name}:%", f"武器{name}%",
        f"干员%的技能适配武器推荐：%{name}%",
        f"武器{name}可适配%",
    ]
    from sqlalchemy import or_

    conditions = []
    for p in patterns:
        conditions.append(KnowledgeChunk.content.ilike(p))

    chunks = (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.chunk_type.in_(
                ["weapon_skill", "weapon_flavor", "weapon_background", "weapon_recommend"]
            ),
            or_(*conditions),
        )
        .all()
    )
    db.close()

    results = []
    for c in chunks:
        key = c.content[:120]
        if key not in already_retrieved:
            already_retrieved.add(key)
            results.append(f"[{name}][{c.chunk_type}] {c.content}")
    return results


def _format_enemy(name: str) -> str:
    """查询敌人信息（类型/抗性/技能/掉落），返回格式化文本"""
    db = SessionLocal()
    en = db.query(Enemy).filter(Enemy.name == name).first()
    if not en:
        db.close()
        return ""

    parts = [
        f"[{en.name}][enemy]",
        f"{en.name}，{en.display_type or '普通'}敌人" + ("（危险标记）" if en.is_dangerous else ""),
    ]
    if en.resistances:
        parts.append("抗性：" + "、".join(
            f"{r.element_label or r.element} {r.percent}%" for r in en.resistances
        ))
    for ab in en.abilities:
        parts.append(f"技能{ab.ordinal}：{ab.description}")
    if en.drops:
        parts.append("掉落：" + "、".join(
            f"{d.item_name}（{d.rarity}星）" for d in en.drops
        ))

    db.close()
    return "；".join(parts)


def _format_equipment(name: str) -> str:
    """查询装备信息（部位/星级/组/属性/获取方式），返回格式化文本"""
    db = SessionLocal()
    eq = db.query(Equipment).filter(Equipment.name == name).first()
    if not eq:
        db.close()
        return ""

    parts = [
        f"[{eq.name}][equipment]",
        f"{eq.name}，{eq.rarity}星{eq.slot_type}装备，{eq.group_name}",
    ]
    if eq.stats:
        parts.append("属性：" + "、".join(s.label for s in eq.stats))
    if eq.description:
        parts.append(f"描述：{eq.description}")
    if eq.flavor:
        parts.append(f"风味：{eq.flavor}")
    if eq.unlock_type:
        parts.append("获取方式：" + UNLOCK_LABELS.get(eq.unlock_type, eq.unlock_type))

    db.close()
    return "；".join(parts)


def enrich(question: str, reranked_contexts: List[str]) -> List[str]:
    """根据 RAG 返回的上下文，从 SQL 补充缺失的结构化数据。

    返回：补充文本列表，可直接拼接进 LLM 上下文。
    """
    all_texts = [question] + reranked_contexts

    operators = _find_operators(all_texts)
    weapons = _find_weapons(all_texts)
    enemies = _find_enemies(all_texts)
    equipments = _find_equipments(all_texts)

    supplements = []

    # 补干员基本信息
    for name in operators:
        supplements.append(_format_operator(name))

    # 补武器技能数据（去重：已召回的跳过）
    already_retrieved = set()
    for ctx in reranked_contexts:
        already_retrieved.add(ctx[:120])

    for name in weapons:
        supplements.extend(_format_weapon_chunks(name, already_retrieved))

    # 补敌人信息
    for name in enemies:
        supplements.append(_format_enemy(name))

    # 补装备信息
    for name in equipments:
        supplements.append(_format_equipment(name))

    return supplements
