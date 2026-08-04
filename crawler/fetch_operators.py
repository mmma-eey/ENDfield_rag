"""
批量爬取干员数据：从 operator.json 读取名单 → 调 API → 处理 → 写入 operator_data/
"""
import json
import os
import time
from urllib.parse import quote

import requests

from crawler.processor import process_operator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPERATOR_LIST_PATH = os.path.join(BASE_DIR, "operator.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "data_main", "operator_data")
API_BASE = "https://api.fz.wiki/api/v1/articles/by-title"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(OPERATOR_LIST_PATH, "r", encoding="utf-8") as f:
    operators = json.load(f)

print(f"共 {len(operators)} 个干员待爬取\n")

success = 0
failed = []

for i, name in enumerate(operators, 1):
    title = f"干员/{name}"
    url = f"{API_BASE}?ns=0&title={quote(title, safe='')}&withRevision=1"
    output_path = os.path.join(OUTPUT_DIR, f"{name}.json")

    # 跳过已存在的
    if os.path.exists(output_path):
        print(f"[{i:02d}/{len(operators)}] {name} - 已存在，跳过")
        success += 1
        continue

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "ENDfield_RAG_Crawler/1.0"
        })
        resp.raise_for_status()
        raw = resp.json()

        processed = process_operator(raw)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(output_path)
        print(f"[{i:02d}/{len(operators)}] {name} - OK ({file_size:,} bytes)")
        success += 1

    except requests.exceptions.HTTPError as e:
        print(f"[{i:02d}/{len(operators)}] {name} - HTTP {resp.status_code}")
        failed.append(name)
    except Exception as e:
        print(f"[{i:02d}/{len(operators)}] {name} - ERROR: {type(e).__name__}: {e}")
        failed.append(name)

    # 礼貌间隔
    time.sleep(0.5)

print(f"\n完成: {success}/{len(operators)} 成功")
if failed:
    print(f"失败: {failed}")
