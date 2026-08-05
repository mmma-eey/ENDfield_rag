"""
敌人 API 响应 → 结构化 JSON 的处理逻辑。
解析 endfieldCardEnemy* 系列组件：基础信息/背景/属性曲线/抗性/技能/掉落/提示/变体。
"""
from typing import Any, Dict, List


def _level_curve_to_dict(curve: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """等级曲线 → {level: {hp, atk, def}}，便于按等级精确查询"""
    return {
        str(c["level"]): {
            "hp": c.get("hp"),
            "atk": c.get("atk"),
            "def": c.get("def"),
        }
        for c in curve
    }


def process_enemy(raw_json: dict) -> dict:
    """输入 API 原始 JSON，输出结构化敌人数据 dict。"""
    article = raw_json["article"]
    revision = raw_json["revision"]
    content = revision["contentJson"]["content"]

    hero: Dict[str, Any] = {}
    background: Dict[str, Any] = {}
    stats: Dict[str, Any] = {}
    resistances: List[Dict[str, Any]] = []
    abilities: List[Dict[str, Any]] = []
    drops: List[Dict[str, Any]] = []
    tips: List[str] = []
    variants: List[Dict[str, Any]] = []

    for c in content:
        t = c.get("type")
        attrs = c.get("attrs", {})
        if t == "endfieldCardEnemyHero":
            hero = attrs
        elif t == "endfieldCardEnemyBackground":
            background = attrs
        elif t == "endfieldCardEnemyStats":
            stats = attrs
        elif t == "endfieldCardEnemyResistances":
            resistances = attrs.get("rows", [])
        elif t == "endfieldCardEnemyAbilities":
            abilities = attrs.get("abilities", [])
        elif t == "endfieldCardEnemyDrops":
            drops = attrs.get("items", [])
        elif t == "endfieldCardEnemyTips":
            tips = attrs.get("tips", [])
        elif t == "endfieldCardEnemyVariants":
            variants = attrs.get("variants", [])

    # ---- 基础战斗/失衡/抗打断/韧性/其他 分组属性 ----
    groups_attrs: List[Dict[str, Any]] = []
    for g in stats.get("groups", []):
        for row in g.get("rows", []):
            groups_attrs.append({
                "group_key": g.get("key", ""),
                "group_label": g.get("label", ""),
                "label": row.get("label", ""),
                "value": row.get("value"),
                "format": row.get("format", ""),
                "attr_type": row.get("attrType", ""),
            })

    # ---- 抗性 ----
    resistances_out = [{
        "element": r.get("element", ""),
        "element_label": r.get("elementLabel", ""),
        "percent": r.get("percent"),
        "scalar": r.get("scalar"),
    } for r in resistances]

    # ---- 技能 ----
    abilities_out = [{
        "ordinal": a.get("ordinal"),
        "ability_id": a.get("abilityId", ""),
        "description": a.get("description", ""),
    } for a in abilities]

    # ---- 掉落 ----
    drops_out = [{
        "name": d.get("name", ""),
        "item_id": d.get("itemId", ""),
        "rarity": d.get("rarity"),
    } for d in drops]

    # ---- 变体 ----
    variants_out = [{
        "enemy_id": v.get("enemyId", ""),
        "is_dangerous": v.get("isDangerous", False),
        "modifiers": [{
            "text": m.get("text", ""),
            "label": m.get("label", ""),
            "attr_type": m.get("attrType", ""),
        } for m in v.get("modifiers", [])],
        "level_curve": _level_curve_to_dict(v.get("curve", [])),
    } for v in variants]

    return {
        "meta": {
            "source": "fz.wiki",
            "article_id": article["id"],
            "updated_at": article["updatedAt"],
        },
        "basic": {
            "name": hero.get("name", ""),
            "nickname": hero.get("nickname", ""),
            "display_type": hero.get("displayType", ""),
            "is_dangerous": hero.get("isDangerous", False),
            "zmd_map_links": hero.get("zmdMapLinks", []),
            "distributions": hero.get("distributions", []),
        },
        "background": {
            "body": background.get("body", ""),
        },
        "stats": {
            "level_curve": _level_curve_to_dict(stats.get("curve", [])),
            "groups": groups_attrs,
            "poise_knots": stats.get("poiseKnots", []),
        },
        "resistances": resistances_out,
        "abilities": abilities_out,
        "drops": drops_out,
        "tips": tips,
        "variants": variants_out,
    }
