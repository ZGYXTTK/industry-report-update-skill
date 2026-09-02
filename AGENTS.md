# industry-report-update-skill · AGENTS entry

> 给 Codex CLI / Continue.dev / Zed / Augment / Aider 等优先读取 AGENTS.md 的工具使用。
> 完整指令见 [`SKILL.md`](./SKILL.md)。

## 用途

以用户提供的**上一期行业月报 docx** 为模板，端到端生成**最新一期月报**。通用引擎 + 行业包机制，换行业只换 `packs/<行业>/`。

## 触发词

```
行业月报更新 / 月报更新 / 生成最新月报 / 更新月报 / generate monthly report
```

不适用（拒绝执行）：
- 周报 / 季报 / 年报
- 双公司专题对比（走姊妹 Skill `专题研究.skill/`）
- 无上期模板从零写
- 只给主题不给旧报路径

## 必填输入

- 上一期月报 docx 文件路径（Agent 自动以此为锚点定位当前对话工作区）

## 可选输入

- 数据截至日期（默认当月最后一天）
- 专题研究要求（默认不改）
- 来源标注粒度（默认章节+具体来源）
- 行业包名（默认 `_default` 兜底）

## 主要输出

- 新月报 .docx（结构保真 ≥95%）
- `runs/<run-id>/`：变更摘要、溯源.jsonl、来源记录、下载资料、11 道门禁报告、运行日志
- 工作区归档：`<工作区>/<产品名>_产出/`（Step 9.5 强制收尾）

## 安装与执行

```bash
# 安装（Tier 1：Claude Code / Cursor / Gemini / Kiro / Goose / OpenCode / Cline / Roo / Kilo / Factory / Antigravity / Codex CLI）
bash install.sh
pwsh -File install.ps1

# 一键执行
python scripts/run.py 旧月报.docx 新月报.docx \
    --key-col-name 公司简称 \
    --jsonl 溯源.jsonl \
    --roster-note 变更摘要.md \
    --out-dir runs/<run-id>/logs

# 断点续跑
python scripts/run.py 旧月报.docx 新月报.docx ... --resume

# 评估（fixtures 正负双向冒烟）
python scripts/run_evals.py --rollout

# 新建行业包（反推骨架）
python scripts/pack.py wizard 旧月报.docx --name medtech
python scripts/pack.py activate medtech
```

## 三条铁律

1. **数据流审计**：旧月报 = 结构模板 + 口径参考，**绝不沿用数值**。时点型按月重采完整枚举。
2. **格式保真**：就地改写（`docx_utils.set_cell_keep` / `set_para_keep`），**禁止** `cell.text = value` / `Document()+add_paragraph+add_table` 从零重建。`format_diff` ≥95% 是硬门槛。
3. **工具盘点先于标 ✅**：所有 MCP / HTTP 通道必须先 smoke test 实测一次，未实测只能标 🟡。

## 门禁速查（11 道）

| # | 门禁 | 命令 |
| --- | --- | --- |
| 1 | 数字提取 | `extract_numbers.py 旧.docx` |
| 2 | 配置校验 | `config_check.py` |
| 3 | 空值 diff | `diff_empty.py 旧.docx 新.docx --key-col-name <键列>` |
| 4 | 一致性 | `consistency_check.py 新.docx` |
| 5 | 交叉一致性 | `cross_consistency_check.py 新.docx` |
| 6 | 合理性 | `reasonableness_check.py 旧.docx 新.docx --roster-note 变更摘要.md` |
| 7 | 格式对比 | `format_diff.py 旧.docx 新.docx --threshold 0.95` |
| 8 | 数值回读 | `verify_value.py 溯源.jsonl` |
| 9 | 溯源反查 | `traceability_check.py 溯源.jsonl --min-coverage 0.9 --require-cross-check` |
| 10 | 锚点自检（dry-run） | `audit/anchor_check.py 溯源.jsonl` |
| 11 | 跨月去重 | `cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv` |

## Gotchas（必须看）

完整 20 条避坑手册见 [`references/gotchas.md`](./references/gotchas.md)。其中 5 条高危：
- **禁止** `cell.text = value` / `p.text = value` 覆写 → 用 `docx_utils.set_cell_keep / set_para_keep`
- **必须用 v2 函数族**：`set_cell_keep`、`fill_table`、`strip_vmerge`、`set_para_keep`、`add_row_copy_fmt`、`set_para_segments_keep_fmt`
- 删除残句用**包含匹配**（`in`），**不用前缀匹配**（`startswith`）
- 申万指数码禁用 `wind_stock_data.get_stock_kline`（801742.SL 被误解析为个股）
- 工作区归档脚本 `archive_to_workspace.py` 不跑 = 未交付（即使门禁全过）

## 依赖

- Python 3.10+
- `python-docx>=0.8.11` · `requests>=2.31` · `PyYAML`（无则 yaml_lite mini 回退）
- 可选：`pandas` `xlrd==1.2.0` `openpyxl>=3.1`
- MCP 数据通道按需：`mx-ds-mcp` / `hexin-ifind-ds` / `qcc` / `itjuzi` / `qcc-document` / `qcc-tender` / `tavily-search`

## 文档导航

| 文档 | 用途 |
| --- | --- |
| `SKILL.md` | 主入口（铁律 + 10 步闭环 + 11 道门禁 + 纪律分级） |
| `README.md` | 项目概览 |
| `使用说明.md` | 中文使用说明（触发方式 + 输入输出 + 10 步详解） |
| `修改示例.md` | 通用反推案例（脱敏通用版） |
| `docs/USAGE.md` | 详细使用 SOP（每月流程 + 故障排查 + 命令参考） |
| `docs/EXAMPLES.md` | 8 个扩展示例 |
| `references/discipline.md` | P0/P1/P2 三级纪律全文 |
| `references/gotchas.md` | 20 条避坑手册 |
| `discovery.json` | 决策契约（marketplace 检索依据） |
| `evals/industry-report-update.eval.md` | 评估 spec（门禁断言 + 评分） |
| `packs/README.md` | 行业包机制说明 |