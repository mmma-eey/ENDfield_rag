"""
武器数据批量入库：weapons_data/*.json → PostgreSQL
同时完成 knowledge_chunks 表迁移（支持武器）和干员-武器映射
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal, init_db, engine
from db.models import (KnowledgeChunk, OperatorWeapon,
                       Weapon, WeaponStage, WeaponSkill,
                       WeaponMaterial, WeaponGem)
from sqlalchemy import text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEAPONS_DIR = os.path.join(BASE_DIR, "data_main", "weapons_data")
OPERATOR_DIR = os.path.join(BASE_DIR, "data_main", "operator_data")


def migrate_knowledge_chunks():
    """使 knowledge_chunks 支持武器：operator_id 改为可空 + 新增 weapon_id 列"""
    with engine.connect() as conn:
        # 检查 weapon_id 列是否存在
        cols = [row[0] for row in conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name='knowledge_chunks'")
        ).fetchall()]

        if "weapon_id" not in cols:
            print("迁移 knowledge_chunks: 添加 weapon_id 列, operator_id 改为可空 ...")
            conn.execute(text(
                "ALTER TABLE knowledge_chunks ADD COLUMN weapon_id VARCHAR"
            ))
            conn.execute(text(
                "ALTER TABLE knowledge_chunks "
                "ALTER COLUMN operator_id DROP NOT NULL"
            ))
            conn.execute(text(
                "ALTER TABLE knowledge_chunks "
                "ADD CONSTRAINT fk_knowledge_chunks_weapon "
                "FOREIGN KEY (weapon_id) REFERENCES weapons(article_id) ON DELETE CASCADE"
            ))
            conn.commit()
            print("迁移完成")
        else:
            print("knowledge_chunks 已支持武器，跳过迁移")


def import_weapon(session, data: dict):
    """导入单把武器 + 知识切片"""
    article_id = data["meta"]["article_id"]
    basic = data["basic"]

    # ---- 武器主表 ----
    wp = Weapon(
        article_id=article_id,
        name=basic["name"],
        name_en=basic.get("name_en"),
        rarity=basic["rarity"],
        weapon_type=basic["weapon_type"],
        max_lv=basic.get("max_lv", 90),
        description=basic.get("description"),
        flavor=basic.get("flavor"),
        categories=basic.get("categories", []),
        total_level_exp=data["stats"].get("total_level_exp", 0),
        total_level_gold=data["stats"].get("total_level_gold", 0),
        total_break_gold=data.get("materials", {}).get("total_break_gold", 0),
        background=data.get("background", {}).get("body", ""),
        updated_at=data["meta"]["updated_at"],
    )
    session.add(wp)

    # ---- 属性成长阶段 ----
    for st in data["stats"].get("stages", []):
        session.add(WeaponStage(
            weapon_id=article_id,
            stage=st["stage"],
            level_range=st["level_range"],
            levels=st["levels"],
            base_atk=st["atk"]["base"],
            slope_atk=st["atk"]["slope"],
            atk_values=st["atk"]["values"],
        ))

    # ---- 技能 ----
    for sk in data.get("skills", []):
        session.add(WeaponSkill(
            weapon_id=article_id,
            name=sk["name"],
            skill_id=sk.get("skill_id"),
            type_label=sk.get("type_label"),
            description=sk.get("description"),
            zero_potential_max_level=sk.get("zero_potential_max_level"),
            levels_data=sk.get("levels"),
            param_table=sk.get("param_table"),
        ))

    # ---- 突破材料 ----
    for am in data.get("materials", {}).get("ascension", []):
        session.add(WeaponMaterial(
            weapon_id=article_id,
            stage=am["stage"],
            unlock_lv=am["unlock_lv"],
            gold=am["gold"],
            items=am["items"],
        ))

    # ---- 基质 ----
    for g in data.get("gems", []):
        session.add(WeaponGem(
            weapon_id=article_id,
            gem_id=g.get("gem_id"),
            display_name=g.get("display_name"),
            tier_name=g.get("tier_name"),
            rarity=g.get("rarity"),
            terms=g.get("terms"),
            domains=g.get("domains"),
            drop_points=g.get("drop_points"),
        ))

    # ---- 知识切片（向量库文本）----
    chunks = []

    # 武器 flavor 描述
    if basic.get("flavor"):
        chunks.append(("weapon_flavor", f"{basic['name']}：{basic['flavor']}"))

    # 技能描述
    for sk in data.get("skills", []):
        desc = sk.get("description", "")
        if desc:
            chunks.append(("weapon_skill", f"{basic['name']} - {sk['name']}：{desc}"))

    # 武器故事
    bg_body = data.get("background", {}).get("body", "")
    if bg_body:
        chunks.append(("weapon_background", f"{basic['name']}武器故事：{bg_body}"))

    for ctype, ctext in chunks:
        session.add(KnowledgeChunk(
            weapon_id=article_id,
            operator_id=None,
            chunk_type=ctype,
            content=ctext,
            embedding=None,
        ))

    return wp.name, len(chunks)


def link_operator_weapons(session):
    """将 operator_weapons 表中的武器名匹配到 weapons 表的 article_id"""
    # 建立 武器名 → article_id 映射
    all_weapons = session.query(Weapon).all()
    name_to_id = {w.name: w.article_id for w in all_weapons}

    # 更新所有 operator_weapons 记录
    rows = session.query(OperatorWeapon).all()
    linked = 0
    unmatched = []

    for row in rows:
        if row.weapon_article_id is not None:
            linked += 1
            continue

        wid = name_to_id.get(row.name)
        if wid:
            row.weapon_article_id = wid
            linked += 1
        else:
            unmatched.append(row.name)

    session.commit()
    return linked, unmatched


def migrate_operator_weapons():
    """给 operator_weapons 表添加 weapon_article_id 外键"""
    with engine.connect() as conn:
        cols = [row[0] for row in conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name='operator_weapons'")
        ).fetchall()]

        if "weapon_article_id" not in cols:
            print("迁移 operator_weapons: 添加 weapon_article_id 列 ...")
            conn.execute(text(
                "ALTER TABLE operator_weapons ADD COLUMN weapon_article_id VARCHAR"
            ))
            conn.execute(text(
                "ALTER TABLE operator_weapons "
                "ADD CONSTRAINT fk_operator_weapons_weapon "
                "FOREIGN KEY (weapon_article_id) REFERENCES weapons(article_id) ON DELETE SET NULL"
            ))
            conn.commit()
            print("迁移完成")
        else:
            print("operator_weapons 已迁移，跳过")


def generate_weapon_mapping_chunks(session):
    """从 operator_weapons 表生成推荐映射切片（双向：干员侧 + 武器侧）"""
    from collections import defaultdict
    from db.models import Operator

    # ---- 干员侧：干员 → 武器 ----
    # 查询所有已关联的记录（含干员名和武器名）
    rows = (
        session.query(OperatorWeapon, Operator.name, Weapon.name, Weapon.rarity)
        .join(Operator, OperatorWeapon.operator_id == Operator.article_id)
        .join(Weapon, OperatorWeapon.weapon_article_id == Weapon.article_id)
        .all()
    )

    # 按干员分组
    op_groups = defaultdict(lambda: defaultdict(list))
    for ow, op_name, wp_name, wp_rarity in rows:
        op_groups[op_name][ow.group_name].append((wp_name, wp_rarity))

    chunks_added = 0
    for op_name, groups in op_groups.items():
        operator = session.query(Operator).filter_by(name=op_name).first()
        if not operator:
            continue

        for group_name, weapons in groups.items():
            weapon_list = "、".join(f"{w}（{r}星）" for w, r in weapons)
            text = f"干员{op_name}的{group_name}武器推荐：{weapon_list}"
            session.add(KnowledgeChunk(
                operator_id=operator.article_id,
                weapon_id=None,
                chunk_type="weapon_recommend",
                content=text,
                embedding=None,
            ))
            chunks_added += 1

    # ---- 武器侧：武器 → 干员 ----
    wp_groups = defaultdict(lambda: defaultdict(list))
    for ow, op_name, wp_name, wp_rarity in rows:
        wp_groups[wp_name][ow.group_name].append(op_name)

    for wp_name, groups in wp_groups.items():
        weapon = session.query(Weapon).filter_by(name=wp_name).first()
        if not weapon:
            continue

        for group_name, operators in groups.items():
            op_list = "、".join(operators)
            text = f"武器{wp_name}可适配干员（{group_name}）：{op_list}"
            session.add(KnowledgeChunk(
                operator_id=None,
                weapon_id=weapon.article_id,
                chunk_type="weapon_recommend",
                content=text,
                embedding=None,
            ))
            chunks_added += 1

    session.commit()
    return chunks_added


def main():
    # 1. 先建新表（weapons 系列），否则 knowledge_chunks 外键迁移会失败
    print("创建武器表 ...")
    init_db()

    # 2. 迁移 knowledge_chunks（添加 weapon_id 外键 + operator_id 可空）
    print("=" * 50)
    migrate_knowledge_chunks()

    # 3. 迁移 operator_weapons（添加 weapon_article_id 外键）
    print("=" * 50)
    migrate_operator_weapons()

    session = SessionLocal()

    try:
        # 3. 导入武器
        print("\n" + "=" * 50)
        print("导入武器数据 ...\n")

        json_files = sorted(
            f for f in os.listdir(WEAPONS_DIR)
            if f.endswith(".json") and f != "weapons.json"
        )

        total = len(json_files)
        success = 0
        total_chunks = 0

        for i, filename in enumerate(json_files, 1):
            filepath = os.path.join(WEAPONS_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 跳过已存在的武器
            existing = session.query(Weapon).filter_by(
                article_id=data["meta"]["article_id"]
            ).first()
            if existing:
                print(f"[{i:02d}/{total}] {data['basic']['name']} - 已存在，跳过")
                success += 1
                continue

            try:
                name, chunk_count = import_weapon(session, data)
                session.commit()
                success += 1
                total_chunks += chunk_count
                print(f"[{i:02d}/{total}] {name} OK (chunks: {chunk_count})")
            except Exception as e:
                session.rollback()
                print(f"[{i:02d}/{total}] {filename} ERROR: {e}")

        # 4. 干员-武器映射
        print("\n" + "=" * 50)
        print("建立干员-武器映射 ...")
        linked, unmatched = link_operator_weapons(session)
        print(f"关联成功: {linked} 条")
        if unmatched:
            print(f"未匹配武器名: {list(set(unmatched))}")

        # 5. 生成武器推荐知识切片
        print("\n" + "=" * 50)
        print("生成武器推荐映射切片 ...")
        map_count = generate_weapon_mapping_chunks(session)
        print(f"新增映射切片: {map_count} 条")

        print(f"\n导入完成: {success}/{total} 武器, 共 {total_chunks} 条知识切片")

    finally:
        session.close()


if __name__ == "__main__":
    main()
