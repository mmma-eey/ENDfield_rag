"""
装备数据批量入库：equipments_data/*.json → PostgreSQL
同时完成 knowledge_chunks 表迁移（支持装备）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal, engine, init_db
from db.models import Equipment, EquipmentStat, KnowledgeChunk
from sqlalchemy import text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EQUIPMENTS_DIR = os.path.join(BASE_DIR, "data_main", "equipments_data")

# 获取方式中文映射（fz.wiki unlockType）
UNLOCK_LABELS = {
    "EquipFormulaChest": "装备图纸箱",
    "AdventureLevel": "冒险等级解锁",
    "DomainShop": "域商店",
    "StarShop": "星商店",
    "DefaultUnlock": "默认解锁",
}

# 附加属性标签顺序（供画像切片拼接）
ATTR_ORDER = ['攻击力', '生命值', '暴击率', '源石技艺强度', '治疗效率加成', '物理伤害加成',
              '终结技充能效率', '对失衡目标伤害加成', '法术伤害加成', '寒冷和电磁伤害加成',
              '全伤害减免', '灼热和自然伤害加成', '普通攻击伤害加成', '战技伤害加成',
              '连携技伤害加成', '终结技伤害加成', '所有技能伤害加成']


def migrate_knowledge_chunks():
    """使 knowledge_chunks 支持装备：新增 equipment_id 列"""
    with engine.connect() as conn:
        cols = [row[0] for row in conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name='knowledge_chunks'")
        ).fetchall()]

        if "equipment_id" not in cols:
            print("迁移 knowledge_chunks: 添加 equipment_id 列 ...")
            conn.execute(text(
                "ALTER TABLE knowledge_chunks ADD COLUMN equipment_id VARCHAR"
            ))
            conn.execute(text(
                "ALTER TABLE knowledge_chunks "
                "ADD CONSTRAINT fk_knowledge_chunks_equipment "
                "FOREIGN KEY (equipment_id) REFERENCES equipments(article_id) ON DELETE CASCADE"
            ))
            conn.commit()
            print("迁移完成")
        else:
            print("knowledge_chunks 已支持装备，跳过迁移")


def build_equipment_chunks(data: dict) -> list[tuple[str, str]]:
    """生成装备知识切片（内容前缀装备名作为标签，保证 BM25/向量可被装备名锚定）"""
    basic = data["basic"]
    name = basic["name"]
    chunks = []

    # 画像：星级/部位/装备组 + 附加属性标签
    stat_labels = [row["label"] for row in data.get("stats", {}).get("rows", [])]
    profile_parts = [f"装备{name}，{basic['rarity']}星{basic['slot_type']}，{basic['group_name']}"]
    if stat_labels:
        profile_parts.append("附加属性：" + "、".join(stat_labels))
    chunks.append(("equipment_profile", "，".join(profile_parts) + "。"))

    # 描述
    if basic.get("description"):
        chunks.append(("equipment_description", f"{name}的装备描述：{basic['description']}"))

    # 风味文本
    if basic.get("flavor"):
        chunks.append(("equipment_flavor", f"{name}的风味文本：{basic['flavor']}"))

    # 属性行（含强化 0~3 级数值；百分比属性标注）
    for row in data.get("stats", {}).get("rows", []):
        label = row.get("label", "")
        if not label:
            continue
        if row.get("is_percent"):
            vals = " / ".join(f"{v:.3f}（百分比）" for v in row.get("values", []))
        else:
            vals = " / ".join(str(v) for v in row.get("values", []))
        chunks.append(("equipment_stat", f"{name}的装备属性-{label}（强化0~3级）：{vals}"))

    # 套装
    suit = data.get("suit", {})
    pieces = suit.get("pieces", [])
    if pieces:
        piece_names = "、".join(p["name"] for p in pieces)
        chunks.append(("equipment_suit",
                       f"{name}所属{basic['group_name']}（{suit.get('piece_count', len(pieces))}件套），套装成员：{piece_names}"))

    # 获取方式
    unlock_type = data.get("materials", {}).get("unlock_type", "")
    if unlock_type:
        label = UNLOCK_LABELS.get(unlock_type, unlock_type)
        chunks.append(("equipment_unlock", f"{name}的获取方式：{label}"))

    return chunks


def import_equipment(session, data: dict):
    """导入单件装备 + 属性 + 知识切片"""
    article_id = data["meta"]["article_id"]
    basic = data["basic"]
    suit = data.get("suit", {})
    materials = data.get("materials", {})

    eq = Equipment(
        article_id=article_id,
        name=basic["name"],
        rarity=basic["rarity"],
        part_type=basic.get("part_type"),
        slot_type=basic["slot_type"],
        group_name=basic.get("group_name"),
        suit_name=basic.get("suit_name"),
        description=basic.get("description"),
        flavor=basic.get("flavor"),
        icon_url=basic.get("icon_url"),
        categories=basic.get("categories", []),
        unlock_type=materials.get("unlock_type"),
        unlock_key=materials.get("unlock_key"),
        suit_piece_count=suit.get("piece_count"),
        suit_self_equip_id=suit.get("self_equip_id"),
        suit_bonus=suit.get("bonus"),
        suit_pieces=suit.get("pieces"),
        updated_at=data["meta"]["updated_at"],
    )
    session.add(eq)

    # 属性
    for row in data.get("stats", {}).get("rows", []):
        session.add(EquipmentStat(
            equipment_id=article_id,
            label=row.get("label", ""),
            attr_type=row.get("attr_type"),
            is_base=row.get("is_base", False),
            is_percent=row.get("is_percent", False),
            enhances=row.get("enhances", False),
            values=row.get("values", []),
            modifier_type=row.get("modifier_type"),
            composite_attr=row.get("composite_attr"),
        ))

    # 知识切片
    chunks = build_equipment_chunks(data)
    for ctype, ctext in chunks:
        session.add(KnowledgeChunk(
            equipment_id=article_id,
            chunk_type=ctype,
            content=ctext,
            embedding=None,
        ))

    return eq.name, len(chunks)


def main():
    print("创建装备表 ...")
    init_db()

    print("=" * 50)
    migrate_knowledge_chunks()

    session = SessionLocal()
    try:
        print("\n导入装备数据 ...\n")
        json_files = sorted(
            f for f in os.listdir(EQUIPMENTS_DIR)
            if f.endswith(".json") and f not in ("equipments.json", "equipments_catalog.json")
        )

        total = len(json_files)
        success = 0
        total_chunks = 0

        for i, filename in enumerate(json_files, 1):
            filepath = os.path.join(EQUIPMENTS_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            existing = session.query(Equipment).filter_by(
                article_id=data["meta"]["article_id"]
            ).first()
            if existing:
                print(f"[{i:02d}/{total}] {data['basic']['name']} - 已存在，跳过")
                success += 1
                continue

            try:
                name, chunk_count = import_equipment(session, data)
                session.commit()
                success += 1
                total_chunks += chunk_count
                print(f"[{i:02d}/{total}] {name} OK (chunks: {chunk_count})")
            except Exception as e:
                session.rollback()
                print(f"[{i:02d}/{total}] {filename} ERROR: {e}")

        print(f"\n导入完成: {success}/{total} 装备, 共 {total_chunks} 条知识切片")
    finally:
        session.close()


if __name__ == "__main__":
    main()
