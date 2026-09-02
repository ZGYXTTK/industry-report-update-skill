# CHANGELOG · industry-report-update-skill

本 Skill 公开版（开源）的全部变更都在这里按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范记录。
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)（MAJOR.MINOR.PATCH）。

## [Unreleased]

### Added
- v1.0.0 开源首发准备中（首版 tag 候选）：
  - LICENSE (Apache-2.0) · CHANGELOG.md · AGENTS.md · discovery.json · install.sh / install.ps1 · marketplace.json · .claude-plugin/plugin.json
  - docs/USAGE.md（每月 SOP + 门禁速查 + 故障排查）· docs/EXAMPLES.md（新增行业包 / 采集项 / 门禁 / 端点 8 例）
  - references/discipline.md（P0/P1/P2 三级纪律全文）· references/gotchas.md（12 条避坑手册）
  - evals/industry-report-update.eval.md + evals/cases/make_fixtures.py + scripts/run_evals.py（fixtures 正负双向冒烟）
  - packs/_default/（5 YAML 脱敏空骨架 + RULES.md + README.md）作为兜底行业包
  - config/_default/（8 个 YAML 示例骨架，与 _default 包配套）
  - .gitignore（隔离 runs/state/下载资料/__pycache__/测试残留）
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
- 真实业务行业包（`packs/robotics/`、`packs/aero/`，含内部标的池、采集清单、权威源映射）
- 真实业务运行记录（`runs/2026-08-20260831142524/`、`runs/2026-08-20260901190113/` 等）
- 真实业务源文件（`下载资料/*.csv`，含上交所/深交所/证监会/披露易全量公开数据）
- 内部口径快照（`config/口径快照/2026-07/08/09.yaml`）

### Fixed
- N/A（公开版首发，未单独修复公开版问题）

### Security
- 全仓库扫描：未发现真实 API key / token / 个人凭证泄漏
- `tool_registry.yaml` 中 `ifind-quant/credentials.json` 仅为路径提示，实际文件位于仓库外且不存在
- 所有真实公司名/法人名已从文档中匿名化

[Unreleased]: https://github.com/<OWNER>/industry-report-update-skill/compare/v0.0.0...HEAD