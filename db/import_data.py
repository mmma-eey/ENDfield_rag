"""将 data_main/operator_data/*.json 批量导入 PostgreSQL"""
import json
import os
import sys

# 切换到项目根目录确保 import 路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal, init_db
from db.models import (KnowledgeChunk, Operator, OperatorAttribute, OperatorLogistic,
                       OperatorMaterialAscension, OperatorMaterialLevelUp,
                       OperatorMaterialSkill, OperatorPotential, OperatorSkill,
                       OperatorTalent, OperatorWeapon)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data_main", "operator_data")


def import_operator(session, data: dict):
    article_id = data["meta"]["article_id"]
    basic = data["basic"]

    # ---- 干员主表 ----
    op = Operator(
        article_id=article_id,
        name=basic["name"],
        name_en=basic.get("name_en"),
        rarity=basic["rarity"],
        profession=basic["profession"],
        sub_profession=basic.get("sub_profession"),
        weapon_type=basic["weapon_type"],
        element=basic["element"],
        faction=basic["faction"],
        tags=basic.get("tags", []),
        categories=basic.get("categories", []),
        description=basic.get("description"),
        bio=data.get("bio"),
        details=data.get("details"),
        updated_at=data["meta"]["updated_at"],
    )
    session.add(op)

    # ---- 属性 ----
    attr_data = data.get("attributes", {})
    stages = attr_data.get("stages", [])
    stage_map = {s["stage"]: s["level_range"][0] for s in stages}  # stage→起始等级
    for key, attr in attr_data.get("data", {}).items():
        for st in attr["stages"]:
            session.add(OperatorAttribute(
                operator_id=article_id,
                attr_key=key,
                label=attr["label"],
                advanced=attr.get("advanced", False),
                stage=st["stage"],
                base_val=st["base"],
                slope=st["slope"],
                values=st["values"],
            ))

    # ---- 技能 ----
    for sk in data.get("skills", []):
        session.add(OperatorSkill(
            operator_id=article_id,
            name=sk["name"],
            skill_type=sk.get("type"),
            group_id=sk.get("group_id"),
            description=sk.get("description"),
            param_table=sk.get("param_table"),
        ))

    # ---- 天赋 ----
    for t in data.get("talents", []):
        session.add(OperatorTalent(
            operator_id=article_id,
            name=t["name"],
            level=t["level"],
            description=t["desc"],
            unlock_stage=t.get("unlock_stage"),
        ))

    # ---- 后勤 ----
    for l in data.get("logistics", []):
        session.add(OperatorLogistic(
            operator_id=article_id,
            name=l["name"],
            description=l["desc"],
            room=l.get("room"),
            unlock_condition=l.get("unlock"),
        ))

    # ---- 潜能 ----
    for p in data.get("potentials", []):
        session.add(OperatorPotential(
            operator_id=article_id,
            name=p["name"],
            level=p["level"],
            description=p["desc"],
        ))

    # ---- 武器 ----
    for w in data.get("weapons", []):
        session.add(OperatorWeapon(
            operator_id=article_id,
            name=w["name"],
            rarity=w.get("rarity"),
            weapon_type=w.get("type"),
            group_name=w.get("group"),
        ))

    # ---- 培养材料：技能 ----
    for sm in data.get("materials", {}).get("skill_up", []):
        session.add(OperatorMaterialSkill(
            operator_id=article_id,
            skill_type=sm["skill_type"],
            max_level=sm.get("max_level"),
            gold=sm.get("gold"),
            items=sm.get("items"),
        ))

    # ---- 培养材料：晋升 ----
    for am in data.get("materials", {}).get("ascension", []):
        session.add(OperatorMaterialAscension(
            operator_id=article_id,
            title=am["title"],
            subtitle=am.get("subtitle"),
            credits=am.get("credits"),
            items=am.get("items"),
        ))

    # ---- 培养材料：等级总计 ----
    lu = data.get("materials", {}).get("level_up_total", {})
    if lu:
        session.add(OperatorMaterialLevelUp(
            operator_id=article_id,
            exp=lu.get("exp", 0),
            gold=lu.get("gold", 0),
        ))

    # ---- 知识切片（向量库文本，embedding 后续 Phase 填充）----
    chunks = []

    # bio
    if data.get("bio"):
        chunks.append(("bio", data["bio"]))

    # 技能描述
    for sk in data.get("skills", []):
        desc = sk.get("description", "")
        if desc:
            chunks.append(("skill", f"{sk['name']}（{sk.get('type', '')}）：{desc}"))

    # 天赋描述
    for t in data.get("talents", []):
        desc = t.get("desc", "")
        if desc:
            chunks.append(("talent", f"{t['name']}（Lv{t.get('level', '')}）：{desc}"))

    # 后勤
    for l in data.get("logistics", []):
        desc = l.get("desc", "")
        if desc:
            chunks.append(("logistic", f"{l['name']}：{desc}"))

    # 档案
    for a in data.get("archive_texts", []):
        body = a.get("body", "")
        if body:
            chunks.append(("archive", f"{a['title']}：{body}"))

    # 语音
    for v in data.get("voice_lines", []):
        text = v.get("text", "")
        if text:
            chunks.append(("voice", f"{v['scene']}：{text}"))

    # 专长
    for s in data.get("specialties", []):
        desc = s.get("desc", "")
        if desc:
            chunks.append(("specialty", f"{s['name']}：{desc}"))

    for ctype, ctext in chunks:
        session.add(KnowledgeChunk(
            operator_id=article_id,
            chunk_type=ctype,
            content=ctext,
            embedding=None,  # 后续 embed.py 阶段填充
        ))

    return op.name, len(chunks)


def main():
    init_db()
    session = SessionLocal()

    json_files = sorted(
        f for f in os.listdir(DATA_DIR) if f.endswith(".json")
    )

    total = len(json_files)
    success = 0
    total_chunks = 0

    for i, filename in enumerate(json_files, 1):
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        try:
            name, chunk_count = import_operator(session, data)
            session.commit()
            success += 1
            total_chunks += chunk_count
            print(f"[{i:02d}/{total}] {name} OK (chunks: {chunk_count})")
        except Exception as e:
            session.rollback()
            print(f"[{i:02d}/{total}] {filename} ERROR: {e}")

    session.close()
    print(f"\n导入完成: {success}/{total} 干员, 共 {total_chunks} 条知识切片")


if __name__ == "__main__":
    main()
