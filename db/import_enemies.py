"""
敌人数据批量入库：enemies_data/*.json → PostgreSQL
同时完成 knowledge_chunks 表迁移（支持敌人）并生成敌人知识切片。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal, engine, init_db
from db.models import (Enemy, EnemyAbility, EnemyAttribute, EnemyDrop,
                       EnemyResistance, EnemyVariant, KnowledgeChunk)
from sqlalchemy import text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENEMIES_DIR = os.path.join(BASE_DIR, "data_main", "enemies_data")


def migrate_knowledge_chunks():
    """使 knowledge_chunks 支持敌人：新增 enemy_id 列 + 外键"""
    with engine.connect() as conn:
        cols = [row[0] for row in conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name='knowledge_chunks'")
        ).fetchall()]

        if "enemy_id" not in cols:
            print("迁移 knowledge_chunks: 添加 enemy_id 列 + 外键 ...")
            conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN enemy_id VARCHAR"))
            conn.execute(text(
                "ALTER TABLE knowledge_chunks "
                "ADD CONSTRAINT fk_knowledge_chunks_enemy "
                "FOREIGN KEY (enemy_id) REFERENCES enemies(article_id) ON DELETE CASCADE"
            ))
            conn.commit()
            print("迁移完成")
        else:
            print("knowledge_chunks 已支持敌人，跳过迁移")


def import_enemy(session, data: dict):
    """导入单个敌人 + 知识切片"""
    article_id = data["meta"]["article_id"]
    basic = data["basic"]

    # ---- 敌人主表 ----
    en = Enemy(
        article_id=article_id,
        name=basic["name"],
        nickname=basic.get("nickname", ""),
        display_type=basic.get("display_type", ""),
        is_dangerous=basic.get("is_dangerous", False),
        background=data.get("background", {}).get("body", ""),
        level_curve=data.get("stats", {}).get("level_curve", {}),
        updated_at=data["meta"]["updated_at"],
    )
    session.add(en)

    # ---- 战斗属性 ----
    for a in data.get("stats", {}).get("groups", []):
        session.add(EnemyAttribute(
            enemy_id=article_id,
            group_key=a["group_key"],
            group_label=a["group_label"],
            label=a["label"],
            value=a.get("value"),
            format=a.get("format", ""),
            attr_type=a.get("attr_type", ""),
        ))

    # ---- 抗性 ----
    for r in data.get("resistances", []):
        session.add(EnemyResistance(
            enemy_id=article_id,
            element=r["element"],
            element_label=r.get("element_label", ""),
            percent=r.get("percent"),
            scalar=r.get("scalar"),
        ))

    # ---- 技能 ----
    for ab in data.get("abilities", []):
        session.add(EnemyAbility(
            enemy_id=article_id,
            ordinal=ab.get("ordinal"),
            ability_id=ab.get("ability_id", ""),
            description=ab.get("description", ""),
        ))

    # ---- 掉落 ----
    for d in data.get("drops", []):
        session.add(EnemyDrop(
            enemy_id=article_id,
            item_name=d["name"],
            item_id=d.get("item_id", ""),
            rarity=d.get("rarity"),
        ))

    # ---- 变体 ----
    for v in data.get("variants", []):
        session.add(EnemyVariant(
            enemy_id=article_id,
            variant_enemy_id=v.get("enemy_id", ""),
            is_dangerous=v.get("is_dangerous", False),
            modifiers=v.get("modifiers", []),
            level_curve=v.get("level_curve", {}),
        ))

    # ---- 知识切片（向量库文本）----
    name = basic["name"]
    chunks = []

    # 档案
    bg = data.get("background", {}).get("body", "")
    if bg:
        chunks.append(("enemy_background", f"敌人{name}档案：{bg}"))

    # 技能
    for ab in data.get("abilities", []):
        desc = ab.get("description", "")
        if desc:
            chunks.append(("enemy_ability", f"敌人{name}技能{ab.get('ordinal', '')}：{desc}"))

    # 抗性
    if data.get("resistances"):
        res_text = "、".join(
            f"{r.get('element_label', r.get('element', ''))}抗性{r.get('percent', '?')}%"
            for r in data["resistances"]
        )
        chunks.append(("enemy_resistance", f"敌人{name}元素抗性：{res_text}"))

    # 掉落
    for d in data.get("drops", []):
        chunks.append(("enemy_drop", f"敌人{name}掉落：{d['name']}（{d.get('rarity', '?')}星）"))

    # 攻略提示
    for tip in data.get("tips", []):
        if tip:
            chunks.append(("enemy_tip", f"敌人{name}攻略提示：{tip}"))

    # 变体
    for v in data.get("variants", []):
        mod_text = "、".join(m.get("text", "") for m in v.get("modifiers", []))
        if mod_text:
            chunks.append(("enemy_variant", f"敌人{name}变体（{v.get('enemy_id', '')}）：{mod_text}"))

    for ctype, ctext in chunks:
        session.add(KnowledgeChunk(
            enemy_id=article_id,
            operator_id=None,
            weapon_id=None,
            chunk_type=ctype,
            content=ctext,
            embedding=None,
        ))

    return en.name, len(chunks)


def main():
    print("创建敌人表 ...")
    init_db()

    print("=" * 50)
    migrate_knowledge_chunks()

    session = SessionLocal()

    try:
        print("\n" + "=" * 50)
        print("导入敌人数据 ...\n")

        json_files = sorted(
            f for f in os.listdir(ENEMIES_DIR)
            if f.endswith(".json") and f != "enemies.json"
        )

        total = len(json_files)
        success = 0
        total_chunks = 0

        for i, filename in enumerate(json_files, 1):
            filepath = os.path.join(ENEMIES_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 跳过已存在的敌人
            existing = session.query(Enemy).filter_by(
                article_id=data["meta"]["article_id"]
            ).first()
            if existing:
                print(f"[{i:02d}/{total}] {data['basic']['name']} - 已存在，跳过")
                success += 1
                continue

            try:
                name, chunk_count = import_enemy(session, data)
                session.commit()
                success += 1
                total_chunks += chunk_count
                print(f"[{i:02d}/{total}] {name} OK (chunks: {chunk_count})")
            except Exception as e:
                session.rollback()
                print(f"[{i:02d}/{total}] {filename} ERROR: {e}")

        print(f"\n导入完成: {success}/{total} 敌人, 共 {total_chunks} 条知识切片")

    finally:
        session.close()


if __name__ == "__main__":
    main()
