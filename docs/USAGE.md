# docs/USAGE.md · industry-report-update-skill 使用说明

> 给"已经会用基础 Agent、但第一次接触本 Skill"的人看的完整 SOP。
> 如果你只是想跑一次：直接看 [`5 分钟上手`](#5-分钟上手)。
> 如果你想做扩展（加门禁 / 加行业包 / 加端点）：看 [`docs/EXAMPLES.md`](./EXAMPLES.md)。

---

## 5 分钟上手

### 1. 安装（任何 harness / 编辑器通用）

```bash
# Tier 1（Claude Code / Cursor / Gemini / Kiro / Goose / OpenCode / Cline / Roo / Kilo / Factory / Antigravity / Codex CLI）
bash install.sh         # Linux/macOS
pwsh -File install.ps1  # Windows
# 安装器自动链接到 12 个 Tier-1 工具 + 通用 ~/.agents/skills/ 兜底

# Tier 2/3（Windsurf / Trae / Junie / Zed / Augment / Aider / Continue.dev）
# v3.1 未声明兼容，安装路径按 roadmap 补充
```

### 2. 触发

在你的 Agent 对话中说出触发词：

```
帮我把 2026.8 月报更新到 2026.9（旧月报路径 D:/reports/工业机器人2026.8.docx）
/industry-report-update-skill
行业月报更新
```

### 3. 一次性确认（Step 4）

Agent 会向你提 ≤5 个必填问题（如"数据截至日期是否 2026-08-31？""专题是否替换？"），你可以：
- 逐项批注
- 或回复 `一键全采`（用 Agent 的默认值）

### 4. 等 Agent 跑完

首跑 2-4 小时（数据采集 1-2h + 门禁循环 30min + 盲审 30min）。成熟用户月度迭代 1-2h。

### 5. 查看产出

产出在 `<工作区>/<产品名>_产出/`：
- 根：`新月报.docx` + `变更摘要.md`
- `源文件/`：交易所 CSV、溯源.jsonl、通道实测.jsonl
- `门禁报告/`：11 道门禁报告 + 运行日志

---

## 每月 SOP（10 步闭环）

| 步 | 动作 | 命令 | 说明 |
| --- | --- | --- | --- |
| 0 | 数据流审计 | `audit/extract_numbers.py 旧.docx` | 提取旧月报每个数字的「数据源 / 口径 / 时点」 |
| 0.5 | 通道健康度 | `channel_health_check.py --ym <YYYY-MM> --run-id <run-id>` | HTTP 直探 + MCP/agent 由 Agent 实测回写 |
| 1 | 拆解 + 快照 | `snapshot.py snapshot --ym <YYYY-MM> --run-id <run-id>` + `snapshot.py diff --ym <YYYY-MM> --prev-ym <上月>` | 落盘本期快照 + 与上期深 diff（≥3 项暂停确认） |
| 2 | 工具盘点 | `tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl` | 阻断级机检 |
| 3 | 能力汇总 | Agent 内联 | 汇总 ❌/🟡 |
| 4 | 确认清单 | Agent 走 `templates/确认清单模板.md` | 必填 ≤5 条 |
| 5 | 数据采集 + 改写 | `datasources/adapters.py` + `docx_utils.py` + 子 Agent fan-out | 保格式改写 + 断点续跑 |
| 5.5 | 锚点自检 | `audit/anchor_check.py 溯源.jsonl` | dry-run 前置 |
| 6 | 门禁循环 | `run.py 旧.docx 新.docx ...` | 一键 11 道门禁；中断加 `--resume` |
| 7 | 来源归档 | Agent 写 `溯源.jsonl` + `verify_value.py` | 数值回读 |
| 8 | 独立盲审 | 子 Agent 走 `templates/subagent任务模板.md` 第六节 | 失败降级 mainagent 并标注 |
| 9 | 归档 + 度量 | `metrics.py record --ym <YYYY-MM> --run-id <run-id> --gate format_diff=<得分>` | `runs/<run-id>/` 六件套 |
| 9.5 | 工作区镜像 | `archive_to_workspace.py --run-id <run-id> --anchor "<旧月报路径>" --product "<产品名>"` | **强制收尾**，不跑即视为未交付 |

---

## 故障排查（按错误类型）

### 1. 月报数字 ≠ 源文件数字
**原因**：改了源文件但溯源.jsonl 没同步；或源 CSV 列名改了；或源 CSV 重命名了但 path 没改。
**处置**：
- 跑 `audit/anchor_check.py 溯源.jsonl --base-dir 下载资料` 看具体哪条 anchor 失效
- 修正溯源.jsonl 的 source_key/source_field 后跑 `verify_value.py`

### 2. format_diff 相似度 < 95%
**原因**：用了 `cell.text =` 覆写；或新增行没复制同表已有行的格式（gridSpan/vMerge 丢失）。
**处置**：
- 改用 `docx_utils.set_cell_keep` / `fill_table` / `set_para_keep` / `add_row_copy_fmt`
- 跑 `audit/format_diff.py 旧.docx 新.docx --threshold 0.95 --format` 看具体哪些段落/表格的格式签名变了

### 3. 通道健康度持续 ❌
**原因**：交易所改接口；WAF 拦截；MCP 通道 token 失效。
**处置**：
- HTTP 通道：跑 `channel_health_check.py` 看具体哪个 URL 失败
- MCP 通道：Agent 按 `endpoints.yaml` 的 `smoke_hint` 真调一次，回写 `runs/<run-id>/sources/通道实测.jsonl`
- 连续 2 期 ❌：自动触发"续费/改接口"提示

### 4. 工作区归档失败
**原因**：脚本退化为 cwd 并触发 `_inside_base` 守卫。
**处置**：
- 显式传 `--ws "<当前对话工作区路径>"` 或 `--anchor "<输入旧月报原始路径>"`
- 工作区识别优先级：`--ws` > `--anchor` 目录 > `DSH_WORKSPACE` > `DSH_SESSION_JSONL` 解码 > cwd

### 5. 跨月去重命中
**原因**：本期事件包含上月已报过的事件（转载合集）。
**处置**：
- 看 `cross_month_dedup.py` 输出，确认是「转载」还是「新事件」
- 转载：在变更摘要中说明"详见上月报告"并删除
- 新事件：保留但附公告日 vs 转载日差异说明

### 6. subagent 通道连续失败 ≥2 次
**原因**：模型路由问题；或宿主 MCP 配置问题。
**处置**：
- 盲审降级为 mainagent 对抗性自查
- 在《独立审核意见.md》标注"独立性受损"
- 连续 ≥3 次暂停执行，提示人工检查模型路由

### 7. docx 被 Word/WPS 占用
**原因**：用户在 Word 中打开了新月报。
**处置**：
- 脚本输出到 `.tmp.docx`，等用户关闭后覆盖
- 用户关闭 → 手动把 `.tmp.docx` 改名为正常文件名

---

## 命令参考（速查）

```bash
# 工具盘点机检（阻断级）
python scripts/tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl

# 通道自检
python scripts/channel_health_check.py --ym <YYYY-MM> --run-id <run-id>

# 锚点 dry-run
python scripts/audit/anchor_check.py runs/<run-id>/sources/溯源.jsonl \
    --base-dir runs/<run-id>/sources/anchors \
    --out runs/<run-id>/logs/锚点自检.md

# 一键门禁
python scripts/run.py 旧月报.docx 新月报.docx \
    --key-col-name 公司简称 \
    --jsonl 溯源.jsonl \
    --roster-note 变更摘要.md \
    --out-dir runs/<run-id>/logs

# 断点续跑
python scripts/run.py 旧月报.docx 新月报.docx ... --resume

# 工作区镜像（open-source 可移植）
python scripts/archive_to_workspace.py --run-id <run-id> --anchor "<旧月报路径>" --product "<产品名>"

# 行业包
python scripts/pack.py list
python scripts/pack.py activate <新行业>
python scripts/pack.py wizard 旧月报.docx --name <新行业>

# 跨月度量
python scripts/metrics.py record --ym <YYYY-MM> --run-id <run-id> --gate format_diff=<得分> --downgrades <N>
python scripts/metrics.py trend

# 评估（fixtures 正负双向冒烟）
python scripts/run_evals.py --rollout
```

---

## 已知边界（如实声明，不伪装）

1. **format_diff 是 rPr/pPr/gridSpan 签名比对**，不覆盖图表/图片视觉差异；含图表报告需人工复核
2. **verify_value 只能验证「月报=源文件」**，不能验证源文件本身对错
3. **diff_empty / verify_value 的键归一化是启发式**，极端同名异写需人工复核
4. **subagent 通道连续失败 ≥3 次必须暂停**，不允许主 Agent 静默接管后无标注
5. **TOC 页码域**需在 Word/WPS 按 F9 刷新
6. **原生 OOXML 图表无法重算**（双轨制兜底：保留原图 + 图下脚注 + 数据表必更新）