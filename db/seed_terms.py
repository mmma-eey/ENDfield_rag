"""种子数据 —— 玩家黑话 → 官方术语映射"""
SEED_TERMS = [
    # === 技能类 ===
    {"slang": "大招", "official": "终结技", "category": "skill", "priority": 3},
    {"slang": "必杀", "official": "终结技", "category": "skill", "priority": 2},
    {"slang": "必杀技", "official": "终结技", "category": "skill", "priority": 2},
    {"slang": "一技能", "official": "战技", "category": "skill", "priority": 3},
    {"slang": "小技能", "official": "战技", "category": "skill", "priority": 3},
    {"slang": "主动技能", "official": "战技", "category": "skill", "priority": 2},
    {"slang": "被动", "official": "天赋", "category": "skill", "priority": 3},
    {"slang": "被动技能", "official": "天赋", "category": "skill", "priority": 2},
    {"slang": "连携", "official": "连携技", "category": "skill", "priority": 3},
    {"slang": "普攻", "official": "普通攻击", "category": "skill", "priority": 3},
    {"slang": "平A", "official": "普通攻击", "category": "skill", "priority": 3},
    {"slang": "基建技能", "official": "后勤技能", "category": "skill", "priority": 3},
    {"slang": "后勤", "official": "后勤技能", "category": "skill", "priority": 2},
    {"slang": "工厂技能", "official": "后勤技能", "category": "skill", "priority": 2},

    # === 伤害/元素类 ===
    {"slang": "灼烧", "official": "灼热附着", "category": "element", "priority": 3},
    {"slang": "火伤", "official": "灼热伤害", "category": "element", "priority": 2},
    {"slang": "灼烧伤害", "official": "灼热伤害", "category": "element", "priority": 3},
    {"slang": "冰伤", "official": "寒冷伤害", "category": "element", "priority": 3},
    {"slang": "电伤", "official": "电磁伤害", "category": "element", "priority": 3},
    {"slang": "雷伤", "official": "电磁伤害", "category": "element", "priority": 2},
    {"slang": "毒伤", "official": "自然伤害", "category": "element", "priority": 2},
    {"slang": "物伤", "official": "物理伤害", "category": "element", "priority": 3},

    # === 机制类 ===
    {"slang": "打断", "official": "失衡", "category": "mechanic", "priority": 3},
    {"slang": "硬直", "official": "失衡", "category": "mechanic", "priority": 2},
    {"slang": "充能", "official": "技力恢复", "category": "mechanic", "priority": 3},
    {"slang": "回蓝", "official": "技力恢复", "category": "mechanic", "priority": 2},
    {"slang": "减防", "official": "防御力降低", "category": "mechanic", "priority": 2},
    {"slang": "增伤", "official": "伤害加成", "category": "mechanic", "priority": 2},
    {"slang": "易伤", "official": "脆弱", "category": "mechanic", "priority": 3},
    {"slang": "护盾", "official": "屏障", "category": "mechanic", "priority": 2},

    # === 职业/干员类 ===
    {"slang": "六星", "official": "6", "category": "rarity", "priority": 3},
    {"slang": "五星", "official": "5", "category": "rarity", "priority": 3},
    {"slang": "T0", "official": "强力干员", "category": "general", "priority": 1},

    # === 装备类 ===
    {"slang": "武器", "official": "适配武器", "category": "equip", "priority": 2},
    {"slang": "装备", "official": "适配武器", "category": "equip", "priority": 2},
    {"slang": "专武", "official": "专属武器", "category": "equip", "priority": 3},
]
