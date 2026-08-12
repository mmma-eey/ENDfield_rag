"""评测用例生成器 —— 从数据库程序化生成 100+ 条对比测试用例

覆盖：干员(30名×3) / 武器 / 敌人 / 装备 / 列表筛选 / 机制人工题
每条标注：expected_sources（来源命中）、expected_keywords（关键词召回）、
         expected_intents（期望意图标签，用于评测意图判断准确率）

输出: tests/eval_compare_queries.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from db.models import (Enemy, Equipment, Operator, Weapon)
from rag.sql_fallback import UNLOCK_LABELS


def main():
    s = SessionLocal()
    queries = []
    idx = 0

    def add(cat, q, sources, kws, intents):
        nonlocal idx
        idx += 1
        queries.append({
            "id": f"G{idx:03d}",
            "category": cat,
            "question": q,
            "expected_sources": sources,
            "expected_keywords": kws,
            "expected_intents": intents,
        })

    # ================= 干员（30 名 × 3 条）=================
    ops = s.query(Operator).order_by(Operator.rarity.desc(), Operator.name).all()
    for op in ops:
        n = op.name
        # 1) 星级/职业（database）
        add("operator_stat", f"{n}是几星干员，什么职业？",
            [n], [f"{op.rarity}星", op.profession], ["database"])
        # 2) 技能名列表（database）
        skill_names = [sk.name for sk in op.skills if sk.name]
        if skill_names:
            add("operator_skill", f"{n}有哪些技能？",
                [n], [skill_names[0]], ["database"])
        # 3) 背景故事（vector）
        add("operator_lore", f"{n}的背景故事是什么？",
            [n], [], ["vector"])

    # ================= 敌人（精选 6 名 × 3 条）=================
    enemies = s.query(Enemy).filter(Enemy.is_dangerous.is_(True)).order_by(Enemy.name).all()
    if len(enemies) < 6:
        enemies = s.query(Enemy).order_by(Enemy.name).limit(6).all()
    for en in enemies[:6]:
        n = en.name
        drops = [d.item_name for d in en.drops]
        ress = [r.element_label for r in en.resistances if r.element_label]
        if drops:
            add("enemy_drop", f"{n}会掉落什么材料？",
                [n], drops[:2], ["database"])
        if ress:
            add("enemy_resist", f"{n}的元素抗性是什么？",
                [n], ress[:2], ["database"])
        add("enemy_skill", f"{n}有什么攻击方式或技能？",
            [n], [], ["vector"])

    # ================= 武器（精选 10 名）=================
    weapons = s.query(Weapon).order_by(Weapon.rarity.desc(), Weapon.name).all()
    for w in weapons[:10]:
        n = w.name
        sk = w.skills[0] if w.skills else None
        kw = [sk.name] if sk and sk.name else []
        add("weapon_skill", f"{n}武器的技能效果是什么？",
            [n], kw, ["vector"])
        add("weapon_match", f"{n}适合什么干员使用？",
            [n], [], ["vector"])

    # ================= 装备（精选 12 名 × 2 条）=================
    equips = s.query(Equipment).order_by(Equipment.rarity.desc(), Equipment.name).all()
    for e in equips[:12]:
        n = e.name
        stat_labels = [st.label for st in e.stats if st.label]
        kw = stat_labels[:2] if stat_labels else []
        add("equipment_stat", f"{n}是什么部位的装备，附加什么属性？",
            [n], [e.slot_type] + kw[:1], ["database"])
        add("equipment_unlock", f"{n}怎么获得？",
            [n], [UNLOCK_LABELS.get(e.unlock_type, e.unlock_type)] if e.unlock_type else [], ["database"])

    # ================= 列表筛选（程序化 8 条）=================
    # 干员星级 × 职业组合（取实际存在的组合）
    combos = {}
    for op in ops:
        combos.setdefault((op.rarity, op.profession), []).append(op.name)
    for (star, prof), names in sorted(combos.items(), key=lambda x: -x[0][0]):
        if len(names) >= 2:
            add("operator_search", f"有哪些{star}星{prof}干员？",
                names[:3], [prof], ["database"])
    # 装备部位列表
    slots = {}
    for e in equips:
        slots.setdefault(e.slot_type, []).append(e.name)
    for slot, names in list(slots.items())[:2]:
        add("equipment_search", f"有哪些{slot}装备？",
            names[:3], [slot], ["database"])

    # ================= 人工机制 / 对比 / 混合题（12 条）=================
    manual = [
        # (category, question, sources, keywords, intents)
        ("mechanism", "什么是灼热附着？", [],
         ["灼热附着", "灼热伤害"], ["vector"]),
        ("mechanism", "什么是连携技？", [],
         ["连携技"], ["vector"]),
        ("mechanism", "干员的终结技有什么特点？", [],
         ["终结技"], ["vector"]),
        ("weapon_compare", "镀红祝福和灯火使命哪个更适合卡缪？",
         ["卡缪", "镀红祝福", "灯火使命"],
         ["镀红祝福", "灯火使命"], ["vector", "database"]),
        ("weapon_compare", "卡缪90级攻击力是多少？",
         ["卡缪"], ["攻击力", "90"], ["database"]),
        ("mechanism", "伏血能恢复多少技力？",
         ["卡缪", "伏血"], ["伏血", "技力"], ["vector", "database"]),
        ("operator_search", "有哪些终末地工业的干员？",
         ["卡缪", "佩丽卡", "陈千语"], ["终末地工业"], ["database"]),
        ("operator_search", "有哪些五星干员？",
         ["佩丽卡", "大潘", "弧光"], ["5星"], ["database"]),
        ("equipment_search", "有哪些五星护甲装备？",
         ["集成实训护甲", "纾难重甲"], ["护甲"], ["database"]),
        ("lore", "陈千语的语音台词有哪些？",
         ["陈千语"], ["语音"], ["vector"]),
        ("mechanism", "哪些干员有灼热伤害？",
         ["卡缪", "狼卫", "莱万汀"], ["灼热"], ["vector", "database"]),
        ("weapon_recommend", "别礼适合带什么武器？",
         ["别礼", "赫拉芬格"], ["武器"], ["vector", "database"]),
    ]
    for cat, q, src, kw, ints in manual:
        add(cat, q, src, kw, ints)

    s.close()

    # 输出
    out = {
        "total": len(queries),
        "categories": {
            "operator_stat": "干员数值查询",
            "operator_skill": "干员技能查询",
            "operator_lore": "干员档案/背景",
            "operator_search": "干员条件筛选",
            "enemy_drop": "敌人掉落",
            "enemy_resist": "敌人抗性",
            "enemy_skill": "敌人技能",
            "weapon_skill": "武器技能效果",
            "weapon_match": "武器适配推荐",
            "weapon_compare": "武器对比/推荐",
            "weapon_recommend": "武器推荐",
            "equipment_stat": "装备属性查询",
            "equipment_unlock": "装备获取方式",
            "equipment_search": "装备条件筛选",
            "mechanism": "游戏机制解释",
            "lore": "剧情/语音/档案",
        },
        "scoring": {
            "source_hit_rate": "期望来源出现在召回 Top5 的比例",
            "keyword_recall": "回答包含期望关键词的比例",
            "intent_acc": "意图判断与期望标签一致的比例",
            "pass": "source_hit>0 且 keyword_recall>0 记为通过",
        },
        "queries": queries,
    }
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tests", "第一次评测", "eval_compare_queries.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 分布统计
    from collections import Counter
    cats = Counter(q["category"] for q in queries)
    ints = Counter(tuple(q["expected_intents"]) for q in queries)
    print(f"生成 {len(queries)} 条用例 → {out_path}")
    print("\n类别分布:")
    for c, n in cats.most_common():
        print(f"  {c}: {n}")
    print("\n意图分布:")
    for i, n in ints.most_common():
        print(f"  {list(i)}: {n}")


if __name__ == "__main__":
    main()
