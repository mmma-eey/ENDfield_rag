# -*- coding: utf-8 -*-
"""完整流程：B站 MP4 URL → paraformer-v2 转写 → 下载转录 JSON → 提取文本
用法: python scripts/transcribe_mp4_url.py <MP4_URL> <输出txt路径>
"""
import sys
import time
import json
import urllib.request

sys.path.insert(0, r"c:\Users\lenovo\Desktop\ENDfield_rag")
from rag.config import DASHSCOPE_API_KEY
from dashscope.audio.asr import Transcription

MODEL = "paraformer-v2"

MP4_URL = sys.argv[1] if len(sys.argv) > 1 else None
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else r"c:\Users\lenovo\Desktop\ENDfield_rag\scripts\mp4_transcript.txt"


def main():
    if not MP4_URL:
        print("请传入 MP4 URL")
        return
    print("提交转写任务 ...")
    resp = Transcription.call(model=MODEL, file_urls=[MP4_URL], api_key=DASHSCOPE_API_KEY)
    print("call status:", resp.status_code)
    if resp.status_code != 200:
        print("code:", resp.code, "| message:", resp.message)
        return
    task_id = resp.output["task_id"]
    print("task_id:", task_id)

    # 轮询
    transcription_url = None
    for i in range(60):
        time.sleep(10)
        r = Transcription.fetch(task=task_id, api_key=DASHSCOPE_API_KEY)
        st = r.output.get("task_status")
        if i % 3 == 0:
            print(f"  [{i*10}s] {st}")
        if st == "SUCCEEDED":
            # 提取 transcription_url
            def find_url(obj):
                if isinstance(obj, dict):
                    if "transcription_url" in obj:
                        return obj["transcription_url"]
                    for v in obj.values():
                        r = find_url(v)
                        if r:
                            return r
                elif isinstance(obj, list):
                    for v in obj:
                        r = find_url(v)
                        if r:
                            return r
                return None
            transcription_url = find_url(r.output)
            break
        if st == "FAILED":
            print("FAILED:", json.dumps(r.output, ensure_ascii=False)[:600])
            return
    if not transcription_url:
        print("未找到 transcription_url")
        return

    print("\n下载转录 JSON ...")
    req = urllib.request.Request(transcription_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as f:
        data = json.loads(f.read().decode("utf-8"))
    print("JSON 顶层 keys:", list(data.keys()) if isinstance(data, dict) else type(data))

    # 提取文本（paraformer-v2 结果格式：data.transcripts[] / data.sentences[]）
    text_parts = []
    if isinstance(data, dict):
        for t in data.get("transcripts", []):
            text_parts.append(t.get("text", ""))
        for s in data.get("sentences", []):
            text_parts.append(s.get("text", ""))
    full = "\n".join([p for p in text_parts if p])
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(full)
    print(f"转写文本 {len(full)} 字符 → {OUT_PATH}")
    print("\n--- 预览前 600 字 ---\n")
    print(full[:600])


if __name__ == "__main__":
    main()
