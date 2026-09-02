# industry-report-update-skill · 行业月报更新（开源版 · Apache-2.0）

> 以**上一期行业月报 docx** 为模板，端到端生成**最新一期月报**的可复用 Agent Skill。
> **通用引擎 + 行业包机制**——主流程适用任何行业；赛道口径封装在 `packs/<行业名>/`。

---

## 它解决什么问题

| 月报更新的痛点 | 本 Skill 的对策 |
| --- | --- |
| 手工抄数易错易漏 | 每个数字强制溯源到源 CSV，脚本逐个回读核对（含币种/单位折算） |
| 汇总数字与表格对不上 | 交叉一致性门禁：正文断言 vs 表格行数 / 分组求和 / 加总等式 |
| 上期事件本月重复报 | 跨月去重门禁：「主体+轮次」指纹跨期比对 + 无名主体拦截 |
| 格式改坏（丢图表/丢列/字体错乱） | 就地改写（复制底稿逐 run 克隆格式），禁止从零重建 |
| 质检对象 ≠ 交付对象 | 全门禁 SHA-256 哈希绑定（脚本验证对象必须 = 交付 docx） |
| 拿不到数据就编 | 铁律：标「本期无法获取 / —」，禁止编造与模糊占位 |

一句话：**旧月报只是格式模具，一个旧数字都不沿用**。

---

## 5 分钟上手

```bash
# 1. 依赖（注意 xlrd 必须 1.2.0，读上交所老式 .xls）
pip install -r requirements.txt

# 2. 安装到本机工具（12 个 Tier-1 工具 + ~/.agents/skills 通用兜底）
pwsh -File install.ps1   # Windows
bash install.sh          # Linux/macOS

# 3. 冒烟验证（fixtures 正负双向）
python evals/cases/make_fixtures.py && python scripts/run_evals.py --rollout

# 4. 首跑
python scripts/run.py ./上月.docx --ym 2026-09 --ws "D:\工作区"
```

详细 SOP 见 [`docs/USAGE.md`](./docs/USAGE.md)；扩展场景见 [`docs/EXAMPLES.md`](./docs/EXAMPLES.md)。

---

## 三条铁律（Skill 灵魂）

1. **数据流审计**：旧月报 = 结构模板 + 口径参考，**绝不沿用数值**。时点型按月重采完整枚举。
2. **格式保真**：就地改写（`docx_utils.set_para_text_keep_fmt`），**禁止** `cell.text = value` / `Document()+add_paragraph+add_table` 从零重建。`format_diff` ≥ 95% 是硬门槛。
3. **工具盘点先于标 ✅**：所有 MCP / HTTP 通道必须先 smoke test 实测一次，未实测只能标 🟡。

---

## 11 道门禁一览

| # | 门禁 | 一句话 | 命令 |
| --- | --- | --- | --- |
| 1 | 数字提取 | 旧报数字登记造册 | `scripts/audit/extract_numbers.py 旧.docx` |
| 2 | 配置校验 | 配置 schema 强校验 + 通道名合法性 | `scripts/audit/config_check.py` |
| 3 | 空值 diff | 上期有值本期不能空（可降软） | `scripts/audit/diff_empty.py 旧.docx 新.docx --key-col-name <键列>` |
| 4 | 一致性 | 合计 = 分项和 | `scripts/audit/consistency_check.py 新.docx` |
| 5 | 交叉一致性 | 正文断言 vs 表格行数 / 分组求和 / 加总等式 | `scripts/audit/cross_consistency_check.py 新.docx` |
| 6 | 合理性 | 环比 ±50% / 增删标的必须有交代（可降软） | `scripts/audit/reasonableness_check.py 旧.docx 新.docx --roster-note 变更摘要.md` |
| 7 | 格式对比 | 相似度 ≥ 95% + 结构差清单 + 自比检测（可降软） | `scripts/audit/format_diff.py 旧.docx 新.docx --threshold 0.95` |
| 8 | 数值回读 | 溯源值 = 源 CSV **且真的写在交付 docx 里** | `scripts/audit/verify_value.py 溯源.jsonl --base-dir 下载资料` |
| 9 | 溯源反查 | 覆盖率 ≥ 90% + 逐条交叉验证 | `scripts/audit/traceability_check.py 溯源.jsonl --min-coverage 0.9 --require-cross-check` |
| 10 | 锚点自检 | 锚点 dry-run（verify_value 前置） | `scripts/audit/anchor_check.py 溯源.jsonl` |
| 11 | 跨月去重 | 「主体+轮次」指纹跨期比对；金额矛盾/无名主体 = 硬伤 | `scripts/audit/cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv` |

