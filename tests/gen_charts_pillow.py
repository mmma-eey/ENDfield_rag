"""评测图表生成 —— Pillow 手绘 PNG 图表

背景：matplotlib 依赖的 numpy OpenBLAS 在沙箱环境运行时崩溃(0xC06D007F)，
改用纯 Python + Pillow 绘制（不依赖 numpy/matplotlib）。

输入（均在 tests/第一次评测/ 下）:
- eval_compare_results.json （端到端 4 组合）
- retrieval_full.json      （检索层 RRF vs MinMax）
输出: tests/第一次评测/charts/*.png
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "第一次评测")
CHARTS = os.path.join(BASE, "charts")
os.makedirs(CHARTS, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

CFG_ORDER = ["A-rrf", "A-minmax", "B-rrf", "B-minmax"]
CFG_SHORT = {"A-rrf": "A+RRF", "A-minmax": "A+MinMax", "B-rrf": "B+RRF", "B-minmax": "B+MinMax"}
CFG_COLOR = {"A-rrf": (76, 114, 176), "A-minmax": (221, 132, 82),
             "B-rrf": (85, 168, 104), "B-minmax": (196, 78, 82)}
METRIC_CN = {"pass_rate": "通过率", "avg_source_hit": "来源命中",
             "avg_keyword_recall": "关键词召回", "avg_intent_hit": "意图命中"}


def _font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, size)


def _text_w(font, s):
    b = font.getbbox(s)
    return b[2] - b[0]


def _draw_centered(d, xy, s, font, fill):
    x, y = xy
    d.text((x - _text_w(font, s) / 2, y), s, font=font, fill=fill)


def _draw_right(d, xy, s, font, fill):
    x, y = xy
    d.text((x - _text_w(font, s), y), s, font=font, fill=fill)


def load(name):
    p = os.path.join(BASE, name)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ================= 1. 总体得分（分组柱状图） =================
def chart1_overall(e2e, out):
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]
    metrics = ["pass_rate", "avg_source_hit", "avg_keyword_recall", "avg_intent_hit"]
    vals = [[summary[c].get(m, 0) for m in metrics] for c in cfgs]

    W, H = 1280, 640
    pad_l, pad_r, pad_t, pad_b = 90, 30, 90, 90
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    _draw_centered(d, (W / 2, 28),
                   "总体得分对比：意图方式(A单模型/B双模型) × 融合方式(RRF/MinMax)", _font(26, True), (30, 30, 30))

    # 网格 + y 轴
    for i in range(6):
        y = pad_t + plot_h - plot_h * i / 5
        d.line([(pad_l, y), (pad_l + plot_w, y)], fill=(224, 224, 224), width=1)
        _draw_right(d, (pad_l - 10, y - 9), f"{i / 5:.1f}", _font(14), (90, 90, 90))

    n_groups, n_bars = len(metrics), len(cfgs)
    group_w = plot_w / n_groups
    bar_w = group_w * 0.7 / n_bars

    for gi, g in enumerate(vals):
        gx = pad_l + gi * group_w
        # 组标签（指标名）
        _draw_centered(d, (gx + group_w / 2, pad_t + plot_h + 14), METRIC_CN[metrics[gi]], _font(18), (30, 30, 30))
        for bi, (v, cfg) in enumerate(zip(g, cfgs)):
            h = plot_h * (v / 1.15)
            x = gx + group_w * 0.15 + bi * bar_w
            y = pad_t + plot_h - h
            d.rectangle([x, y, x + bar_w, pad_t + plot_h], fill=CFG_COLOR[cfg])
            if v > 0:
                _draw_centered(d, (x + bar_w / 2, y - 20), f"{v:.2f}", _font(13), (60, 60, 60))

    # 图例
    lx = pad_l + 10
    for cfg in cfgs:
        d.rectangle([lx, H - 46, lx + 18, H - 28], fill=CFG_COLOR[cfg])
        d.text((lx + 26, H - 48), CFG_SHORT[cfg], font=_font(16), fill=(30, 30, 30))
        lx += 40 + _text_w(_font(16), CFG_SHORT[cfg])
    img.save(os.path.join(out, "1_总体得分对比.png"))
    print("1_总体得分对比.png")


# ================= 2. 分类通过率热图 =================
def chart2_heatmap(e2e, out):
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]
    cats = sorted(set().union(*(summary[c].get("categories", {}).keys() for c in cfgs)))

    W, H = 1300, 110 + len(cats) * 34
    pad_l, pad_t = 200, 70
    cell_w = 210
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    _draw_centered(d, (W / 2, 26), "分类别通过率热图（颜色越深通过率越高）", _font(24, True), (30, 30, 30))
    for j, c in enumerate(cfgs):
        _draw_centered(d, (pad_l + j * cell_w + cell_w / 2, pad_t - 22), CFG_SHORT[c], _font(16), (30, 30, 30))
    for i, cat in enumerate(cats):
        y = pad_t + i * 34
        d.text((pad_l - 12, y + 4), cat, font=_font(15), fill=(30, 30, 30), anchor="rs")
        for j, cfg in enumerate(cfgs):
            st = summary[cfg].get("categories", {}).get(cat)
            v = st["passed"] / st["total"] if st and st["total"] else 0.0
            r = int(255 * (1 - v) + 60 * v)
            g = int(235 * (1 - v) + 90 * v)
            b = int(235 * (1 - v) + 90 * v)
            x = pad_l + j * cell_w
            d.rectangle([x, y, x + cell_w - 6, y + 30], fill=(r, g, b))
            if v > 0:
                _draw_centered(d, (x + (cell_w - 6) / 2, y + 6), f"{v:.0%}", _font(14), (20, 20, 20))
            else:
                _draw_centered(d, (x + (cell_w - 6) / 2, y + 6), "-", _font(14), (120, 120, 120))
    img.save(os.path.join(out, "2_分类通过率热图.png"))
    print("2_分类通过率热图.png")


# ================= 3. 平均耗时 =================
def chart3_time(e2e, out):
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]
    times = [summary[c]["avg_time"] for c in cfgs]

    W, H = 1100, 560
    pad_l, pad_r, pad_t, pad_b = 90, 40, 90, 100
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    _draw_centered(d, (W / 2, 28),
                   "平均响应耗时对比（A=单模型全走Agent；B=小模型分类+快速路径）", _font(24, True), (30, 30, 30))
    y_max = 10.0
    for i in range(6):
        y = pad_t + plot_h - plot_h * i / 5
        d.line([(pad_l, y), (pad_l + plot_w, y)], fill=(224, 224, 224), width=1)
        _draw_right(d, (pad_l - 10, y - 9), f"{y_max * i / 5:.0f}", _font(14), (90, 90, 90))
    d.text((pad_l - 10, pad_t + plot_h + 6), "秒", font=_font(14), fill=(90, 90, 90))

    n = len(cfgs)
    bar_w = plot_w / n * 0.5
    for i, (cfg, t) in enumerate(zip(cfgs, times)):
        x = pad_l + plot_w / n * i + (plot_w / n - bar_w) / 2
        h = plot_h * (t / y_max)
        y = pad_t + plot_h - h
        d.rectangle([x, y, x + bar_w, pad_t + plot_h], fill=CFG_COLOR[cfg])
        _draw_centered(d, (x + bar_w / 2, y - 26), f"{t:.1f}s", _font(15), (30, 30, 30))
        _draw_centered(d, (x + bar_w / 2, pad_t + plot_h + 12), CFG_SHORT[cfg], _font(16), (30, 30, 30))
    img.save(os.path.join(out, "3_平均耗时对比.png"))
    print("3_平均耗时对比.png")


# ================= 4. 检索融合对比（横向条形图） =================
def _hbar_chart(title, items, color, path):
    pad_l, pad_r, pad_t, pad_b = 260, 200, 70, 40
    row_h = 36
    H = pad_t + pad_b + len(items) * row_h
    W = 1280
    plot_w = W - pad_l - pad_r
    max_v = max((v for _, v in items), default=1) or 1
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    _draw_centered(d, (W / 2, 30), title, _font(22, True), (30, 30, 30))
    for i, (lab, v) in enumerate(items):
        y = pad_t + i * row_h
        d.text((pad_l - 14, y + 4), lab, font=_font(15), fill=(30, 30, 30), anchor="rs")
        w = plot_w * (v / max_v)
        d.rectangle([pad_l, y, pad_l + w, y + 24], fill=color)
        d.text((pad_l + w + 10, y + 4), f"{v:.3f}", font=_font(15), fill=(30, 30, 30))
    img.save(path)
    print(os.path.basename(path))


def chart4_fusion_retrieval(ret, out):
    cats = sorted(ret.get("categories", {}).keys())
    items_r = [(c, ret["categories"][c]["rrf_avg"]) for c in cats]
    items_m = [(c, ret["categories"][c]["minmax_avg"]) for c in cats]
    _hbar_chart(f"各分类 Top5 来源命中率 —— RRF（平均 {ret['avg_source_hit']['rrf']:.3f}）",
                items_r, (76, 114, 176), os.path.join(out, "4a_检索融合对比_RRF.png"))
    _hbar_chart(f"各分类 Top5 来源命中率 —— MinMax（平均 {ret['avg_source_hit']['minmax']:.3f}）",
                items_m, (221, 132, 82), os.path.join(out, "4b_检索融合对比_MinMax.png"))


# ================= 5. 两两胜率矩阵 =================
def chart5_win_matrix(e2e, out):
    details = e2e["details"]
    groups = {}
    for d in details:
        groups.setdefault(d["config"], {})[d["id"]] = d
    cfgs = [c for c in CFG_ORDER if c in groups]

    cell = 150
    pad_l, pad_t = 190, 80
    W = pad_l + len(cfgs) * cell + 30
    H = pad_t + len(cfgs) * cell + 40
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    _draw_centered(d, (W / 2, 30), "来源命中两两胜率矩阵（行 vs 列，>0.5 表示行更优）", _font(22, True), (30, 30, 30))
    for j, c in enumerate(cfgs):
        _draw_centered(d, (pad_l + j * cell + cell / 2, pad_t - 26), CFG_SHORT[c], _font(16), (30, 30, 30))
    for i, ci in enumerate(cfgs):
        d.text((pad_l - 14, pad_t + i * cell + cell / 2 - 10), CFG_SHORT[ci], font=_font(16), fill=(30, 30, 30), anchor="rs")
        for j, cj in enumerate(cfgs):
            x, y = pad_l + j * cell, pad_t + i * cell
            if i == j:
                d.rectangle([x + 3, y + 3, x + cell - 3, y + cell - 3], fill=(230, 230, 230))
                _draw_centered(d, (x + cell / 2, y + cell / 2 - 10), "-", _font(16), (90, 90, 90))
                continue
            ids = set(groups[ci].keys()) & set(groups[cj].keys())
            win = sum(1 for qid in ids if groups[ci][qid]["source_hit_rate"] > groups[cj][qid]["source_hit_rate"])
            tie = sum(1 for qid in ids if groups[ci][qid]["source_hit_rate"] == groups[cj][qid]["source_hit_rate"])
            v = (win + 0.5 * tie) / len(ids) if ids else 0.5
            if v >= 0.5:
                r, g, b = int(255 * (1 - (v - 0.5) * 2)), int(160 + (v - 0.5) * 2 * 60), 110
            else:
                r, g, b = 230, int(90 + v * 2 * 60), int(70 + v * 2 * 60)
            d.rectangle([x + 3, y + 3, x + cell - 3, y + cell - 3], fill=(r, g, b))
            _draw_centered(d, (x + cell / 2, y + cell / 2 - 10), f"{v:.2f}", _font(18, True), (20, 20, 20))
    img.save(os.path.join(out, "5_两两胜率矩阵.png"))
    print("5_两两胜率矩阵.png")


def main():
    e2e = load("eval_compare_results.json")
    ret = load("retrieval_full.json")
    chart1_overall(e2e, CHARTS)
    chart2_heatmap(e2e, CHARTS)
    chart3_time(e2e, CHARTS)
    chart4_fusion_retrieval(ret, CHARTS)
    chart5_win_matrix(e2e, CHARTS)
    print(f"\n图表已输出至: {CHARTS}")


if __name__ == "__main__":
    main()
