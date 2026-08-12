# -*- coding: utf-8 -*-
"""SnapAny B站视频解析 —— 复刻前端签名算法，发送请求返回视频直链

用法:
  python scripts/snapany_extract.py <B站视频链接> [G-Session-ID]

说明:
  - 匿名接口按 IP 限流（free_limit_exceeded），登录后带 G-Session-ID 可绕开
  - 会话 ID 是登录后 cookie 里的 token，可在浏览器 DevTools 查看，也可用
    环境变量 SNAPANY_SESSION_ID 提供
"""
import os
import sys
import time
import json
import hashlib
import hmac
import requests

API_URL = "https://api.snapany.com/v1/extract/post"
SIGN_KEY = "a5wU-SVyy5gXIyMbPQIfIz7UP7rCBp76U8Z8i-FtDMU"  # 前端 JS 硬编码
LOCALE = "zh"
TIMEZONE = "Asia/Shanghai"


def sign(url, locale, ts):
    """G-Footer = hex( HMAC-SHA256(key, url + locale + timestamp) )"""
    payload = f"{url}{locale}{ts}"
    return hmac.new(SIGN_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def extract(bili_url, session_id=None):
    session_id = session_id or os.getenv("SNAPANY_SESSION_ID")
    ts = int(time.time() * 1000)
    headers = {
        "Content-Type": "application/json",
        "Accept-Language": LOCALE,
        "G-Timestamp": str(ts),
        # 签名输入 = 用户链接 + locale + 时间戳（不是 API 地址）
        "G-Footer": sign(bili_url, LOCALE, ts),
        "G-Timezone": TIMEZONE,
        "X-No-Error-Toast": "1",
        "Origin": "https://snapany.com",
        "Referer": "https://snapany.com/zh/bilibili",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    }
    if session_id:
        headers["G-Session-ID"] = session_id
    resp = requests.post(API_URL, json={"link": bili_url}, headers=headers, timeout=60)
    print("HTTP", resp.status_code, "| 带会话:", bool(session_id))
    data = resp.json()
    if data.get("code") not in (None, 0, 200):
        print("API 错误:", json.dumps(data, ensure_ascii=False)[:500])
        if data.get("code") == "free_limit_exceeded":
            print("→ 免费接口限流中，登录后带 G-Session-ID 可绕开")
        return None
    d = data.get("data") or data  # 兼容 {data:{...}} 与顶层 {...} 两种结构
    if not d.get("medias"):
        print("响应结构:", json.dumps(data, ensure_ascii=False)[:800])
        return d
    print("标题:", d.get("text"))
    for m in d.get("medias", []):
        print("\n[medias]", m.get("media_type"))
        print("  合成 mp4 直链:", m.get("resource_url"))
        print("  封面:", m.get("preview_url"))
        print("  下载需带头:", json.dumps(m.get("headers"), ensure_ascii=False))
        for v in m.get("variants", []):
            print(f"    {v.get('quality_label')}: video={v.get('video_url')} ")
            print(f"                          audio={v.get('audio_url')}")
    return d


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.bilibili.com/video/BV1ydEv64Eez"
    sess = sys.argv[2] if len(sys.argv) > 2 else None
    extract(url, sess)
