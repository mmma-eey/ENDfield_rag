"""对比评测图表报告 —— 生成自包含 HTML + 内联 SVG 图表

不依赖 matplotlib（避免环境 DLL 问题），输出单文件 HTML，
用浏览器即可打开查看所有对比图表。

输入:
- tests/reports/eval_compare_results.json （端到端 4 组合）
- tests/reports/retrieval_full.json      （检索层 RRF vs MinMax）
输出:
- tests/reports/eval_report.html
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "第一次评测")
OUT_PATH = os.path.join(REPORTS_DIR, "eval_report.html")

CFG_ORDER = ["A-rrf", "A-minmax", "B-rrf", "B-minmax"]
CFG_CN = {"A-rrf": "A·单模型意图+RRF", "A-minmax": "A·单模型意图+MinMax",
          "B-rrf": "B·双模型意图+RRF", "B-minmax": "B·双模型意图+MinMax"}
CFG_COLOR = {"A-rrf": "#4C72B0", "A-minmax": "#DD8452",
             "B-rrf": "#55A868", "B-minmax": "#C44E52"}
METRIC_CN = {"pass_rate": "通过率", "avg_source_hit": "来源命中",
             "avg_keyword_recall": "关键词召回", "avg_intent_hit": "意图命中"}

# ---------- SVG 基础工具 ----------
def svg_bars_groups(title, groups, labels, colors, y_max=1.0,
                    fmt="{:.2f}", fig_w=900, fig_h=420):
    """多组分组柱状图。groups: [[{value,label},...]...] 每列一组"""
    n_groups = len(groups)     # 柱子组数
    n_bars = len(labels)       # 每组柱数
    pad_l, pad_r, pad_t, pad_b = 70, 20, 50, 60
    plot_w = fig_w - pad_l - pad_r
    plot_h = fig_h - pad_t - pad_b
    group_w = plot_w / n_groups
    bar_w = group_w * 0.72 / n_bars

    parts = [f'<text x="{pad_l}" y="{30}" font-size="17" font-weight="bold">{title}</text>']
    # 网格 + Y 轴
    for i in range(6):
        y = pad_t + plot_h - plot_h * i / 5
        v = y_max * i / 5
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{fig_w-pad_r}" y2="{y:.1f}" '
                     f'stroke="#e0e0e0" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" font-size="11" text-anchor="end">{v:.1f}</text>')
    # 柱子 + 组标签
    for gi, grp in enumerate(groups):
        gx = pad_l + gi * group_w
        for bi, (val, lab) in enumerate(zip(grp, labels)):
            h = plot_h * (val / y_max) if val else 2
            x = gx + group_w * 0.14 + bi * bar_w
            y = pad_t + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                         f'fill="{colors[bi]}" rx="2"/>')
            if val > 0:
                parts.append(f'<text x="{x+bar_w/2:.1f}" y="{y-4:.1f}" font-size="10" '
                             f'text-anchor="middle">{fmt.format(val)}</text>')
        parts.append(f'<text x="{gx+group_w/2:.1f}" y="{pad_t+plot_h+22}" font-size="11" '
                     f'text-anchor="middle">{labels[0]}</text>')
        # 组标题（= 该组名）
        parts.append(f'<text x="{gx+group_w/2:.1f}" y="{pad_t+plot_h+42}" font-size="13" '
                     f'font-weight="bold" text-anchor="middle">{labels[0]}</text>')
    return f'<svg width="{fig_w}" height="{fig_h}" viewBox="0 0 {fig_w} {fig_h}">' + "".join(parts) + "</svg>"


def svg_heatmap(title, rows, cols, matrix, fmt="{:.0%}", fig_w=920):
    """热力图。rows: 行标签, cols: 列标签, matrix: 2D 数值"""
    pad_l, pad_r, pad_t, pad_b = 150, 30, 55, 60
    cell_w = min(120, (fig_w - pad_l - pad_r) / max(len(cols), 1))
    fig_h = pad_t + pad_b + len(rows) * 34
    plot_w = cell_w * len(cols)
    parts = [f'<text x="{pad_l}" y="{30}" font-size="17" font-weight="bold">{title}</text>']
    # 列头
    for j, c in enumerate(cols):
        x = pad_l + j * cell_w + cell_w / 2
        parts.append(f'<text x="{x:.1f}" y="{pad_t-18}" font-size="12" text-anchor="middle">{c}</text>')
    for i, r in enumerate(rows):
        y = pad_t + i * 34
        parts.append(f'<text x="{pad_l-10}" y="{y+20}" font-size="12" text-anchor="end">{r}</text>')
        for j in range(len(cols)):
            v = matrix[i][j]
            x = pad_l + j * cell_w
            # 蓝-黄-红 色阶
            rv = min(1.0, max(0.0, v))
            rr = int(255 * (1 - rv) + 200 * rv)
            gg = int(230 * (1 - rv) + 60 * rv)
            bb = int(230 * (1 - rv) + 60 * rv)
            color = f"rgb({rr},{gg},{bb})"
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cell_w-4:.1f}" height="30" '
                         f'fill="{color}" rx="3"/>')
            if v > 0:
                parts.append(f'<text x="{x+cell_w/2-2:.1f}" y="{y+20}" font-size="12" '
                             f'text-anchor="middle">{fmt.format(v)}</text>')
            else:
                parts.append(f'<text x="{x+cell_w/2-2:.1f}" y="{y+20}" font-size="12" '
                             f'text-anchor="middle">-</text>')
    return f'<svg width="{fig_w}" height="{fig_h}" viewBox="0 0 {fig_w} {fig_h}">' + "".join(parts) + "</svg>"


def svg_hbars(title, items, colors=None, fig_w=920):
    """横向条形图。items: [(label, value), ...]"""
    pad_l, pad_r, pad_t, pad_b = 210, 60, 50, 40
    row_h = 34
    fig_h = pad_t + pad_b + len(items) * row_h
    plot_w = fig_w - pad_l - pad_r
    max_v = max((v for _, v in items), default=1) or 1
    parts = [f'<text x="{pad_l}" y="{30}" font-size="17" font-weight="bold">{title}</text>']
    for i, (lab, v) in enumerate(items):
        y = pad_t + i * row_h
        w = plot_w * (v / max_v)
        color = (colors or ["#4C72B0"] * len(items))[i]
        parts.append(f'<rect x="{pad_l}" y="{y}" width="{w:.1f}" height="24" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{pad_l-10}" y="{y+17}" font-size="12" text-anchor="end">{lab}</text>')
        parts.append(f'<text x="{pad_l+w+6:.1f}" y="{y+17}" font-size="12">{v:.3f}</text>')
    return f'<svg width="{fig_w}" height="{fig_h}" viewBox="0 0 {fig_w} {fig_h}">' + "".join(parts) + "</svg>"


def svg_legend(items):
    return "".join(
        f'<span style="display:inline-block;margin-right:16px;">'
        f'<span style="display:inline-block;width:12px;height:12px;background:{c};'
        f'vertical-align:middle;"></span> {lab}</span>'
        for lab, c in items
    )


# ---------- 数据加载 ----------
def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    e2e_path = os.path.join(REPORTS_DIR, "eval_compare_results.json")
    ret_path = os.path.join(REPORTS_DIR, "retrieval_full.json")
    e2e = load(e2e_path)
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]

    html = []
    html.append("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
                "<title>ENDfield RAG 对比评测报告</title></head><body>")
    html.append("<style>body{font-family:'Microsoft YaHei',sans-serif;margin:24px;"
                "background:#f7f8fa;color:#222}"
                "h1{font-size:24px}h2{margin-top:44px;border-left:4px solid #4C72B0;"
                "padding-left:10px}.card{background:#fff;border-radius:10px;"
                "padding:20px 24px;margin:16px 0;box-shadow:0 1px 4px rgba(0,0,0,.08)}"
                "table{border-collapse:collapse;width:100%;font-size:14px}"
                "th,td{border:1px solid #ddd;padding:8px 12px;text-align:center}"
                "th{background:#f0f2f5}.ok{color:#2e7d32}.bad{color:#c62828}</style>")

    # ===== 概要 =====
    html.append(f"<h1>ENDfield RAG 对比评测报告</h1>")
    html.append("<div class='card'>"
                f"<b>测试规模：</b>{e2e['queries_total']} 条用例 × 4 种配置组合 "
                f"（{len(e2e['details'])} 次端到端调用）＋ 检索层 {load(ret_path)['total']} 条对比<br>"
                "<b>评测日期：</b>2026-08-10 ｜ <b>模型：</b>DeepSeek deepseek-chat ｜ "
                "<b>Embedding：</b>text-embedding-v4 ｜ <b>Reranker：</b>qwen3-rerank"
                "</div>")

    # ===== 1. 总体得分 =====
    html.append("<h2>1. 总体得分对比</h2><div class='card'>")
    metrics = ["pass_rate", "avg_source_hit", "avg_keyword_recall", "avg_intent_hit"]
    groups = []
    for cfg in cfgs:
        groups.append([summary[cfg].get(m, 0) for m in metrics])
    html.append(svg_bars_groups("端到端评测：意图方式(A单模型/B双模型) × 融合方式(RRF/MinMax)",
                                groups, [METRIC_CN[m] for m in metrics],
                                [CFG_COLOR[c] for c in cfgs]))
    html.append("<p>" + svg_legend([(CFG_CN[c], CFG_COLOR[c]) for c in cfgs]) + "</p>")
    html.append("</div>")

    # 得分表格
    html.append("<div class='card'><table><tr><th>配置</th><th>通过</th><th>通过率</th>"
                "<th>来源命中</th><th>关键词召回</th><th>意图命中</th><th>均耗时</th></tr>")
    for cfg in cfgs:
        s = summary[cfg]
        ok = "ok" if s["pass_rate"] > 0.9 else "bad"
        html.append(f"<tr><td><b>{CFG_CN[cfg]}</b></td>"
                    f"<td>{s['passed']}/{s['total']}</td>"
                    f"<td class='{ok}'>{s['pass_rate']:.1%}</td>"
                    f"<td>{s['avg_source_hit']:.3f}</td>"
                    f"<td>{s['avg_keyword_recall']:.3f}</td>"
                    f"<td>{s['avg_intent_hit']:.3f}</td>"
                    f"<td>{s['avg_time']:.1f}s</td></tr>")
    html.append("</table></div>")

    # ===== 2. 分类热图 =====
    html.append("<h2>2. 分类别通过率热图</h2><div class='card'>")
    cats = sorted(set().union(*(summary[c].get("categories", {}).keys() for c in cfgs)))
    matrix = []
    for cat in cats:
        row = []
        for cfg in cfgs:
            st = summary[cfg].get("categories", {}).get(cat)
            row.append(st["passed"] / st["total"] if st and st["total"] else 0.0)
        matrix.append(row)
    html.append(svg_heatmap("分类别通过率（颜色越深越高）", cats,
                            [CFG_CN[c] for c in cfgs], matrix))
    html.append("</div>")

    # ===== 3. 平均耗时 =====
    html.append("<h2>3. 平均响应耗时对比</h2><div class='card'>")
    groups = [[summary[c]["avg_time"] for c in cfgs]]
    html.append(svg_bars_groups("平均耗时（秒）", groups, [CFG_CN[c] for c in cfgs],
                                [CFG_COLOR[c] for c in cfgs], y_max=8, fmt="{:.1f}"))
    html.append("<p style='color:#666'>A=单模型全走Agent多次LLM判断；B=小模型分类+快速路径，耗时更短。</p>")
    html.append("</div>")

    # ===== 4. 检索融合对比 =====
    ret = load(ret_path)
    html.append("<h2>4. 检索层：RRF vs MinMax 归一化加权召回</h2><div class='card'>")
    html.append(f"<p><b>Top5 来源命中率：</b>RRF <b>{ret['avg_source_hit']['rrf']:.4f}</b> vs "
                f"MinMax <b>{ret['avg_source_hit']['minmax']:.4f}</b> ｜ "
                f"RRF胜 {ret['win_count']['rrf']} 条 / MinMax胜 {ret['win_count']['minmax']} 条 / "
                f"平局 {ret['win_count']['tie']} 条（共 {ret['total']} 条）</p>")
    ret_cats = sorted(ret.get("categories", {}).keys())
    items = [(c, ret["categories"][c]["rrf_avg"]) for c in ret_cats]
    html.append(svg_hbars("各分类 RRF 平均来源命中", items, ["#4C72B0"] * len(items)))
    items2 = [(c, ret["categories"][c]["minmax_avg"]) for c in ret_cats]
    html.append(svg_hbars("各分类 MinMax 平均来源命中", items2, ["#DD8452"] * len(items2)))
    html.append("</div>")

    # ===== 5. 两两胜率矩阵 =====
    html.append("<h2>5. 来源命中两两胜率矩阵</h2><div class='card'>")
    details = e2e["details"]
    groups = {}
    for d in details:
        groups.setdefault(d["config"], {})[d["id"]] = d
    n = len(cfgs)
    matrix = []
    rows = []
    for ci in cfgs:
        row = []
        rows.append(CFG_CN[ci])
        for cj in cfgs:
            if ci == cj:
                row.append(0.5)
                continue
            ids = set(groups[ci].keys()) & set(groups[cj].keys())
            win = sum(1 for qid in ids if groups[ci][qid]["source_hit_rate"] > groups[cj][qid]["source_hit_rate"])
            tie = sum(1 for qid in ids if groups[ci][qid]["source_hit_rate"] == groups[cj][qid]["source_hit_rate"])
            row.append((win + 0.5 * tie) / len(ids) if ids else 0.5)
        matrix.append(row)
    html.append(svg_heatmap("行配置 vs 列配置（>0.5 表示行更优）", rows,
                            [CFG_CN[c] for c in cfgs], matrix, fmt="{:.2f}"))
    html.append("</div>")

    # ===== 6. 失败清单 =====
    html.append("<h2>6. 各配置失败用例清单</h2>")
    for cfg in cfgs:
        fails = [d for d in details if d["config"] == cfg and not d["passed"]]
        html.append(f"<div class='card'><b>{CFG_CN[cfg]}：失败 {len(fails)} 条</b>")
        if fails:
            html.append("<table><tr><th>ID</th><th>类别</th><th>问题</th>"
                        "<th>来源缺失</th><th>关键词缺失</th></tr>")
            for f in fails[:15]:
                html.append(f"<tr><td>{f['id']}</td><td>{f['category']}</td>"
                            f"<td style='text-align:left'>{f['question']}</td>"
                            f"<td>{','.join(f.get('source_misses', [])) or '-'}</td>"
                            f"<td>{','.join(f.get('keyword_misses', [])) or '-'}</td></tr>")
            html.append("</table>")
            if len(fails) > 15:
                html.append(f"<p style='color:#666'>… 其余 {len(fails)-15} 条见明细 JSON</p>")
        html.append("</div>")

    html.append("</body></html>")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print(f"HTML 报告已生成: {OUT_PATH}")


if __name__ == "__main__":
    main()
