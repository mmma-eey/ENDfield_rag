"""
干员 API 响应 → 结构化 JSON 的处理逻辑。
属性滑动栏：5 等阶 base + slope 公式 + 逐级精确值。
"""

def parse_value(v):
    """'56.2' → 56.2, '5.0%' → 5.0, '3.0m' → 3.0"""
    v = str(v).replace("%", "").replace("m", "")
    return float(v)


def analyze_attribute(cells):
    """
    对 5 个等阶的 cells 数组，计算每等阶的 base + slope + values。
    cells: [[stage0 values], [stage1 values], ...]
    """
    stages_info = []
    for si, stage_cells in enumerate(cells):
        nums = [parse_value(v) for v in stage_cells]
        n = len(nums)
        base = nums[0]
        if n >= 2:
            slope = (nums[-1] - nums[0]) / (n - 1)
        else:
            slope = 0.0
        stages_info.append({
            "stage": si,
            "levels": n,
            "base": base,
            "slope": round(slope, 6),
            "values": nums
        })
    return stages_info


def process_operator(raw_json: dict) -> dict:
    """输入 API 原始 JSON，输出结构化干员数据 dict。"""
    article = raw_json["article"]
    revision = raw_json["revision"]
    content = revision["contentJson"]["content"]
    template = content[0]["attrs"]
    template_name = template["templateName"]
    hero = template["hero"]
    attributes_raw = template.get("attributes", {})
    potentials_raw = template.get("potentials", {})

    # --- 属性 ---
    breaks = attributes_raw.get("breaks", [])
    break_info = [{
        "stage": b["breakStage"],
        "level_range": [b["levels"][0], b["levels"][-1]]
    } for b in breaks]

    attributes_processed = {}
    for r in attributes_raw.get("rows", []):
        attributes_processed[r["key"]] = {
            "label": r.get("label", r["key"]),
            "advanced": r.get("advanced", False),
            "stages": analyze_attribute(r["cells"])
        }

    # --- 技能 ---
    skills_processed = []
    for sk in template["skills"]["skills"]:
        param_rows = []
        if "paramTable" in sk and "rows" in sk["paramTable"]:
            for row in sk["paramTable"]["rows"]:
                param_rows.append({"label": row["label"], "values": row["values"]})
        skills_processed.append({
            "name": sk["name"],
            "type": sk.get("typeLabel", ""),
            "group_id": sk.get("groupId", ""),
            "description": sk.get("description", ""),
            "param_table": param_rows
        })

    # --- 档案 ---
    archive_data = template["archive"]
    archive_list = [
        {"title": a["title"], "body": a["body"], "unlock": a.get("unlockHint", "")}
        for a in archive_data.get("archive", [])
    ]
    voice_list = [
        {"scene": v["scene"], "text": v["text"], "unlock": v.get("unlockHint", "")}
        for v in archive_data.get("voice", [])
    ]
    specialties_list = [
        {"name": s["name"], "label": s.get("label", ""), "desc": s.get("desc", "")}
        for s in archive_data.get("specialties", [])
    ]

    # --- 天赋 ---
    talents_data = template["talents"]
    talent_list = [
        {"name": t["name"], "level": t["level"], "desc": t["desc"],
         "unlock_stage": t.get("unlockStage", 0)}
        for t in talents_data.get("talents", [])
    ]
    logistics_list = [
        {"name": l["name"], "desc": l["desc"], "room": l.get("room", ""),
         "unlock": l.get("unlock", "")}
        for l in talents_data.get("logistics", [])
    ]

    # --- 潜能 ---
    potential_list = [
        {"name": p["name"], "level": p["level"], "desc": p["desc"]}
        for p in potentials_raw.get("potentials", [])
    ]

    # --- 武器 ---
    weapon_list = []
    for g in template["weapons"].get("group1", []):
        weapon_list.append({
            "name": g["name"], "rarity": g["rarity"],
            "type": g.get("weaponType", ""), "group": "技能适配"
        })
    for g in template["weapons"].get("group2", []):
        weapon_list.append({
            "name": g["name"], "rarity": g["rarity"],
            "type": g.get("weaponType", ""), "group": "属性适配"
        })

    # --- 培养材料 ---
    materials_data = template["materials"]
    skill_materials = []
    for sm in materials_data.get("skillUp", []):
        items = [{"name": i["name"].strip(), "qty": i["qty"], "tier": i["tier"]}
                 for i in sm.get("items", [])]
        skill_materials.append({
            "skill_type": sm.get("typeLabel", ""),
            "max_level": sm.get("maxLevel", 0),
            "gold": sm.get("totalGold", 0),
            "items": items
        })

    ascension_materials = []
    for am in materials_data.get("ascension", []):
        items = [{"name": i["name"].strip(), "qty": i["qty"], "tier": i["tier"]}
                 for i in am.get("items", [])]
        ascension_materials.append({
            "title": am["title"],
            "subtitle": am.get("subtitle", ""),
            "credits": am.get("credits", 0),
            "items": items
        })

    level_up_total = materials_data.get("levelUpTotal", {})

    # --- 组装 ---
    return {
        "meta": {
            "source": "fz.wiki",
            "template": template_name,
            "article_id": article["id"],
            "updated_at": article["updatedAt"]
        },
        "basic": {
            "name": hero["name"],
            "name_en": hero.get("nameEn", ""),
            "rarity": hero["rarity"],
            "profession": hero["profession"],
            "sub_profession": hero.get("subProfession", ""),
            "weapon_type": hero["weaponType"],
            "element": hero["element"],
            "faction": hero["faction"],
            "tags": hero.get("tags", []),
            "categories": article.get("categories", []),
            "description": article.get("description", "")
        },
        "details": {
            "所属": (hero.get("meta", [{}])[0].get("value", "") if len(hero.get("meta", [])) > 0 else ""),
            "主属性": (hero.get("meta", [{}])[1].get("value", "").split("/")[0].strip() if len(hero.get("meta", [])) > 1 else ""),
            "副属性": (hero.get("meta", [{}])[1].get("value", "").split("/")[1].strip() if len(hero.get("meta", [])) > 1 else ""),
            "CV_中": (hero.get("meta", [{}])[2].get("value", "") if len(hero.get("meta", [])) > 2 else ""),
            "CV_日": (hero.get("meta", [{}])[3].get("value", "") if len(hero.get("meta", [])) > 3 else ""),
            "CV_英": (hero.get("meta", [{}])[4].get("value", "") if len(hero.get("meta", [])) > 4 else ""),
            "CV_韩": (hero.get("meta", [{}])[5].get("value", "") if len(hero.get("meta", [])) > 5 else ""),
        },
        "bio": hero.get("bio", ""),
        "attributes": {
            "stages": break_info,
            "formula": "value(level) = round(base + slope * (level - stage_start_level))",
            "data": attributes_processed
        },
        "skills": skills_processed,
        "talents": talent_list,
        "logistics": logistics_list,
        "potentials": potential_list,
        "weapons": weapon_list,
        "archive_texts": archive_list,
        "voice_lines": voice_list,
        "specialties": specialties_list,
        "materials": {
            "skill_up": skill_materials,
            "ascension": ascension_materials,
            "level_up_total": {
                "exp": level_up_total.get("exp", 0),
                "gold": level_up_total.get("gold", 0)
            }
        }
    }
