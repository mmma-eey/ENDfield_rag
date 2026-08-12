# -*- coding: utf-8 -*-
"""术语纠偏脚本 —— 通用清洗 ASR 转写文本中的同音/错字术语

流程：
1. 从 data_main/data_wiki 自动收集权威术语（干员/武器/装备/敌人名）
2. 补充游戏领域通用机制词（技力/腐蚀/脆弱/连携...）
3. 调 DeepSeek 分析文本中的错词，输出 {错词: 正确词} 映射（JSON）
4. 脚本按映射批量替换（长词优先，避免部分替换）
5. 输出清洗后文本 + 替换报告

用法:
  单文件: python scripts/term_correction.py <输入txt> [输出txt]
  批量  : python scripts/term_correction.py --all   # 清洗 data_main/data_community 下全部 .txt
          python scripts/term_correction.py a.txt b.txt   # 多个文件逐个清洗
"""
import os
import sys
import json
import re

sys.path.insert(0, r"c:\Users\lenovo\Desktop\ENDfield_rag")
from rag.config import DEEPSEEK_BASE_URL, LLM_MODEL, REPLY_API_KEY

DATA_WIKI = r"c:\Users\lenovo\Desktop\ENDfield_rag\data_main\data_wiki"
DATA_COMMUNITY = r"c:\Users\lenovo\Desktop\ENDfield_rag\data_main\data_community"

# 纠偏专用模型：必须用非推理模型。LLM_MODEL=deepseek-v4-flash 是推理模型，
# 输出全在 reasoning_content、content 恒为空，无法用于 JSON 提取。
CORRECTION_MODEL = os.getenv("CORRECTION_MODEL", "deepseek-chat")

# 安全目标词白名单：不在权威术语表里、但允许模型纠偏到的常见游戏/口语词。
# 用于过滤 LLM 幻觉（如 叠252流→二蜗牛、清波→轻波 这类反向/编造映射）。
ALLOWLIST_COMMON = {
    "战技", "连携", "结论", "角色", "角色评测", "面板值", "聚怪", "易伤", "增幅",
    "精锻", "充能", "破会阵", "处决", "重击", "乘算", "泛用性", "常驻", "专三",
    "冻屏", "如果", "智觉", "意觉", "零潜", "一潜", "满潜", "五潜", "二潜", "专精",
    "冷启动", "实战", "输出", "辅助", "大招", "普攻", "主C", "副C", "队伍", "对群",
    "对单", "手感", "倍率", "伤害", "词条", "被动", "天赋", "专武", "档位", "帧",
    "终末地", "明日方舟", "测评", "决测评", "评测", "视频", "拜拜", "下期", "回响",
    "博士", "增伤", "效果", "能力", "机制", "循环", "操作", "轴", "配装", "首轮",
    "阶段", "覆盖", "消耗", "回复", "触发", "状态", "场景", "环境", "敌人", "目标",
    "范围", "爆伤", "暴击", "倍率", "每秒", "维持", "第二C", "智力",
}

# 已知高频错词硬规则：经人工确认的确定性同音错词，不依赖 LLM、每次必纠。
# 兜底 LLM 的不稳定（如本次漏纠 轻波→清波、凌雨→囹圄）。
KNOWN_ALIASES = {
    "轻波": "清波",          # 清波装备组
    "凌雨": "囹圄", "淋雨": "囹圄", "灵雨": "囹圄",   # 诀的囹圄状态
}

# 游戏领域通用机制词（非实体名，但 ASR 高频误写）
MECHANISM_TERMS = [
    "技力", "腐蚀", "脆弱", "附着", "连携", "囹圄", "增益", "灼热",
    "减抗", "充能", "聚怪", "破坏阵", "急速打击", "永续", "后摇",
    "重击", "处决", "实战", "专精", "潜能", "源石技艺", "初始伤害",
    "法术增幅", "智识", "意志", "主C", "副C", "攻坚", "开荒", "冷启动",
]


