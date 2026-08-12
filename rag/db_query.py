"""数据库查询 —— 结构化数据查询层（数据库路由 / database_query 工具使用）

按问题中的实体名 + 属性/等级需求，从 PG 返回格式化的结构化数据。
复用 rag.sql_fallback 的实体发现与基础格式化逻辑，并补充属性成长数值提取。
"""
import re
from typing import Dict, List

from db.database import SessionLocal
from db.models import Equipment, Operator, OperatorAttribute
from rag.sql_fallback import (_find_enemies, _find_equipments, _find_operators,
                              _find_weapons, _format_enemy, _format_equipment,
                              _format_operator, _format_weapon_chunks)

NO_DATA_MSG = "数据库查询未找到相关实体数据。"

# 星级解析（阿拉伯数字 + 中文数字）
_CN_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_STAR_RE = re.compile(r"(?:(\d{1,2})|([一二三四五六七八九十]))\s*星")
# 装备类问题提示词（用于决定字段查询目标是装备还是干员）
_EQUIPMENT_HINT_RE = re.compile(r"装备|护甲|护手|配件|防具|部位")

# 属性中文 → attr_key 映射（覆盖评测与常见查询）
ATTR_ALIASES = {
    "攻击力": "Atk", "攻击": "Atk",
    "防御力": "Def", "防御": "Def",
    "生命值": "MaxHp", "生命": "MaxHp", "血量": "MaxHp",
    "暴击率": "CriticalRate",
    "暴击伤害": "CriticalDamageIncrease",
    "力量": "Str", "意志": "Will", "智识": "Wisd", "敏捷": "Agi",
    "治疗效率加成": "HealOutputIncrease",
    "物理伤害加成": "PhysicalDamageIncrease",
    "源石技艺强度": "PhysicalAndSpellInflictionEnhance",
    "普攻距离": "NormalAttackRange",
    "终结技伤害加成": "UltimateSkillDamageIncrease",
    "连携技冷却缩减": "ComboSkillCooldownScalar",
    "失衡效率加成": "PoiseDamageOutputScalar",
}
_LEVEL_RE = re.compile(r"(\d{1,2})\s*级")


def _format_attribute_rows(label: str, rows: List[OperatorAttribute],
                           level: int | None) -> str:
    """将某属性各阶段成长表格式化为文本；level 非空时定位到具体等级。

    rows: 按 stage 升序的属性行（含 base_val / values 列表）。
    等级换算：stage0 起始 Lv1，后续阶段起始等级 = 前阶段起始 + 前阶段值个数 - 1
    （阶段首尾等级重叠 1 级，与源数据 level_range 一致）。
    """
    # 推算各阶段等级范围
    segs: List[tuple] = []
    start = 1
    for a in sorted(rows, key=lambda x: x.stage):
        n = len(a.values) or 1
        segs.append((a, start, start + n - 1))
        start = start + n - 1

    if level is None:
        overview = "、".join(
            f"Lv{s}~{e}:{a.values[0] if a.values else a.base_val}"
            f"→{a.values[-1] if a.values else a.base_val}"
            for a, s, e in segs
        )
        return f"[属性] {label}成长：{overview}"

    for a, s, e in segs:
        if s <= level <= e:
            off = level - s
            if 0 <= off < len(a.values):
                v = a.values[off]
                return (f"[属性] {label}：Lv{level}≈{v}"
                        f"（{label}阶段Lv{s}~{e}范围 {a.values[0]}~{a.values[-1]}）")
    return f"[属性] {label}：查无 Lv{level} 数据"


def _match_operator_attributes(question: str, name: str) -> List[str]:
    """若问题中同时出现干员名 + 属性名（可含等级），返回属性数值文本。"""
    if name not in question:
        return []
    # 按名称长度降序匹配，避免"攻击"被"攻击力"子串吞并导致的重复查询
    labels = sorted((k for k in ATTR_ALIASES if k in question), key=len, reverse=True)
    labels = [k for i, k in enumerate(labels)
              if not any(k in other for other in labels[:i])]
    if not labels:
        return []
    m = _LEVEL_RE.search(question)
    level = int(m.group(1)) if m else None

    db = SessionLocal()
    texts = []
    try:
        op = db.query(Operator).filter(Operator.name == name).first()
        if op:
            for label in labels:
                key = ATTR_ALIASES[label]
                rows = [a for a in op.attributes if a.attr_key == key]
                if rows:
                    texts.append(_format_attribute_rows(label, rows, level))
    finally:
        db.close()
    return texts


def find_entities(texts: List[str]) -> Dict[str, List[str]]:
    """从文本中提取命中的实体名，按类型分组：operators/weapons/enemies/equipments。"""
    return {
        "operators": _find_operators(texts),
        "weapons": _find_weapons(texts),
        "enemies": _find_enemies(texts),
        "equipments": _find_equipments(texts),
    }


