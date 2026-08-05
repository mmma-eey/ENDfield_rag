"""
装备 API 响应 → 结构化 JSON 的处理逻辑。
模板：装备档案（attrs: hero / suit / stats / materials）
"""


def process_equipment(raw_json: dict) -> dict:
    """输入 API 原始 JSON，输出结构化装备数据 dict。"""
    article = raw_json["article"]
    revision = raw_json["revision"]
    content = revision["contentJson"]["content"]

    # 第一个 wikiTemplateInstance 即装备档案
    template = None
    for blk in content:
        attrs = blk.get("attrs") or {}
        if attrs.get("templateName"):
            template = attrs
            break
    if template is None:
        raise RuntimeError("装备页未找到模板组件")

    hero = template.get("hero", {})
    suit = template.get("suit", {})
    stats = template.get("stats", {})
    materials = template.get("materials", {})

    # --- 基础信息 ---
    basic = {
        "name": hero.get("name", ""),
        "rarity": hero.get("rarity", 0),
        "part_type": hero.get("partType", ""),   # Body / Hand / EDC
        "slot_type": hero.get("slotType", ""),   # 护甲 / 护手 / 配件
        "group_name": hero.get("groupName", ""),
        "suit_name": hero.get("suitName", ""),
        "description": hero.get("description", ""),
        "flavor": hero.get("flavor", ""),
        "icon_url": hero.get("iconUrl", ""),
        "categories": article.get("categories", []),
    }

    # --- 套装信息 ---
    pieces = []
    for p in suit.get("pieces", []):
        pieces.append({
            "name": p.get("name", ""),
            "rarity": p.get("rarity", 0),
            "part_type": p.get("partType", ""),
            "slot_type": p.get("slotType", ""),
            "equip_id": p.get("equipId", ""),
        })

    suit_info = {
        "group_name": suit.get("groupName", ""),
        "piece_count": suit.get("pieceCount", 0),
        "self_equip_id": suit.get("selfEquipId", ""),
        "bonus": suit.get("bonus"),
        "pieces": pieces,
    }

    # --- 属性（含强化等级 0~3 的数值） ---
    stat_rows = []
    for row in stats.get("rows", []):
        stat_rows.append({
            "label": row.get("label", ""),
            "attr_type": row.get("attrType", ""),
            "is_base": row.get("isBase", False),
            "is_percent": row.get("isPercent", False),
            "enhances": row.get("enhances", False),
            "values": row.get("values", []),  # 长度 = len(enhance_levels)，对应 0~3 强化
            "modifier_type": row.get("modifierType", ""),
            "composite_attr": row.get("compositeAttr", ""),
        })

    stats_info = {
        "enhance_levels": stats.get("enhanceLevels", [0, 1, 2, 3]),
        "rows": stat_rows,
    }

    # --- 获取方式 ---
    materials_info = {
        "unlock_type": materials.get("unlockType", ""),
        "unlock_key": materials.get("unlockKey", ""),
        "gold": materials.get("gold", 0),
        "items": materials.get("items", []),
    }

    return {
        "meta": {
            "source": "fz.wiki",
            "template": template.get("templateName", "装备档案"),
            "article_id": article["id"],
            "updated_at": article["updatedAt"],
        },
        "basic": basic,
        "suit": suit_info,
        "stats": stats_info,
        "materials": materials_info,
    }
