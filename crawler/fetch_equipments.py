"""
批量爬取装备数据：从 equipments.json 读取名单 → 调 API → 处理 → 写入 equipments_data/
"""
import json
import os
import time
from urllib.parse import quote

import requests

from crawler.equipment_processor import process_equipment

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EQUIPMENT_LIST_PATH = os.path.join(BASE_DIR, "data_main", "equipments_data", "equipments.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "data_main", "equipments_data")
API_BASE = "https://api.fz.wiki/api/v1/articles/by-title"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(EQUIPMENT_LIST_PATH, "r", encoding="utf-8") as f:
    equipments = json.load(f)

print(f"共 {len(equipments)} 件装备待爬取\n")

success = 0
failed = []

for i, name in enumerate(equipments, 1):
    title = f"装备/{name}"
    url = f"{API_BASE}?ns=0&title={quote(title, safe='')}&withRevision=1"
    output_path = os.path.join(OUTPUT_DIR, f"{name}.json")

    # 跳过已存在的
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"[{i:02d}/{len(equipments)}] {name} - 已存在，跳过 ({file_size:,} bytes)")
        success += 1
        continue

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "ENDfield_RAG_Crawler/1.0"
        })
        resp.raise_for_status()
        raw = resp.json()

        processed = process_equipment(raw)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(output_path)
        print(f"[{i:02d}/{len(equipments)}] {name} - OK ({file_size:,} bytes)")
        success += 1

    except requests.exceptions.HTTPError as e:
        print(f"[{i:02d}/{len(equipments)}] {name} - HTTP {resp.status_code}")
        failed.append(name)
    except Exception as e:
        print(f"[{i:02d}/{len(equipments)}] {name} - ERROR: {type(e).__name__}: {e}")
        failed.append(name)

    # 礼貌间隔
    time.sleep(0.5)

print(f"\n完成: {success}/{len(equipments)} 成功")
if failed:
    print(f"失败: {failed}")
