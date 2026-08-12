"""对比评测图表 —— 读取评测结果生成可视化报告

输入:
- tests/reports/eval_compare_results.json （端到端 4 组合）
- tests/reports/retrieval_full.json      （检索层 RRF vs MinMax）
输出:
- tests/reports/charts/*.png
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
CHARTS_DIR = os.path.join(REPORTS_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

CFG_ORDER = ["A-rrf", "A-minmax", "B-rrf", "B-minmax"]
CFG_SHORT = {"A-rrf": "A+RRF", "A-minmax": "A+MinMax", "B-rrf": "B+RRF", "B-minmax": "B+MinMax"}
CFG_COLORS = {"A-rrf": "#4C72B0", "A-minmax": "#DD8452", "B-rrf": "#55A868", "B-minmax": "#C44E52"}

METRIC_LABELS = {
    "pass_rate": "通过率",
    "avg_source_hit": "来源命中",
    "avg_keyword_recall": "关键词召回",
    "avg_intent_hit": "意图命中",
}


def load_e2e(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_retrieval(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chart1_overall(e2e: dict, outdir: str):
    """总体得分：4 组合 × 4 指标"""
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]
    metrics = ["pass_rate", "avg_source_hit", "avg_keyword_recall", "avg_intent_hit"]

    x = np.arange(len(metrics))
    width = 0.2
    fig, ax = plt.subplots(figsize=(11, 6))
    for i, cfg in enumerate(cfgs):
        vals = [summary[cfg][m] for m in metrics]
        ax.bar(x + (i - (len(cfgs) - 1) / 2) * width, vals, width,
               label=CFG_SHORT[cfg], color=CFG_COLORS[cfg])
        for xi, v in zip(x + (i - (len(cfgs) - 1) / 2) * width, vals):
            ax.text(xi, v + 0.01, f"{v:.2f}", ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_LABELS[m] for m in metrics])
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("得分")
    ax.set_title("端到端评测：意图方式(A单模型/B双模型) × 融合方式(RRF/MinMax) 总体得分对比")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "1_总体得分对比.png"), dpi=150)
    plt.close(fig)
    print("已生成 1_总体得分对比.png")


def chart2_category_heatmap(e2e: dict, outdir: str):
    """分类别通过率热图：类别 × 4 组合"""
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]

    # 收集类别
    cats = set()
    for cfg in cfgs:
        cats.update(summary[cfg].get("categories", {}).keys())
    cats = sorted(cats)

    matrix = np.zeros((len(cats), len(cfgs)))
    for i, cat in enumerate(cats):
        for j, cfg in enumerate(cfgs):
            st = summary[cfg].get("categories", {}).get(cat)
            if st and st["total"] > 0:
                matrix[i, j] = st["passed"] / st["total"]

    fig, ax = plt.subplots(figsize=(10, max(6, len(cats) * 0.42)))
    im = ax.imshow(matrix, cmap="YlGnBu", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(cfgs)))
    ax.set_xticklabels([CFG_SHORT[c] for c in cfgs])
    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels(cats)
    ax.set_title("分类别通过率热图（颜色越深通过率越高）")
    for i in range(len(cats)):
        for j in range(len(cfgs)):
            v = matrix[i, j]
            ax.text(j, i, f"{v:.0%}" if v > 0 else "-",
                    ha="center", va="center", fontsize=8,
                    color="white" if v > 0.5 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "2_分类通过率热图.png"), dpi=150)
    plt.close(fig)
    print("已生成 2_分类通过率热图.png")


def chart3_time(e2e: dict, outdir: str):
    """平均耗时对比（含 API 调用构成分析）"""
    summary = e2e["summary"]
    cfgs = [c for c in CFG_ORDER if summary.get(c, {}).get("total", 0) > 0]
    times = [summary[c]["avg_time"] for c in cfgs]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar([CFG_SHORT[c] for c in cfgs], times,
                  color=[CFG_COLORS[c] for c in cfgs])
    for b, t in zip(bars, times):
        ax.text(b.get_x() + b.get_width() / 2, t + 0.15, f"{t:.1f}s",
                ha="center", fontsize=10)
    ax.set_ylabel("平均响应耗时 (s)")
    ax.set_title("平均响应耗时对比\n（A=单模型全走Agent多次LLM判断；B=小模型分类+快速路径）")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "3_平均耗时对比.png"), dpi=150)
    plt.close(fig)
    print("已生成 3_平均耗时对比.png")


def chart4_fusion_retrieval(ret: dict, outdir: str):
    """检索层融合方式对比：RRF vs MinMax"""
    cats = sorted(ret.get("categories", {}).keys())
    rrf_vals = [ret["categories"][c]["rrf_avg"] for c in cats]
    mm_vals = [ret["categories"][c]["minmax_avg"] for c in cats]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = np.arange(len(cats))
    width = 0.38
    b1 = ax.bar(x - width / 2, rrf_vals, width, label="RRF 排名融合", color="#4C72B0")
    b2 = ax.bar(x + width / 2, mm_vals, width, label="MinMax 归一化加权", color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=35, ha="right")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Top5 来源命中率")
    ax.set_title(f"检索层召回对比：RRF 平均 {ret['avg_source_hit']['rrf']:.3f} vs "
                 f"MinMax 平均 {ret['avg_source_hit']['minmax']:.3f}"
                 f"（RRF胜{ret['win_count']['rrf']} / MinMax胜{ret['win_count']['minmax']}"
                 f" / 平{ret['win_count']['tie']}，共{ret['total']}条）")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    for xi, (v1, v2) in enumerate(zip(rrf_vals, mm_vals)):
        ax.text(xi - width / 2, v1 + 0.02, f"{v1:.2f}", ha="center", fontsize=7)
        ax.text(xi + width / 2, v2 + 0.02, f"{v2:.2f}", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "4_检索融合方式对比.png"), dpi=150)
    plt.close(fig)
    print("已生成 4_检索融合方式对比.png")


def chart5_win_matrix(e2e: dict, outdir: str):
    """4 组合两两胜率对比：来源命中率（A vs B 意图方式 × RRF vs MinMax 融合方式）"""
    details = e2e["details"]
    groups = {}
    for d in details:
        groups.setdefault(d["config"], {})[d["id"]] = d

    cfgs = [c for c in CFG_ORDER if c in groups]
    n = len(cfgs)
    matrix = np.zeros((n, n))
    for i, ci in enumerate(cfgs):
        for j, cj in enumerate(cfgs):
            if i == j:
                continue
            ids = set(groups[ci].keys()) & set(groups[cj].keys())
            win = sum(1 for qid in ids
                      if groups[ci][qid]["source_hit_rate"] > groups[cj][qid]["source_hit_rate"])
            tie = sum(1 for qid in ids
                      if groups[ci][qid]["source_hit_rate"] == groups[cj][qid]["source_hit_rate"])
            matrix[i, j] = (win + 0.5 * tie) / len(ids) if ids else 0.5

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels([CFG_SHORT[c] for c in cfgs])
    ax.set_yticklabels([CFG_SHORT[c] for c in cfgs])
    ax.set_title("来源命中率两两胜率矩阵\n（行配置 vs 列配置，>0.5 表示行更优）")
    for i in range(n):
        for j in range(n):
            if i != j:
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=10)
    fig.colorbar(im, ax=ax, shrink=0.85)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "5_两两胜率矩阵.png"), dpi=150)
    plt.close(fig)
    print("已生成 5_两两胜率矩阵.png")


def main():
    e2e_path = os.path.join(REPORTS_DIR, "eval_compare_results.json")
    ret_path = os.path.join(REPORTS_DIR, "retrieval_full.json")

    if not os.path.exists(e2e_path):
        print(f"未找到端到端结果 {e2e_path}，跳过图表 1/2/3/5")
    else:
        e2e = load_e2e(e2e_path)
        chart1_overall(e2e, CHARTS_DIR)
        chart2_category_heatmap(e2e, CHARTS_DIR)
        chart3_time(e2e, CHARTS_DIR)
        chart5_win_matrix(e2e, CHARTS_DIR)

    if os.path.exists(ret_path):
        ret = load_retrieval(ret_path)
        chart4_fusion_retrieval(ret, CHARTS_DIR)
    else:
        print(f"未找到检索层结果 {ret_path}，跳过图表 4")

    print(f"\n图表已输出至: {CHARTS_DIR}")


if __name__ == "__main__":
    main()
