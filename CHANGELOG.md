# CHANGELOG · industry-report-update-skill

本 Skill 公开版（开源）的全部变更都在这里按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范记录。
版本号遵循 [Semantic Versioning](https://semver.org/lang/)（MAJOR.MINOR.PATCH）。

## [1.0.0] · 2026-09-01 · 开源首发（Apache-2.0）

### Added
- 开源首发准备：
  - LICENSE (Apache-2.0) · CHANGELOG.md · AGENTS.md · discovery.json · install.sh / install.ps1 · marketplace.json · .claude-plugin/plugin.json
  - docs/USAGE.md（每月 SOP + 门禁速查 + 故障排查）· docs/EXAMPLES.md（新增行业包 / 采集项 / 门禁 / 端点 8 例）
  - references/discipline.md（P0/P1/P2 三级纪律全文）· references/gotchas.md（20 条避坑手册）
  - evals/industry-report-update.eval.md + evals/cases/make_fixtures.py + scripts/run_evals.py（fixtures 正负双向冒烟）
  - packs/_default/（5 YAML 脱敏空骨架 + RULES.md + README.md）作为兜底行业包
  - config/_default/（9 个 YAML 脱敏骨架：5 个赛道 YAML + endpoints + tool_registry + agent_health + 渠道状态）
  - .gitignore（隔离 runs/state/下载资料/__pycache__/测试残留 + 真实业务行业包）
- 新增 `cross_month_dedup.py`（P1-2 跨月去重门禁）
- 新增 `channel_pick.py`（P1-1 通道排序）
- 新增 `anchor_check.py`（P0-2 锚点 dry-run 自检）
- 新增 `build_report.py` + `docx_build.py`（声明式构建引擎）

### Changed
- v2.1 → v1.0.0 公开版编号重置（母版内部仍为 v2.1）
- SKILL.md / README.md / 使用说明.md / 修改示例.md 改写：删除所有真实公司名/法人名（全部替换为占位符 "A 公司/B 公司/CEO 张三/…"），改为通用反推案例
- `robotics` / `aero` / `_backup` 三个行业包从开源仓库移除（私有保留），改用 `_default` 兜底包占位
- `runs/` `state/` `下载资料/` 全部从仓库隔离（私有运行痕迹与业务源文件）

### Removed
- 真实业务行业包（`packs/robotics/`、`packs/`、``），含内部标的池、采集清单、权威源映射
- 真实业务运行记录（`runs/2026-08-20260831142524/`、`runs/2026-08-20260901190113/` 等）
- 真实业务源文件（`下载资料/*.csv`，含上交所/深交所/证监会/披露易全量公开数据）
- 内部口径快照（`config/口径快照/2026-07/08/09.yaml`）

### Fixed
- 修复 v1.0.0 首发 commit 中 6 个文件因 PowerShell 5.1 zh-CN 区域默认 ANSI/GBK 编码导致的中文字符损坏（`README.md` / `使用说明.md` / `CHANGELOG.md` / `marketplace.json` / `.claude-plugin/plugin.json` / `docs/EXAMPLES.md`）。改用 .NET UTF-8（`[System.Text.UTF8Encoding]::new($false)`）直接写入修复。
- 修复 `scripts/tests/test_p0_fixes.py` 中残留的本地业务路径示例（脱敏为 `D:\Desktop\industry-research\reports\...`）。
- 修复 SKILL.md frontmatter 与文档内容不一致（v2.1 → v1.0.0；触发词补英文 `generate monthly report`；"实战示例"改"通用反推案例（脱敏）"；门禁速查编号 9.5/9 → 11 道顺序编号；已知边界编号连续化）。
- 修复 SKILL.md / README.md / AGENTS.md 中错误的函数名引用（`set_para_text_keep_fmt` → `set_cell_keep / set_para_keep`）。
- 修复 CHANGELOG.md / discovery.json / SKILL.md 中触发词列表缺失英文触发词 `generate monthly report`。

### Security
- 全仓库扫描：未发现真实 API key / token / 个人凭证泄漏
- `tool_registry.yaml` 中所有涉及 token / 凭证路径 / 本地账号的具体通道全部脱敏为 `<your_aggregator>` 占位符；真实账号路径（如 `D:\Desktop\...`）全部移除
- 所有真实公司名 / 法人名 / 品牌名（行业月度合集名）已从文档中匿名化

### Maintenance
- 验证：35 个 .py 文件全部 `python -m py_compile` 通过（0 fail）
- 验证：13 个 .yaml 文件全部 `yaml.safe_load` 通过（0 fail）
- 验证：5 个 .json 文件全部 `json.load` 通过（0 fail）

[1.0.0]: https://github.com/ZGYXTTK/industry-report-update-skill/releases/tag/v1.0.0
[Unreleased]: https://github.com/ZGYXTTK/industry-report-update-skill/compare/v1.0.0...HEAD