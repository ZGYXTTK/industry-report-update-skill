# scripts · industry-report-update-skill 工具库（v3.1 · 开源版）

本目录是 SKILL 的「可执行载体」，把铁律从口号变成可跑的门禁。
公开版仅含**通用引擎 + 兜底行业包**，具体行业包由用户激活后通过 `pack.py wizard` 反推。

## 目录结构

```
scripts/
├── run.py                    # 统一入口：11 道门禁一键 + --resume 断点续跑
├── run_evals.py              # 评估器（fixtures 正负双向冒烟 + --promote / --against-baseline）
├── build_report.py           # 声明式构建引擎（content/ → docx）
├── docx_build.py             # 原语库（保格式写）
├── docx_utils.py             # 格式保真工具库（多 run / 多段落 / 合并单元格 gridSpan）
├── yaml_lite.py              # 统一 YAML 加载器（PyYAML 优先 + mini 回退，双后端一致性验证）
├── channel_health_check.py    # Step 0.5 通道自检（HTTP 直探 + MCP 实测回写校验）
├── channel_pick.py           # 通道排序（P1
├── snapshot.py               # 口径快照 + 叶子级深 diff（≥3 项暂停确认）
├── manifest.py               # runs/<run-id>/manifest.json 运行契约
├── pack.py                   # 行业包管理（list / activate / wizard）
├── metrics.py                # 跨月度量（record / / trend）
├── checkpoint.py             # 采集项级断点
├── workspace.py              # 解析「当前对话工作区」路径
├── archive_to_workspace.py   # 工作区归档（P0-11 强制收尾）
├── tool_inventory.py         # Step 2 机检（阻断级）
├── conflict_classify.py      # 冲突分级
├── dump_docx.py              # docx 结构 dump（调试用）
├── dump_docx_full.py         # docx 完整 dump（调试用）
├── audit/
│   ├── extract_numbers.py        # ① 数据流审计：结论性语句提取
│   ├── config_check.py           # ② 配置一致性校验
│   ├── diff_empty.py             # ③ 空值 diff（--key-col-name 业务键对齐）
│   ├── consistency_check.py      # ④ 一致性（合计硬门禁、占比提示）
│   ├── cross_consistency_check.py # ⑤ 交叉一致性（正文「共N家」vs 表格行数）
│   ├── cross_month_dedup.py      # ⑪ 跨月去重（P1-2 新增）
│   ├── anchor_check.py           # ⑩ 锚点自检 dry-run（P0-2 新增）
│   ├── reasonableness_check.py   # ⑥ 合理性（环比异常/名单变化须交代）
│   ├── format_diff.py            # ⑦ 格式对比 + 相似度评分
│   ├── verify_value.py           # ⑧ 数值回读（月报数字 vs 源文件回读值）
│   ├── traceability_check.py     # ⑨ 溯源反查（覆盖率 + 交叉验证强制）
│   └── build_traceability.py     # 溯源.jsonl 半自动生成（自动锚定键列）
├── tests/
│   ├── test_p0_fixes.py          # P0 缺陷修复回归测试
│   └── test_reasonableness_parse.py  # 合理性检查解析单元测试
├── ../datasources/adapters.py    # 数据源适配器（反爬/分页/WAF + health_check）
└── README.md                    # 本文件
```

## 依赖

- `python-docx>=0.8.11`（必装）
- `requests`、`pandas`、`xlrd==1.2.0`、`openpyxl>=3.1`（datasources/adapters.py 用，懒加载）
- `PyYAML`（推荐，无则 yaml_lite mini 回退）
- 标准库 `zipfile` / `xml.etree`（format_diff 解包 XML，无额外依赖）

## 一键用法（推荐）

```bash
# 全部 11 道门禁
python scripts/run.py 旧月报.docx 新月报.docx --key-col-name 公司简称 \
    --jsonl 溯源.jsonl --roster-note 变更摘要.md --out-dir runs/<run-id>/logs

# 中断后续跑（跳过已通过门禁，状态存 <out-dir>/门禁状态.json）
python scripts/run.py 旧月报.docx 新月报.docx --key-col-name 公司简称 \
    --jsonl 溯源.jsonl --roster-note 变更摘要.md --out-dir runs/<run-id>/logs --resume

# 软门禁降级（内容重建模式）
python scripts/run.py 旧月报.docx 新月报.docx --soft-gates 03_diff_empty,06_reasonableness_check,07_format_diff ...

# 评估
python scripts/run_evals.py --rollout              # 跑全部 fixtures
python scripts/run_evals.py --promote            # 推广为基线
python scripts/run_evals.py --rollout --against-baseline  # 对比基线（防回归）
```

## 单门禁用法速查

