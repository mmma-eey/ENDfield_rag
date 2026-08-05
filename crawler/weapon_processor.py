"""
武器 API 响应 → 结构化 JSON 的处理逻辑。
stats.curve 为 90 级逐级滑块，按突破阶段归纳为 base + slope 公式。
"""


def process_weapon(raw_json: dict) -> dict:
    """输入 API 原始 JSON，输出结构化武器数据 dict。"""
    article = raw_json["article"]
    revision = raw_json["revision"]
    content = revision["contentJson"]["content"]
    template = content[0]["attrs"]
    template_name = template.get("templateName", "武器档案")

    hero = template["hero"]
    stats = template["stats"]
    skills_raw = template.get("skills", {}).get("skills", [])
    materials_raw = template.get("materials", {})
    gems_raw = template.get("gems", {})
    background_raw = template.get("background", {})

    # --- 属性成长 (stats.curve → 滑块公式) ---
    curve = stats["curve"]
    breaks = stats["breaks"]

    # 按突破阶段分组
    stage_ranges = []
    for b in breaks:
        unlock_lv = b["unlockLv"]
        # 该阶段覆盖的等级范围
        next_stage = next(
            (bb["unlockLv"] for bb in breaks if bb["unlockLv"] > unlock_lv), 91
        )
        stage_ranges.append((unlock_lv, next_stage - 1))

    attr_keys = ["atk"]
    # 有些武器可能有更多属性，动态检测第一条数据
    if curve:
        sample = curve[0]
        for k in sample:
            if k not in ("lv", "lvUpExp", "lvUpGold"):
                attr_keys.append(k)
    attr_keys = list(dict.fromkeys(attr_keys))  # 去重保序

    stages_info = []
    for si, (start_lv, end_lv) in enumerate(stage_ranges):
        stage_curve = [c for c in curve if start_lv <= c["lv"] <= end_lv]
        if not stage_curve:
            continue

        n = len(stage_curve)
        entry = {"stage": si, "level_range": [start_lv, end_lv], "levels": n}
        for key in attr_keys:
            first_val = stage_curve[0][key]
            last_val = stage_curve[-1][key]
            slope = round((last_val - first_val) / (n - 1), 6) if n >= 2 else 0.0
            entry[key] = {
                "base": first_val,
                "slope": slope,
                "values": [c[key] for c in stage_curve],
            }
        stages_info.append(entry)

    # 逐级升级经验与金币（全 90 级）
    level_up_detail = []
    cumulative_exp = 0
    cumulative_gold = 0
    for c in curve:
        cumulative_exp += c.get("lvUpExp", 0)
        cumulative_gold += c.get("lvUpGold", 0)
        level_up_detail.append({
            "lv": c["lv"],
            "atk": c["atk"],
            "lv_up_exp": c.get("lvUpExp", 0),
            "lv_up_gold": c.get("lvUpGold", 0),
            "cumulative_exp": cumulative_exp,
            "cumulative_gold": cumulative_gold,
        })

    total_level_exp = cumulative_exp
    total_level_gold = cumulative_gold

    # --- 技能 ---
    skills_processed = []
    for sk in skills_raw:
        param_rows = []
        if "paramTable" in sk and "rows" in sk["paramTable"]:
            for row in sk["paramTable"]["rows"]:
                param_rows.append({
                    "label": row["label"],
                    "values": row["values"],
                })

        levels_data = []
        for lv_data in sk.get("levels", []):
            levels_data.append({
                "level": lv_data["level"],
                "desc": lv_data.get("desc", ""),
                "values": lv_data.get("values", {}),
            })

        skills_processed.append({
            "name": sk["name"],
            "skill_id": sk.get("skillId", ""),
            "type_label": sk.get("typeLabel", ""),
            "description": sk.get("description", ""),
            "zero_potential_max_level": sk.get("zeroPotentialMaxLevel", 0),
            "levels": levels_data,
            "param_table": param_rows,
        })

    # --- 突破材料 ---
    ascension_materials = []
    for bm in materials_raw.get("breaks", []):
        items = []
        for it in bm.get("items", []):
            items.append({
                "id": it["id"],
                "name": it["name"],
                "qty": it["qty"],
                "tier": it["tier"],
            })
        ascension_materials.append({
            "stage": bm["stage"],
            "unlock_lv": bm["unlockLv"],
            "gold": bm["gold"],
            "items": items,
        })

    gold_item = materials_raw.get("goldItem", {})
    total_break_gold = materials_raw.get("totalGold", 0)

    # --- 基质 (gems) ---
    gems_processed = []
    for preset in gems_raw.get("presets", []):
        terms_list = []
        for t in preset.get("terms", []):
            terms_list.append({
                "label": t["label"],
                "level": t["level"],
                "type_label": t.get("typeLabel", ""),
            })

        domains_list = []
        for d in preset.get("domains", []):
            domains_list.append({
                "domain_id": d["domainId"],
                "domain_name": d["domainName"],
            })

        drop_points = []
        for dp in preset.get("dropPoints", []):
            drop_points.append({
                "name": dp["name"],
                "domain_name": dp.get("domainName", ""),
                "world_level": dp.get("worldLevel", 0),
                "recommend_lv": dp.get("recommendLv", 0),
            })

        gems_processed.append({
            "gem_id": preset.get("gemId", ""),
            "display_name": preset.get("displayName", ""),
            "tier_name": preset.get("tierName", ""),
            "rarity": preset["rarity"],
            "terms": terms_list,
            "domains": domains_list,
            "drop_points": drop_points,
        })

    # --- 组装 ---
    return {
        "meta": {
            "source": "fz.wiki",
            "template": template_name,
            "article_id": article["id"],
            "updated_at": article["updatedAt"],
        },
        "basic": {
            "name": hero["name"],
            "name_en": hero.get("nameEn", ""),
            "rarity": hero["rarity"],
            "weapon_type": hero["weaponType"],
            "max_lv": hero.get("maxLv", 90),
            "description": hero.get("description", ""),
            "flavor": hero.get("flavor", ""),
            "categories": article.get("categories", []),
        },
        "stats": {
            "formula": "value(level) = round(base + slope * (level - stage_start_level))",
            "stages": stages_info,
            "breaks": [{
                "stage": b["stage"],
                "unlock_lv": b["unlockLv"],
                "gold": b["gold"],
                "skill_bounds": b.get("skillBounds", []),
            } for b in breaks],
            "level_up_detail": level_up_detail,
            "total_level_exp": total_level_exp,
            "total_level_gold": total_level_gold,
        },
        "skills": skills_processed,
        "materials": {
            "ascension": ascension_materials,
            "gold_item": {
                "id": gold_item.get("id", ""),
                "name": gold_item.get("name", ""),
                "tier": gold_item.get("tier", 0),
            },
            "total_break_gold": total_break_gold,
        },
        "gems": gems_processed,
        "background": {
            "body": background_raw.get("body", ""),
        },
    }
