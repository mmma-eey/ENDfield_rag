"""更新数据库：管理员·男/女 -> 男/女管理员 (文件已改名, 只更新 DB)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data_main", "operator_data")

from db.database import SessionLocal, init_db
from db.models import Operator

init_db()
session = SessionLocal()

for new_file in ["女管理员.json", "男管理员.json"]:
    new_path = os.path.join(DATA_DIR, new_file)
    with open(new_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    article_id = data["meta"]["article_id"]
    new_name = data["basic"]["name"]
    new_desc = data["basic"].get("description")
    op = session.query(Operator).filter(Operator.article_id == article_id).first()
    if op:
        op.name = new_name
        op.description = new_desc
        print(f"[数据库] {op.name} 已更新 (article_id={article_id})")
    else:
        print(f"[数据库] WARN: article_id={article_id} 未找到记录")

session.commit()
session.close()
print("\n完成")