```bash
# ③ 空值 diff
python scripts/audit/diff_empty.py 旧.docx 新.docx --key-col-name 公司简称

# ⑤ 交叉一致性
python scripts/audit/cross_consistency_check.py 新.docx

# ⑥ 合理性：环比 ±50% 与新增/移除标的必须在变更摘要逐条点名，否则硬伤
python scripts/audit/reasonableness_check.py 旧.docx 新.docx --roster-note 变更摘要.md --out 合理性校验报告.md

# ⑦ 格式对比
python scripts/audit/format_diff.py 旧.docx 新.docx --threshold 0.95

# ⑧ 数值回读：溯源.jsonl 带锚点（source_key + source_field / source_row + source_field）
python scripts/audit/verify_value.py 溯源.jsonl --base-dir 下载资料 --out 数值回读报告.md
#   --rel-tol 0.001（数值相对误差容忍）  --require-anchor（无锚点也判硬伤）

# ⑨ 溯源反查（source_file 或 url 二选一即算有出处）
python scripts/audit/traceability_check.py 溯源.jsonl --min-coverage 0.9 --require-cross-check --against-docx 新.docx --out 溯源反查报告.md

# ⑩ 锚点自检（run.py 前必跑）
python scripts/audit/anchor_check.py 溯源.jsonl --base-dir 下载资料 --out 锚点自检.md

# ⑪ 跨月去重
python scripts/audit/cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv

# 通道自检（MCP/agent 通道需先由 Agent 实测回写 通道实测.jsonl）
python scripts/channel_health_check.py --ym 2026-09 --run-id <run-id> --mcp-log runs/<run-id>/sources/通道实测.jsonl

# 通道排序
python scripts/channel_pick.py --run-id <run-id>

# 口径快照（落盘 + 深 diff）
python scripts/snapshot.py snapshot --ym 2026-09 --run-id <run-id>
python scripts/snapshot.py diff --ym 2026-09 --prev-ym 2026-08

# 运行契约（子 Skill 前置检查读它）
python scripts/manifest.py init --ym 2026-09 --run-id <run-id> --pack _default
python scripts/manifest.py get --run-id <run-id> [--key preconditions.channel_health_done]
python scripts/manifest.py set --run-id <run-id> --key preconditions.channel_health_done --value true

# 行业包
python scripts/pack.py list
python scripts/pack.py activate _default
python scripts/pack.py wizard 旧月报.docx --name medtech

# 跨月度量
python scripts/metrics.py record --ym 2026-09 --run-id <run-id> --gate format_diff=0.978 --downgrades 1
python scripts/metrics.py trend

# 工作区归档（Step 9.5 · P0-11 强制收尾 · v3.1）
#   --anchor 缺省时自动探测：--anchor 目录 > DSH_WORKSPACE > DSH_SESSION_JSONL > cwd
#   产物镜像到 <当前对话工作区>/<产品名>_产出/
python scripts/archive_to_workspace.py --run-id <run-id> --anchor "<输入旧月报路径>" --product "<产品名>"
python scripts/archive_to_workspace.py --run-id <run-id> --ws "D:\\工作区" --product "<产品名>"
```

## 溯源.jsonl 锚点写法（verify_value.py 回读依据）

```json
{"cell": "表8!R2", "value": "1.2亿元", "source_file": "下载资料/融资.csv",
 "source_key": "A 公司", "source_field": "融资金额", "status": "verified",
 "cross_checked": ["iFinD"], "as_of": "2026-09-30"}
```

- 锚点 A：`source_key`（+ 可选 `source_key_col`，默认首列）+ `source_field`
- 锚点 B：`source_row`（1-based 数据行）+ `source_field`
- 网页来源：`url` + `snapshot`（快照存档路径）；`status=gap` 的记录跳过比对

## 已知边界（如实声明，勿伪装）

1. `format_diff.py` 的相似度是「格式属性签名」比对，不覆盖图表/嵌入对象/图像的视觉差异
2. `verify_value.py` 只能验证「月报=源文件」，不能验证源文件本身对错（权威源选择靠 Step 2 纪律）
3. `reasonableness_check.py` 的「交代检查」是关键词点名（变更摘要中出现该标的即算交代），不判断原因解释的质量
4. `consistency_check.py` 的「合计=分项和」依赖表中存在含「合计/总计」关键字的行
5. `docx_utils.add_row_copy_fmt` 已处理横向 gridSpan；跨行 vMerge 复杂表需人工复核
6. `yaml_lite.py` mini 回退不支持 YAML 锚点/多文档/标签 —— 遇到会显式报错并提示安装 PyYAML
7. `checkpoint.py` 记录的是采集项状态；门禁级断点用 `run.py --resume`（门禁状态.json）

## 回归测试

```bash
# P0 缺陷修复回归（覆盖一次代码审查发现的 P0 缺陷修复，全部断言 PASS 才退出 0）
python scripts/tests/test_p0_fixes.py
python scripts/tests/test_reasonableness_parse.py
```

覆盖范围详见 `references/discipline.md` 与 `references/gotchas.md`。