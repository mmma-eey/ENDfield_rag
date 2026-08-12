# 问题与解决方案记录（Troubleshooting）

> 本文件记录项目开发过程中遇到并解决的问题，供后续复现/排查参考。
> 更新日期：2026-08-07

---

## 1. LLM 空响应问题（关键）

- **现象**：DeepSeek 生成 API 偶发返回空 `content`（generator 偶发空回答）；术语纠偏脚本 `term_correction.py` 的 LLM 连续 3 次返回空 content。
- **根因**：`.env` 中 `LLM_MODEL=deepseek-v4-flash` 是**推理模型**，输出全部放在 `reasoning_content`，`content` 恒为空（`finish_reason=length`）。
- **解决**：改用 `deepseek-chat`（v4-flash 的非推理别名）后正常。
- **附带缓解**：`rag/generator.py` 对空回答加最多 2 次重试，缓解 API 间歇性空响应。
- **教训**：DeepSeek 有多个模型名指向同一模型，推理模式与普通模式的 `content` 行为不同，排查空响应先确认模型别名。

---

## 2. 检索召回不足（装备 10 题全挂 → 全部通过）

- **现象**：加权融合（BM25 0.3 + Cosine 0.7）下 10 个装备题全挂（0/10），装备切片召不回。
- **解决**：混合检索改为 **RRF（Reciprocal Rank Fusion）**：
  `score = 1/(60+rank_bm25) + 1/(60+rank_vector)`（按排名融合，不按分数），`RRF_K=60`。
- **效果**：评测 **27/40 → 39/40**，装备 10 题全部通过。
- **配套修改**：
  - 装备切片带装备名标签（`equipment_profile/description/flavor/stat/suit/unlock` 六类）
  - `bm25_index.py` 的 clean_text 正则修复：`{[a-zA-Z_:0-9]+}` → `{[^}]+}`（清除 `{ultimate_gain_up:0.0%}` 残留）
  - `sql_fallback.py` 新增装备分支，命中装备名即补结构化数据
  - 生成前统一 clean_text 拼接

---

## 3. 列表类查询失败（Q24）

- **现象**："有哪些终末地工业的干员"类查询失败。
- **原因**：无意图路由 + 无列表聚合。
- **状态**：排期 Phase 2（P1：查询预处理 + 简单意图路由；P1：列表类查询聚合）。

---

## 4. 装备推荐推理失败（庄方宜四件套）

- **结论**：根因是**检索而不是推理**——对照实验证明给足壤流套数据后普通模式都能答对，当前工具检索不到壤流套才失败。
- **规划**：方案B（全 Agent tool calling 编排）+ DeepSeek 思考模式（`extra_body={"thinking":{"type":"enabled"}}` + `reasoning_effort`，注意：需回传 `reasoning_content`、不支持 `temperature`、长推理链耗 token）。

---

## 5. B站视频内容提取（字幕/音频/转写）

- **B站字幕 API**：需登录，且部分视频**无字幕轨道**（yt-dlp 双重确认）→ 纯字幕方案不可行。
- **阿里听悟（网页版）**：免费有分段，但**游戏术语错误率高于 paraformer-v2**。
- **方案定型**：**MP4 签名直链 + DashScope paraformer-v2 异步转写**（零本地下载，23min 约 4 分钟，约 0.3 元/视频）。

---

## 6. DashScope ASR 系列坑

| 问题 | 原因 | 解决 |
|------|------|------|
| `OSS oss://` URL 服务端读不到（SERVER_ERROR / FILE_DOWNLOAD_FAILED） | `OssUtils.upload()` 返回私有 URL（ACL=private） | 用**公网带签名 CDN 直链**绕过防盗链 |
| `.m4s` 格式不被识别 | DashScope 解码器不认 fMP4 分片 | ffmpeg 转标准 wav/mp4 |
| paraformer-v1 模型名报错 | SDK 只有 `paraformer-v1/mtl/8k` 等 | 用 `paraformer-v2` 字符串（之前失败是 URL 问题） |
| base64 data URL 被拒 | 请求体过大 | 改用直链 |
| tmpfiles.org 直链失败 | 国内网络连不上 | 弃用 |
| 0 秒接收 | 签名直链可正常接收 | 确认链路 |