全门禁默认硬失败阻断；用 `--soft-gates` 显式降级（记 ⚠️ 转盲审，绝不静默放行）。

---

## 安装

### 方式 1 · Claude Code marketplace

```bash
/plugin marketplace add <OWNER>/industry-report-update-skill
```

### 方式 2 · 安装器（推荐）

```bash
bash install.sh            # Linux/macOS（symlink）
pwsh -File install.ps1     # Windows（Junction，非管理员可用）
```

### 方式 3 · git clone 到工具原生路径

```bash
git clone https://github.com/<OWNER>/industry-report-update-skill.git <目标路径>/industry-report-update-skill
```

| 工具 | 路径 |
| --- | --- |
| Claude Code | `~/.claude/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| Cursor | `%APPDATA%\Cursor\User\skills\`（Win）/ `~/.config/Cursor/User/skills/` |
| Codex CLI | `~/.config/Codex/skills/` |
| Goose | `~/.config/goose/skills/` |
| Roo Code / Cline / Kilo / Kiro / Factory / Antigravity | `~/.config/<工具>/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| 通用兜底（任何读取 AGENTS.md 的工具） | `~/.agents/skills/` |

Tier 2/3（Windsurf / Trae / Junie / Zed / Augment / Aider / Continue.dev）：v1.0.0 未声明兼容，安装路径按 roadmap 补充。

---

## 目录结构

```
industry-report-update-skill/
├── SKILL.md                # 主入口（触发词 + 铁律 + 流程 + Gotchas）
├── AGENTS.md               # Codex CLI 等优先读取的精简入口
├── README.md               # 本文件
├── LICENSE                 # Apache-2.0
├── CHANGELOG.md            # 版本变更记录
├── discovery.json          # 决策契约（marketplace 检索依据）
├── docs/
│   ├── USAGE.md            # 详细使用 SOP（每月流程 + 故障排查 + 命令参考）
│   └── EXAMPLES.md         # 8 个扩展示例（新增行业包 / 采集项 / 门禁 / 端点）
├── config/
│   └── _default/           # 兜底行业包配置（5 YAML + endpoints + tool_registry + agent_health + 渠道状态）
├── packs/
│   ├── README.md           # 行业包机制说明
│   └── _default/           # 兜底行业包骨架（5 YAML + RULES.md + README.md）
├── scripts/
│   ├── run.py              # 11 道门禁一键 + --resume 断点续跑
│   ├── run_evals.py        # 评估器（fixtures 正负双向冒烟）
│   ├── build_report.py     # 声明式构建引擎
│   ├── docx_build.py       # 原语库
│   ├── docx_utils.py       # 保真改写工具库
│   ├── yaml_lite.py        # 统一 YAML 加载器（PyYAML + mini 回退）
│   ├── pack.py             # 行业包管理（list/activate/wizard）
│   ├── snapshot.py         # 口径快照 + 深 diff
│   ├── manifest.py         # 运行契约（runs/<run-id>/manifest.json）
│   ├── metrics.py          # 跨月度量
│   ├── channel_health_check.py  # 通道健康度自检
│   ├── channel_pick.py     # 通道排序（P1
│   ├── workspace.py        # 工作区探测
│   ├── archive_to_workspace.py  # 工作区归档（P0-11 强制收尾）
│   ├── tool_inventory.py   # 工具盘点机检（阻断级）
│   ├── checkpoint.py       # 采集项
│   ├── conflict_classify.py  # 冲突分级
│   ├── audit/              # 11 道门禁（extract_numbers/config_check/diff_empty/...）
│   ├── datasources/adapters.py  # 数据源适配器
│   └── tests/test_p0f_fixes.py  # 回归测试
├── templates/              # 确认清单 / 变更摘要 / 溯源 schema / 子 Agent 任务
├── references/
│   ├── discipline.md       # P0/P1/P2 三级纪律全文
│   └── gotchas.md          # 20 条避坑手册
├── 专题研究.skill/          # 专题对比独立子 Skill（manifest 契约对接）
├── evals/                  # 评估（fixtures 正负双向 + run_evals 一键）
└── .claude-plugin/
    └── plugin.json          # Claude Code marketplace 注册
```