def _parse_rarity(question: str):
    """解析问题中的星级（支持 5星/五星），无则返回 None"""
    m = _STAR_RE.search(question)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    return _CN_NUMS.get(m.group(2))


def _match_enum(keywords: List[str], question: str) -> str | None:
    """返回问题中包含的字段枚举值（最长优先，避免"护甲"误吞"护手"等）"""
    hits = [k for k in keywords if k and k in question]
    hits.sort(key=len, reverse=True)
    return hits[0] if hits else None


def _field_query(question: str) -> List[str]:
    """字段模糊查询：按 阵营/职业/武器类型/装备部位/星级 过滤。

    针对"有哪些 X 的干员/装备"类列表查询（Q24/Q38 场景）：
    问题中无实体名，但含字段枚举值（如"终末地工业"、"5星"、"先锋"）。
    """
    db = SessionLocal()
    try:
        factions = [r[0] for r in db.query(Operator.faction).distinct() if r[0]]
        professions = [r[0] for r in db.query(Operator.profession).distinct() if r[0]]
        weapon_types = [r[0] for r in db.query(Operator.weapon_type).distinct() if r[0]]
        slot_types = [r[0] for r in db.query(Equipment.slot_type).distinct() if r[0]]
    finally:
        db.close()

    rarity = _parse_rarity(question)
    faction = _match_enum(factions, question)
    profession = _match_enum(professions, question)
    weapon_type = _match_enum(weapon_types, question)
    slot_type = _match_enum(slot_types, question)

    lines: List[str] = []

    # ---- 装备字段查询（命中部位词，且问题偏装备语境）----
    if slot_type and (_EQUIPMENT_HINT_RE.search(question) or not (faction or profession or weapon_type)):
        conditions = [Equipment.slot_type == slot_type]
        if rarity:
            conditions.append(Equipment.rarity == rarity)
        db = SessionLocal()
        try:
            rows = db.query(Equipment).filter(*conditions).order_by(Equipment.rarity.desc()).all()
        finally:
            db.close()
        for e in rows:
            lines.append(f"[{e.name}] {e.rarity}星{e.slot_type}")
        return lines

    # ---- 干员字段查询 ----
    conditions = []
    if faction:
        conditions.append(Operator.faction == faction)
    if profession:
        conditions.append(Operator.profession == profession)
    if weapon_type:
        conditions.append(Operator.weapon_type == weapon_type)
    if rarity:
        conditions.append(Operator.rarity == rarity)
    if not conditions:
        return []

    db = SessionLocal()
    try:
        rows = db.query(Operator).filter(*conditions).order_by(Operator.rarity.desc()).all()
    finally:
        db.close()
    for o in rows:
        lines.append(f"[{o.name}] {o.rarity}星{o.profession}，{o.weapon_type}，所属{o.faction}")
    return lines


# 装备部位枚举（用于从字段查询结果反推实体类型）
_EQUIPMENT_SLOTS = {"护甲", "护手", "配件", "轻甲", "重甲"}


def field_query_entities(question: str) -> Dict[str, List[str]]:
    """字段查询命中的实体名分组（供 pipeline 构建引用来源/评测）。

    行格式：干员 [卡缪] 6星先锋，长柄武器，所属终末地工业
            装备 [50式应龙轻甲] 5星护甲
    """
    entities: Dict[str, List[str]] = {"operators": [], "weapons": [], "enemies": [], "equipments": []}
    for line in _field_query(question):
        m = re.match(r"\[([^\]]+)\] (\d+)星([^，,、]+)", line)
        if not m:
            continue
        name, tail = m.group(1), m.group(3)
        if tail in _EQUIPMENT_SLOTS:
            entities["equipments"].append(name)
        else:
            entities["operators"].append(name)
    return entities


def query_database(question: str, extra_texts: List[str] | None = None) -> str:
    """按问题从结构化数据库查询实体信息（含属性/等级数值），返回格式化文本。

    未命中任何实体时返回 NO_DATA_MSG（调用方应回退到向量检索）。
    """
    all_texts = [question] + (extra_texts or [])
    entities = find_entities(all_texts)

    parts: List[str] = []
    for name in entities["operators"]:
        base = _format_operator(name)
        if base:
            parts.append(base)
        parts.extend(_match_operator_attributes(question, name))
    for name in entities["weapons"]:
        parts.extend(_format_weapon_chunks(name, set()))
    for name in entities["enemies"]:
        parts.append(_format_enemy(name))
    for name in entities["equipments"]:
        parts.append(_format_equipment(name))

    parts = [p for p in parts if p]
    if parts:
        return "\n".join(parts)

    # 无实体命中 → 字段模糊查询（阵营/职业/武器类型/装备部位/星级 列表查询）
    parts = _field_query(question)
    if not parts:
        return NO_DATA_MSG
    return "\n".join(parts)