def collect_terms():
    """从 data_wiki 收集所有权威实体名（干员/武器/敌人/装备 + 干员技能天赋名）"""
    terms = set(MECHANISM_TERMS)
    sources = {}

    # 干员名
    op_file = os.path.join(DATA_WIKI, "operator_data", "operator.json")
    with open(op_file, encoding="utf-8") as f:
        ops = json.load(f)
    terms.update(ops)
    sources["干员"] = ops

    # 干员技能/天赋名（诀的"阵诀·智"、囹圄等都在这里）
    skill_names = set()
    for op in ops:
        opj = os.path.join(DATA_WIKI, "operator_data", f"{op}.json")
        if not os.path.exists(opj):
            continue
        try:
            with open(opj, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for sk in data.get("skills", []):
            if sk.get("name"):
                skill_names.add(sk["name"])
        for tk in data.get("talents", []):
            if tk.get("name"):
                skill_names.add(tk["name"])
    if skill_names:
        terms.update(skill_names)
        sources["技能"] = sorted(skill_names)

    # 武器名
    w_file = os.path.join(DATA_WIKI, "weapons_data", "weapons.json")
    with open(w_file, encoding="utf-8") as f:
        weapons = json.load(f)
    terms.update(weapons)
    sources["武器"] = weapons

    # 敌人名
    e_file = os.path.join(DATA_WIKI, "enemies_data", "enemies.json")
    with open(e_file, encoding="utf-8") as f:
        enemies = json.load(f)
    terms.update(enemies)
    sources["敌人"] = enemies

    # 装备名（从文件名提取，去掉 .json）
    equip_dir = os.path.join(DATA_WIKI, "equipments_data")
    equips = []
    for fn in os.listdir(equip_dir):
        if fn.endswith(".json") and not fn.startswith(("equipments",)):
            equips.append(fn[:-5])
    terms.update(equips)
    sources["装备"] = equips

    # 过滤掉过短/含特殊字符的术语（避免误替换）
    valid = {t for t in terms if len(t) >= 2 and not re.search(r"[αβγδ·:：]", t)}
    return sorted(valid, key=len, reverse=True), sources


def build_prompt(text, terms, sources):
    term_block = ""
    for cat, names in sources.items():
        term_block += f"【{cat}】{'、'.join(names[:80])}\n"
    return f"""你是游戏术语纠偏专家。以下是一段由语音识别（ASR）生成的《明日方舟：终末地》游戏测评转写文本，其中包含大量同音错字术语。

【权威术语表】（正确写法）：
{term_block}

【规则】
1. 找出文本中与权威术语对应的【错误写法】（同音字、近音字、错字，如"自觉/智觉"→"阵诀·智"、"击力/吉力"→"技力"、"辅蚀"→"腐蚀"）
2. 只纠正术语类错误，不要改动数字、标点、正常语句
3. 输出严格的 JSON 对象：{{"错误词": "正确词", ...}}，每个错误词必须是文本中实际出现的原样词
4. 不要输出任何 JSON 以外的内容

【转写文本】
{text}"""


def llm_build_mapping(text, terms, sources):
    """调 DeepSeek 生成纠偏映射（json_object 模式 + 重试）"""
    from openai import OpenAI
    import time
    client = OpenAI(api_key=REPLY_API_KEY, base_url=DEEPSEEK_BASE_URL)
    prompt = build_prompt(text, terms, sources)
    content = ""
    for attempt in range(3):
        resp = client.chat.completions.create(
            model=CORRECTION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        if content and content.strip():
            break
        print(f"  [!] 第{attempt+1}次空响应，重试 ...")
        time.sleep(1.5)
    if not content or not content.strip():
        print("  [!] 多次空响应，返回空映射")
        return {}
    # 提取 JSON（兼容 ```json 包裹）
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        print("  [!] 无法从响应提取 JSON:", content[:300])
        return {}
    try:
        mapping = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        print("  [!] JSON 解析失败:", e, content[:300])
        return {}
    mapping = {k: v for k, v in mapping.items() if k != v}
    return post_filter_mapping(mapping, terms, sources)


def post_filter_mapping(mapping, terms, sources):
    """过滤 LLM 幻觉映射：
    1. 错误词必须 ≥2 字（单字替换风险极高，如 绝→觉、角→觉）
    2. 正确词必须 ∈ 权威术语表 ∪ 安全白名单（挡住 二蜗牛/轻波/淋雨 等编造目标）
    """
    allowed = set(terms)
    for v in sources.values():
        allowed.update(v)
    allowed.update(ALLOWLIST_COMMON)
    kept, dropped = {}, 0
    for k, v in mapping.items():
        if k == v or len(k) < 2 or v not in allowed:
            dropped += 1
            continue
        kept[k] = v
    if dropped:
        print(f"      后置过滤剔除 {dropped} 条高风险映射")
    return kept


def apply_mapping(text, mapping):
    """批量替换：按错误词长度降序，避免短词覆盖长词"""
    stats = {}
    for wrong in sorted(mapping, key=len, reverse=True):
        if wrong not in text:
            continue
        count = text.count(wrong)
        text = text.replace(wrong, mapping[wrong])
        stats[wrong] = (mapping[wrong], count)
    return text, stats


def correct_file(in_path, out_path=None):
    """清洗单个文件，返回 (替换词数, 映射条数)"""
    with open(in_path, encoding="utf-8") as f:
        text = f.read()
    print(f"\n=== {in_path} ({len(text)} 字符) ===")

    print("[1/3] 收集权威术语 ...")
    terms, sources = collect_terms()
    detail = "/".join(f"{k}{len(v)}" for k, v in sources.items())
    print(f"      共 {len(terms)} 个术语（{detail}）")

    print("[2/3] LLM 分析错词映射 ...")
    mapping = llm_build_mapping(text, terms, sources)
    print(f"      得到 {len(mapping)} 条映射")

    print("[3/3] 批量替换 ...")
    corrected, stats = apply_mapping(text, mapping)
    # 已知错词硬规则兜底（轻波→清波、凌雨→囹圄）
    corrected, alias_stats = apply_mapping(corrected, KNOWN_ALIASES)
    stats.update(alias_stats)
    if out_path is None:
        out_path = os.path.splitext(in_path)[0] + "_corrected.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(corrected)
    # 映射存 json 便于审计
    map_path = os.path.splitext(out_path)[0] + ".mapping.json"
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"      替换了 {len(stats)} 个词，输出 → {out_path}")

    print("\n--- 替换明细 ---")
    for wrong, (right, cnt) in sorted(stats.items(), key=lambda x: -x[1][1]):
        print(f"  {wrong} → {right}  ×{cnt}")

    print("\n--- 清洗后预览前 300 字 ---\n")
    print(corrected[:300])
    return len(stats), len(mapping)


def main():
    args = sys.argv[1:]

    # 批量模式：--all 清洗 data_community 下全部 .txt
    if "--all" in args:
        files = sorted(
            os.path.join(DATA_COMMUNITY, fn)
            for fn in os.listdir(DATA_COMMUNITY)
            if fn.endswith(".txt")
        )
    else:
        files = [a for a in args if a.endswith(".txt")]
    if not files:
        print("用法:")
        print("  python scripts/term_correction.py <输入txt> [输出txt]")
        print("  python scripts/term_correction.py --all   # 清洗 data_community 全部 .txt")
        sys.exit(1)

    for in_path in files:
        correct_file(in_path)


if __name__ == "__main__":
    main()