---

## 触发词

```
行业月报更新 / 月报更新 / 生成最新月报 / 更新月报 / generate monthly report
```

**不适用**（`discovery.json` 声明拒绝）：
- 周报 / 季报 / 年报
- 双公司专题对比（走姊妹 Skill `专题研究.skill/`）
- 无上期模板从零写
- 只给主题不给旧报路径

---

## 兼容性（v1.0.0 实际声明）

- **Tier 1**（原生 SKILL.md，12 工具）：Claude Code / Cursor / Gemini / Kiro / Goose / OpenCode / Cline / Roo / Kilo / Factory / Antigravity / Codex CLI
- **Tier 2/3**：未声明兼容（roadmap 补充中）
- **运行环境**：Python 3.10+；MCP 数据通道（iFinD / Wind / 企查查 / IT 桔子 / Tavily 等）需宿主环境配置，缺失时按降级链降级并如实标注

---

## 依赖

```bash
pip install -r requirements.txt
```

详见 `requirements.txt`：python-docx / requests / jsonschema / pandas / xlrd / openpyxl。

---

## 文档导航

| 文档 | 用途 |
| --- | --- |
| `SKILL.md` | 主入口（铁律 + 10 步闭环 + 9 道门禁 + 纪律分级） |
| `AGENTS.md` | 精简入口（Codex CLI 等优先读取） |
| `README.md` | 项目概览（本文件） |
| `使用说明.md` | 中文使用说明（触发方式 + 输入输出 + 9 步详解） |
| `修改示例.md` | 实战反推案例（脱敏通用版） |
| `docs/USAGE.md` | 详细 SOP（每月流程 + 故障排查 + 命令参考） |
| `docs/EXAMPLES.md` | 8 个扩展示例 |
| `references/discipline.md` | P0/P1/P2 三级纪律全文 |
| `references/gotchas.md` | 20 条避坑手册 |
| `discovery.json` | 决策契约 |
| `evals/industry-report-update.eval.md` | 评估 spec |
| `CHANGELOG.md` | 版本变更记录 |

---

## 与姊妹项目的关系

本 Skill 是 `industry-report-update` v2.1 母版的完整公开版（Apache-2.0）。
姊妹项目：
- `gfreport-renew-skill` v0.2.0（https://github.com/ZGYXTTK/GFreport-renew-skill）—— JSON 配置 + jsonschema 强校验 + 11 道门禁（含哈希绑定交付物指纹）的轻量派生版

两者互为补充：
- 本 Skill（`industry-report-update-skill`）：YAML 配置 + PyYAML/mini 双回退 + 通用引擎 + 行业包机制
- 姊妹项目（`gfreport-renew-skill`）：JSON 配置 + 强 schema + 哈希绑定

---

## 质量与验证状态（v1.0.0 发布基线）

| 评估项 | 状态 |
| --- | --- |
| `validate.py`（agent-skill-creator 规范校验） | 待首次基线跑 |
| `security_scan.py`（agent-skill-creator 安全扫描） | 待首次基线跑 |
| `run_evals.py --rollout`（fixtures 正负双向） | 待首次基线跑 |

---

## License

Apache License 2.0 ©  industry-report-update-skill authors

详见 [`LICENSE`](./LICENSE)。