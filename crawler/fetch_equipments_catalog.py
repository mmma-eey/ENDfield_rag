"""
爬取装备目录页（title=装备）→ 生成 equipments.json（名字列表，供 fetch_equipments.py 使用）
同时保存完整目录信息 equipments_catalog.json（含部位/星级/装备组/附加属性）
"""
import json
import os
from urllib.parse import quote

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "data_main", "equipments_data")
API_BASE = "https://api.fz.wiki/api/v1/articles/by-title"
CATALOG_TITLE = "装备"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_catalog():
    url = f"{API_BASE}?ns=0&title={quote(CATALOG_TITLE)}&withRevision=1"
    resp = requests.get(url, timeout=30, headers={"User-Agent": "ENDfield_RAG_Crawler/1.0"})
    resp.raise_for_status()
    raw = resp.json()

    article = raw["article"]
    content = raw["revision"]["contentJson"]["content"]

    # 目录在第一个 wikiTemplateInstance 的 attrs.roster 中
    roster = None
    for blk in content:
        attrs = blk.get("attrs") or {}
        if attrs.get("roster"):
            roster = attrs["roster"]
            break
    if roster is None:
        raise RuntimeError("目录页未找到 roster 组件")

    entries = roster["entries"]
    print(f"目录页: {article['title']} | 共 {len(entries)} 件装备")

    # 完整目录信息
    catalog = {
        "meta": {
            "source": "fz.wiki",
            "article_id": article["id"],
            "title": article["title"],
            "updated_at": article["updatedAt"],
        },
        "attr_groups": roster.get("attrGroups", []),
        "attr_order": roster.get("attrOrder", []),
        "entries": entries,
    }
    catalog_path = os.path.join(OUTPUT_DIR, "equipments_catalog.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"完整目录已保存: {catalog_path}")

    # 名字列表（供批量精爬使用）
    names = [e["name"] for e in entries]
    names_path = os.path.join(OUTPUT_DIR, "equipments.json")
    with open(names_path, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    print(f"名单已保存: {names_path} ({len(names)} 个)")


if __name__ == "__main__":
    fetch_catalog()