---

## 7. SnapAny B站视频解析（scripts/snapany_extract.py）

- **接口**：`POST https://api.snapany.com/v1/extract/post`，body `{"link": "<B站链接>"}`。
- **签名**（前端 JS 硬编码密钥 `a5wU-SVyy5gXIyMbPQIfIz7UP7rCBp76U8Z8i-FtDMU`）：
  `G-Footer = hex( HMAC-SHA256( link + locale + timestamp ) )`，`G-Timestamp = Date.now()` 毫秒。
- **匿名限流**：`free_limit_exceeded`（HTTP 401，按 IP）→ **登录后带 `G-Session-ID` 头**（= cookie 里的 `token`）即可绕开；会话跨域 fetch 不带 cookie，全靠该头传递。
- **响应结构**（顶层，注意不是 data.data）：`{text, post_url, medias:[{resource_url, preview_url, headers, variants, formats}]}`。
  - `resource_url` = 合成 1080p MP4 直链（即页面点【下载视频】按钮跳转的 URL）
  - `variants` = 1080p/720p/480p/360p 音视频分离 m4s 流，下载需带 `headers`（iPhone UA + `Referer: https://www.bilibili.com/`）
- **有效期**：直链带 `deadline` 签名，约 **2 小时过期**，重新解析即可。
- **用法**：`python scripts/snapany_extract.py <链接> <G-Session-ID>`（或环境变量 `SNAPANY_SESSION_ID`）。

---

## 8. 术语纠偏（scripts/term_correction.py）

- **流程**：
  1. `collect_terms()` 从 data_wiki 收集权威术语（干员30 + 技能/天赋174 + 武器76 + 敌人83 + 装备243 + 机制词 ≈ 527 个）
  2. LLM（deepseek-chat，json_object 模式）生成 `{错词: 正确词}` 映射
  3. **后置过滤防幻觉**：剔单字映射 + 目标必须是权威术语/白名单词（拦截"清波→轻波"类编造）
  4. **硬规则兜底**：`KNOWN_ALIASES` 固化已确认高频错词（如 轻波→清波、凌雨/淋雨/灵雨→囹圄）
  5. 批量替换（长词优先）+ 输出 `_corrected.txt` 与 `.mapping.json`（人工审计）
- **效果**：诀视频 62 处替换（赛西→赛希、辅蚀→腐蚀、自觉→智觉、凌雨→囹圄…）；卡缪视频 63 处替换（战绩→战技、洛曦→洛茜、卡密欧→卡缪…）。
- **残留问题**：LLM 有随机性，每次跑映射略有差异，偶有漏纠/误判 → 依赖 `.mapping.json` 审计 + 固化高频词。

---

## 9. 环境与工具坑

- **conda `run -c` 不支持多行命令**（`NotImplementedError`）→ 写脚本文件执行。
- **Python 环境分工**：爬虫/数据库用 `data_process` (3.12)，RAG 用 `llm_dev` (3.11)，不要混用 pip。

---

## 10. 数据源选择（已确认）

- **fz.wiki 最优**：解包数据、更新快、公开 API `https://api.fz.wiki/api/v1/articles/by-title?ns=0&title={URL编码}&withRevision=1`（免认证）。
- 森空岛官方 Wiki：反调试、质量差（弃）；GameKee：停更（弃）；warfarin.wiki：robots 限制 GPTBot/ClaudeBot + `ai-train=no`（弃）。

---

## 11. 待办（未修复/排期）

| 优先级 | 项目 |
|--------|------|
| P0 | `generator.py` `chat_with_history()` 引用未定义 `SYSTEM_PROMPT`（应为 `GENERATION_SYSTEM_PROMPT`），LLM 调用无超时 |
| P1 | 查询预处理 + 意图路由（列表类聚合解决 Q24） |
| P1 | 意图路由加 guide 分支（攻略库与官方数据 RRF 融合按 source 加权） |
| P2 | 材料/基建/配方数据、多轮对话记忆 |
| P3 | 地图/任务/剧情数据 |
