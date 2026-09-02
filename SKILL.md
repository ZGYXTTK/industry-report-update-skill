---
name: "industry-report-update"
description: "行业月报更新：以用户提供的旧行业月报为模板，端到端生成最新一期月报。核心方法论＝数据流审计（先逆向反推每个结论的数据源/口径/时点，再重新采集、完整枚举、逐条溯源）＋格式保真（保留格式地改写，非 cell.text 覆写）＋源文件归档（每表对应章节+具体来源源文件、金额标财报期、多源交叉验证）＋工作区归档（全产出镜像到使用者当前对话工作区）。内置可执行门禁脚本（数字提取/空值diff/一致性/交叉一致性/合理性/格式diff/数值回读/溯源反查/配置校验）与跨月复用配置（口径/采集/权威源/时点对齐/标的池/端点），支持断点续跑与运行契约。专题对比走独立子Skill（专题研究.skill）；子Agent通道失败由mainagent兜底。触发词：行业月报更新 / 月报更新 / 生成最新月报 / 更新月报。"
version: "2.1"
author: deepseek-harness
---
> 行业月报更新 SKILL · 以旧月报为模板，端到端生成最新一期月报。
> 本版（v2）：验证闭环（数值回读+合理性门禁+盲审）、通道配置化、断点续跑、行业包化、纪律分级。

## 三条铁律（本 Skill 的灵魂）

1. **数据流审计**：旧月报是"结构模板 + 口径参考"，**绝不当数值来源**。每个承载数据的单元都按月重新采集、完整枚举、逐条溯源。
2. **格式保真**：新月报格式与旧月报对齐 ≥95%，用"保留格式地改写"而非 `cell.text = value` 覆写。
3. **工具盘点优先**：Step 2 的第一动作是盘点本机全部可用工具（以实时 tools/list 为准）并 smoke test，映射表写「具体工具名 + 实测结果」；**没实测过的工具一律标 🟡，不得标 ✅**。

**命令**：`/industry-report-update` · 触发词：行业月报更新 / 月报更新 / 生成最新月报 / 更新月报

---

## 资源索引

| 资源 | 路径 | 用途 |
| --- | --- | --- |
| 行业包 | `packs/<行业名>/` | 赛道口径/标的池/权威源/专属纪律（当前激活内容在 config/，见 packs/README.md） |
| 激活配置 | `config/*.yaml` | 口径字典/采集清单/权威源映射/时点对齐/标的池（跨月复用，每月只改截至日期） |
| 端点配置 | `config/endpoints.yaml` | 通道探测目标（URL/方法/请求头），官网改接口只改这里 |
| 格式保真库 | `scripts/docx_utils.py` | 保留格式改写（多 run/多段/合并单元格） |
| 数据源适配器 | `datasources/adapters.py` | 交易所/证监会反爬/分页/WAF 封装 + health_check() |
| 统一入口 | `scripts/run.py` | 一键跑全部门禁 + 断点续跑（--resume） |
| 门禁脚本 | `scripts/audit/` | 数字提取/空值diff/一致性/交叉一致性/合理性/格式diff/数值回读/溯源反查/配置校验 |
| 通道自检 | `scripts/channel_health_check.py` | Step 0.5 硬性前置（HTTP 直探 + MCP 实测回写校验） |
| 口径快照 | `scripts/snapshot.py` | 落盘快照 + 叶子级深 diff（≥3 项暂停确认） |
| 运行契约 | `scripts/manifest.py` | runs/<run-id>/manifest.json，子 Skill 只认它 |
| 行业包管理 | `scripts/pack.py` | list / activate / wizard（新行业反推建包） |
| 跨月度量 | `scripts/metrics.py` | 每期质量指标入 runs/metrics.json，trend 看趋势 |
| 断点状态 | `scripts/checkpoint.py` | 采集项级断点（Step 5 用） |
| 工作区探测 | `scripts/workspace.py` | 解析「当前对话工作区」路径（`--ws` > `--anchor`目录 > `DSH_WORKSPACE` > `DSH_SESSION_JSONL`解码 > cwd；`--anchor`=输入旧月报原始路径，open-source 通用） |
| 工作区归档 | `scripts/archive_to_workspace.py` | **Step 9.5 强制**：把本 run 全产出（报告/变更摘要/专题/源文件/门禁报告/输入）镜像到当前对话工作区 `<工作区>/<产品名>_产出`；不依赖运行环境 |
| 工具清单校验 | `scripts/tool_inventory.py` | **Step 2 机检**：校验 `工具清单.jsonl` 是否覆盖 `config/tool_registry.yaml` 全部已知源、聚合器是否 discover 过、未测是否未标✅（阻断级） |
| 已知源注册表 | `config/tool_registry.yaml` | Step 2 必须覆盖的本机已知信息源清单（含 QVeris 等仓库类），破除思维锚定 |
| 模板 | `templates/` | 确认清单/变更摘要/溯源schema/审计产出/工具清单/子任务（含盲审规范+自检清单） |
| 构建引擎 | `scripts/build_report.py` + `scripts/docx_build.py` | **P2-1**：content/ 声明式构建（模板+内容→月报），原语库含全部保格式操作 |
| 通道选择 | `scripts/channel_pick.py` | **P1-1**：通道实测 → 每采集项建议通道顺序（❌ 沉底） |
| 跨月去重 | `scripts/audit/cross_month_dedup.py` | **P1-2**：本期候选 vs 上月报告实体比对（门禁第 10 道） |
| 锚点自检 | `scripts/audit/anchor_check.py` | **P0-2**：溯源锚点 dry-run（run.py 前置，规则见 docstring） |
| 实战示例 | `修改示例.md` | 机器人月报 6月→7月复盘 |
| 脚本说明 | `scripts/README.md` | 全部脚本用法 + 已知边界 |

---

## 执行清单（10 步闭环）

0. **数据流审计**——反推每个结论的数据源/口径/时点，区分时点型 vs 结构型（extract_numbers.py 提取雏形）。
0.5. **通道健康度自检**——channel_health_check.py；MCP/agent 通道由 Agent 按 endpoints.yaml 的 smoke_hint 真调一次并回写 `通道实测.jsonl`。
1. **理解构成 + 口径快照**——拆「章节→最小内容单元」+ 格式基准；manifest.py init **（必带 `--old-doc <输入旧月报原始路径>`，供 Step 9.5 归档自动锚定工作区）**；snapshot.py snapshot + diff（≥3 项暂停确认）。
2. **映射信息获取途径**——两段式枚举：①tools/list 直连盘点 + smoke test；②**仓库/聚合类源（如 `mcp__qveris__discover`）必须 discover 一次并记录子工具**；③覆盖 `config/tool_registry.yaml` 全部已知源；产出 `工具清单.jsonl` + 映射表，并跑 `tool_inventory.py` 机检（阻断级）。
3. **能力提升分析**——汇总 ❌/🟡。
4. **征询意见**——确认清单一次性问（必填 ≤5 条，支持「一键全采」，结果落盘）。
5. **副本修改生成**——类型驱动处理（结构型复制/半结构型核变化/时点型重采）+ docx_utils 保格式改写（P0-1 函数族）+ checkpoint 断点 + 研究型任务子 Agent fan-out（**结果必须落盘** runs/<run-id>/sources/子任务-<名称>.md，见 P1-4）+ **采集前 channel_pick.py 通道排序、采集后 cross_month_dedup.py 跨月去重**（P1-1/P1-2）。**专题对比走 专题研究.skill，不硬塞**。
6. **循环修正**——run.py 一键门禁（中断加 --resume），最多 3 轮。
7. **来源归档 + 数值回读**——源文件「章节+具体来源」命名、溯源.jsonl 带锚点、verify_value 回读比对、traceability 反查、变更摘要（含异常波动说明）。
8. **独立盲审**——子 Agent 盲审（只看新月报+源文件，严禁给溯源推理）；失败 ≥2 次降级 mainagent 并标注独立性受损；≥3 次暂停。
9. **归档 + 度量**——runs/<run-id>/ 六件套归档，manifest 更新前置状态，metrics.py record 本期指标。
9.5. **工作区归档（P1 强制收尾）**——`archive_to_workspace.py` 把全部产出镜像到**当前对话工作区**；agent 须确认并传入工作区路径（--ws），产出缺失即视为未完成。

---

## 工作流详解（关键步骤）

### Step 0 · 数据流审计（铁律）
对旧月报每个结论性数字回答「审计四问」：①统计口径？②数据源？③时点型还是结构型？④旧月报怎么得出的？
产出用 `templates/数据流审计产出模板.md`：结论清单 + 数据-要求矩阵 + 口径定义。
四铁律：重新采集不沿用 / 完整枚举不按记忆 / 逐条溯源 / 如实报告缺口。

### Step 0.5 · 通道健康度自检（硬性前置）
```bash
python scripts/channel_health_check.py --ym <YYYY-MM> --run-id <run-id>
```
- HTTP 通道：脚本按 `config/endpoints.yaml` 直接探测；
- MCP / agent 通道：脚本**无法**调宿主工具，Agent 必须按 endpoints.yaml 的 `smoke_hint` 真调一次，
  按行回写 `runs/<run-id>/sources/通道实测.jsonl`：
  `{"channel":"...","status":"ok|degraded|fail","tested_at":"YYYY-MM-DD","detail":"..."}`
  脚本校验新鲜度（默认 35 天），过期/缺失 → 🟡 待实测；
- 结果追加 `state/渠道历史.jsonl`，连续 2 期 ❌ 自动触发「续费/改接口」提示。

### Step 1 · 理解构成 + 口径快照 + 运行契约
```bash
python scripts/manifest.py init --ym <YYYY-MM> --run-id <run-id> --pack robotics
python scripts/snapshot.py snapshot --ym <YYYY-MM> --run-id <run-id>
python scripts/snapshot.py diff --ym <YYYY-MM> --prev-ym <上月>
python scripts/audit/config_check.py --out 配置校验报告.md
```
- snapshot 深 diff ≥3 项 → **暂停并请求用户确认**；
- python-docx 拆段落/表格，记录完整格式基准（供 format_diff 对比）。

### Step 2 · 映射信息获取途径（两段式枚举 + 机检，先盘点再映射）
> 目的不是「记录用了哪些源」，而是**穷尽本机全部可用信息源，优中选优做主源，其余做交叉验证**。
> **必须**产出两份 artifact 并写入 `runs/<run-id>/sources/`，缺一即视为 Step 2 未完成：
> ① `工具清单.jsonl`（盘点结果，供 `scripts/tool_inventory.py` 机检）② 《信息获取途径映射表.docx》。
1. **第一段：直连枚举**——tools/list 盘点本机全部工具（MCP/插件/Skill 分组），逐组 smoke test（真取一条样例）；✅=已实测 / 🟡=未测 / ❌=不可用。**未实测不得标 ✅。**
2. **第二段：仓库/聚合器必查**——对**任何「工具仓库/聚合类」源（`mcp__qveris__discover`、带 discover/search 的注册表、能聚合子工具的 server）必须执行一次 discover/搜索**，记录其暴露的具体工具（found_tools）；**不得因「名字抽象看不出用途/怕按量计费/配置里没写」而跳过**。（这正是本次 QVeris 被漏的根因。）
3. **对照注册表覆盖**——逐条列出 `config/tool_registry.yaml` 的已知信息源在普查中的结论（存在/未装/不可用），发现"本机有、注册表未列"的源必须补记。
4. **跑机检**：`python scripts/tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl` → 阻断（缺聚合器探查/已知源未盘点/未测标✅）则返工。
5. 逐最小内容单元写：具体工具名（禁止"iFinD"这类抽象标签）+ 覆盖度 + 2-3 级降级链 → 《信息获取途径映射表.docx》。主源用已实测(✅)且权威的；测试过但非主用的作交叉验证。
> ⚠️ config 的「采集通道」只是权威源参考，**不是**本机工具全集；本机存在即应进清单并实测。成本分层：discover/盘点免费，真正取数的 call 才按量计费——不要因怕花钱跳过盘点。

### Step 4 · 征询意见（一次性结构化确认）
用 `templates/确认清单模板.md`：必填 ≤5 条（超出转建议项），每项给默认值+反推依据；
用户可逐项批注或「一键全采」；确认结果落盘 `runs/<run-id>/input/用户确认.md`。
「≥95% 把握」= 所有必填项已获明确答复。

### Step 5 · 副本修改生成（保格式改写 + 断点续跑）
1. 复制副本；先跑 `datasources/adapters.py` 的 health_check() 与 `python scripts/channel_pick.py --run-id <run-id>`（P1-1：按本期通道实测排序每项的通道顺序，❌ 沉底），按采集清单「类型」处理：
   结构型→直接复制；半结构型→只核变化字段（名单沿用标的池）；时点型→全量重采（失败沿降级链切换）。
2. **断点**：每完成一个采集项 `checkpoint.record(item_id,'done',...)`；中断后 `checkpoint.resume(清单)` 续跑。
3. 研究型单元按 `templates/subagent任务模板.md` fan-out，主 Agent 验真回接。
4. 改写优先用声明式引擎 `python scripts/build_report.py --template 旧月报.docx --content runs/<run-id>/content --out 新月报.docx`（P2-1/P2-2，content/ 约定见 templates/content-schema-example.json；行业特有逻辑写 content/hooks.py）。手写脚本时用 docx_utils（**禁止** `cell.text=`/`p.text=`/`add_paragraph` 覆写；
   **必须使用 v2 保留结构函数族**——旧 API 只改首段/重建 run，是「旧值残留」「格式回归」两类门禁失败的根因，2026-09 实测修复）：
```python
from docx_utils import set_cell_keep, fill_table, strip_vmerge, set_para_keep, add_row_copy_fmt
set_cell_keep(cell, value)                # 单元格写入：保留全部段落与 run 结构；list 值按段落 1:1 分配
fill_table(table, rows, start_row=1)      # 表格回填：自动删多余数据行/克隆补足行，再逐格 set_cell_keep
strip_vmerge(table)                       # 重填前清除 vMerge 残留（防序号跳号/事件-标的错配）
set_para_keep(p, text)                    # 段落写入：首 run 写文本、其余 run 置空（run 结构保留，防 format 回归）
add_row_copy_fmt(table, values)           # 新增行复制格式（含 gridSpan）
set_para_segments_keep_fmt(p, [(...), ])  # 仅用于需要多格式 run 的标题段
```
5. **图表双轨（P2-11）**：原生 OOXML 图表无法重算 → 保留原图 + 图下加机器可检脚注
   「注：本图数据截至旧期 YYYY-MM，最新数据见表 X」**并把对应数据表列为必更新项**；
   图片类图表重生成后替换并同步图内数据。
6. 无法获取标注「本期无法获取 / —」；docx 被占用先写 .tmp.docx；删除章节跳过 `<w:sectPr>`。

### Step 6 · 循环修正（run.py 一键，最多 3 轮）
```bash
# 先跑锚点自检（dry-run，把 verify_value/traceability 的锚点错误前置为一次本地检查）：
python scripts/audit/anchor_check.py runs/<run-id>/sources/溯源.jsonl \
    --base-dir runs/<run-id>/sources/anchors --out runs/<run-id>/logs/锚点自检.md
python scripts/run.py 旧月报.docx 新月报.docx --key-col-name 公司简称 \
    --jsonl 溯源.jsonl --roster-note 变更摘要.md --out-dir runs/<run-id>/logs
# 中断后续跑（跳过已通过门禁）：
python scripts/run.py 旧月报.docx 新月报.docx --key-col-name 公司简称 \
    --jsonl 溯源.jsonl --roster-note 变更摘要.md --out-dir runs/<run-id>/logs --resume
```
第 3 轮仍磨不平的差距（如 TOC 需 F9）逐条如实报告。

### Step 7 · 来源归档 + 数值回读
- 源文件命名「章节+具体来源」；金额标财报期；正文表格加脚注「财务数据为各公司最近披露财报期，详见源文件」；
- `溯源.jsonl` 按 templates/溯源.schema.json：**数值类必须带锚点**（source_key+source_field 或 source_row+source_field），
  网页来源另存快照（snapshot 字段）；出处为 source_file 或 url 二选一；
- **锚点约定**（详读 `scripts/audit/anchor_check.py` docstring，run.py 前必跑该自检）：
  锚点文件一律用 **CSV 文本**（首行表头；"xls" 实为 CSV 的可直接用）；source_key 在键列按
  「半角化/去括号/去公司后缀」匹配，键列默认首列、可用 `source_key_col` 指列名；
  source_field 为取值列名；数值比对取 value **首个数字**（勿在 value 前缀段混入无关数字/单位，
  万元/亿元/% 混用会判单位不一致）；url-only 记录不参与回读但认可为出处；
- `build_traceability.py` 半自动生成（自动锚定键列）→ Agent 补 status/cross_checked；
- **verify_value.py 回读比对**（月报数字≠源文件数字 = 硬伤；量级差 10/100/10000 倍报单位疑似不一致）；
- traceability_check.py 反查（覆盖率 + 交叉验证强制）；conflict_classify.py 冲突分级；
- 《变更摘要.md》必须含「异常波动说明」——环比 ±50% 以上与新增/移除标的逐条点名（reasonableness 门禁回查）。

### Step 8 · 独立盲审（P0）
按 `templates/subagent任务模板.md` 第六节「盲审规范」执行：
- 审核子 Agent **只给**新月报 + 下载资料/源文件；**严禁给**溯源.jsonl/变更摘要/主 Agent 推理；
- 输出按 阻断/建议/提示 分级；阻断级 >0 → 修正后**换新审核 Agent 复审**；
- **盲审 prompt 必须附带下方《盲审自检清单》**（全部为本 Skill 各期实测踩坑模式，随附可令盲审 1-2 轮收敛）：
  1. 跨月去重：本期事件/公司逐条与上月报告比对（公告日 vs 转载日，±45 天窗口）；
  2. 上月口径残句扫描：以「上月」为叙述主语的数据段、上月数值以新值身份出现、段首无主语残句；
  3. 合并单元格伪影：vMerge 残留（序号跳号/事件-标的错配）、gridSpan 错位；
  4. 续表表头：跨页拆表的第二物理表有无表头；表头孤立（无数据行）；
  5. 正文计数=表行数：每处「共 N 家/条/笔」逐一对表；
  6. 日期口径：公告日/官网更新日/转载日差一天须注明；
  7. 金额单位：万元/亿元/美元混排、占比与金额加总口径；
  8. 通道降级声明：受限通道是否在正文注脚可见（而非只在变更摘要）；
  9. run/格式保真：图片替换后图注、字体一致性；
  10. 表格行数缩减后的残行清理（上月行残留→计数与一致性误报）；
  11. 残句删除用包含匹配（in），不用前缀匹配（startswith）；
  12. 「无法获取/未核实/—」标注真实性抽查（源文件里其实有没有）。
- 通道失败按 D 节兜底（降级 mainagent 须标注「独立性受损」）。

### Step 9 · 归档 + 度量
```bash
python scripts/manifest.py set --run-id <run-id> --key preconditions.channel_health_done --value true
python scripts/metrics.py record --ym <YYYY-MM> --run-id <run-id> --gate format_diff=<得分> --downgrades <N>
```

### Step 9.5 · 工作区归档（P1 强制收尾）
> 目的：保证任何一次调用，全产出都出现在**使用者的当前对话工作区**（而非 skill 基目录/AppData 缓存）。
> 若 Skip 此步，则本 Skill 的交付视为未完成。
>
> ★ **open-source 可移植要求**：Agent 必须显式传入工作区，**不得依赖**本 Skill 所在运行环境；
> 首选 `--anchor`（用你打开的那份**输入旧月报的原始路径**，其目录即工作区——任何环境都成立），其次 `--ws`。
> 只靠自动探测（DSH_SESSION_JSONL 解码）仅在 DeepSeek Harness 生效，其他运行时可能退化为 skill 基目录（此时脚本会**安全拒绝**并报错，需补传）。
```bash
# 可移植（推荐）：以输入旧月报原始路径为锚点，自动定位工作区
python scripts/archive_to_workspace.py --run-id <run-id> --anchor "<输入旧月报原始路径>" --product "<产品名>"
# 或显式指定工作区：
python scripts/archive_to_workspace.py --run-id <run-id> --ws "<当前对话工作区路径>" --product "<产品名>"
# 自动探测（Harness 内可用）：--ws/--anchor/DSH_WORKSPACE/DSH_SESSION_JSONL/cwd 依次兜底
python scripts/archive_to_workspace.py --run-id <run-id> --product "<产品名>"
```
产物结构（在工作区 `<工作区>/<产品名>_产出/`）：
- 根：新月报 .docx、变更摘要.md、专题*.md
- `输入/`：旧月报、用户确认等
- `源文件/`：交易所 CSV、溯源.jsonl、通道实测.jsonl、采集记录*.md（并自动并入 skill 基目录 `下载资料/` 的源文件）
- `门禁报告/`：格式对比/一致性/交叉一致性/空值对比/溯源反查/配置校验/运行日志/通道降级日志/通道健康度

> 工作区识别优先级：`--ws` > `--anchor` 目录 > `DSH_WORKSPACE` > `DSH_SESSION_JSONL` 解码 > 当前工作目录。脚本会**拒绝**把产出写到 skill 基目录内；一旦解析结果异常（如退化为基目录）即报错提示补传，绝不静默写错位置。

---

## 门禁速查（9 道）

| # | 门禁 | 命令 | 拦截条件 |
| --- | --- | --- | --- |
| 1 | 数字提取 | `extract_numbers.py 旧.docx` | 无（产出清单） |
| 2 | 配置校验 | `config_check.py` | 采集项缺字段/通道名未定义 |
| 3 | 空值 diff | `diff_empty.py 旧.docx 新.docx --key-col-name 公司简称` | 旧有值→新空值>0（业务键对齐） |
| 4 | 一致性 | `consistency_check.py 新.docx` | 合计≠分项和（硬） |
| 5 | 交叉一致性 | `cross_consistency_check.py 新.docx` | 正文「共N家」≠表格行数（硬） |
| 6 | 合理性 | `reasonableness_check.py 旧.docx 新.docx --roster-note 变更摘要.md` | 环比±50%未说明 / 新增移除未点名（硬） |
| 7 | 格式对比 | `format_diff.py 旧.docx 新.docx --threshold 0.95` | 相似度<95%（结构变化不计） |
| 8 | 数值回读 | `verify_value.py 溯源.jsonl` | 月报数字≠源文件回读值 / 锚点失效（硬） |
| 9.5 | 跨月去重 | `cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv` | 候选名命中上月实体（全名/子串）且未逐条处置（硬） |
| 9 | 溯源反查 | `traceability_check.py 溯源.jsonl --min-coverage 0.9 --require-cross-check --against-docx 新.docx` | 无出处/源文件缺失/覆盖率(登记溯源行)<90%/未交叉验证；真实覆盖率(vs docx 数据单元)为报告性指标，不做100%硬性拦截 |

> 一键：`scripts/run.py`（含断点续跑 --resume、单项重跑 --only、逐门禁计时）。前置：`anchor_check.py` 锚点自检 dry-run。资源文件不可用时用本文件内联规则，不阻断任务。

---

## 纪律分级

### P0 · 阻断级（违反即返工，不得交付）

1. **禁止编造**：拿不到就标「本期无法获取 / —」；专题未取得招股书填「未取得招股书」。
2. **重新采集不沿用**：时点型数据按月重采完整枚举。
3. **工具实测先于标 ✅**：未 smoke test 的工具不得标 ✅；映射表写具体工具名。
4. **来源逐条标注**：正文「来源：机构+日期」，表格「数据来源+截至」；溯源.jsonl 数值类带锚点。
5. **数值回读通过**：verify_value 无 ❌（月报数字 = 源文件数字）。
6. **名单/异常有交代**：环比异常与新增/移除标的在变更摘要逐条点名（reasonableness 无 ❌）。
7. **盲审通过**：独立盲审无阻断级问题；复审必须换新审核 Agent。
8. **格式对齐 ≥95%**：format_diff 评分达标（结构变化不计）。
9. **空值必补**：diff_empty 抓「旧有值→新空值」，非空则必补（业务键对齐，禁用序号）。
10. **口径漂移暂停**：snapshot 深 diff ≥3 项必须暂停并请求用户确认。
11. **产出必达工作区**：Step 9.5 必须执行 `archive_to_workspace.py`，全产出须出现在使用者**当前对话工作区**（不得只留在 skill 基目录 run 内）——违反即视为未交付。

### P1 · 警告级（须如实记录并可追溯，不阻断交付）

1. 一次性确认：必填 ≤5 条，确认结果落盘。
2. 字段口径一致：同一字段全表统一（法人统一工商名、是否上市统一"是/否"）。
3. 时点统一：按 时点对齐策略.yaml 对齐各来源时点，首页脚注写明采集日+目标时点。
4. 财报期双轨：源文件标期 + 正文表格脚注。
5. 差距如实报告：TOC 需 F9、图表未更新、数据源无接口、子Agent 失败等明确告知。
6. 通道降级全月报可追溯：正文「数据来源」段显式引用本期实际生效通道与降级链。
7. 每表对应「章节+具体来源」源文件；交叉验证标注冲突+采用源+理由。
8. 归档完整：runs/<run-id>/ 六件套 + 运行日志 + 通道降级日志 + metrics 记录。

### P2 · 行业包级（见 packs/<行业名>/RULES.md）

机器人包示例：港股 6 个月有效期剔除、美股 S-1/SPAC 分类、卖方一致预期独立小表等。
**换行业只换包，不改本文件。**

---

## 运行机制

### A. 通道自检与实测回写（Step 0.5）
端点在 `config/endpoints.yaml`（配置化，改接口不动脚本）；HTTP 直探 + MCP/agent 由 Agent 实测回写
`通道实测.jsonl`；历史入 `state/渠道历史.jsonl`，连续 2 期 ❌ 触发续费/改接口提示。

### B. 口径快照与版本治理（Step 1）
5 个 YAML 加 version 字段；snapshot.py 落盘 `config/口径快照/<YYYYMM>.yaml` 并做叶子级深 diff；
月报首页脚注写「按口径字典 vX.Y、采集清单 vX.Y（采集日/目标时点）」；
禁止裸改 YAML——新增版本号 + 备份旧版 + 变更摘要列差异。

### C. 专题独立化（强制）
专题对比走 `专题研究.skill/SKILL.md`，前置状态从 `runs/<run-id>/manifest.json` 读取（P1-7 契约）；
大月报只引用专题结论与关键数字，占位符 `详见专题报告-<对比对象>-<YYYYMM>`；
招股书 PDF 落盘 下载资料/，用 qcc-document 解析回填；PDF 不可获取填「未取得招股书」。

### D. 盲审与兜底（Step 8）
每月开局先测 subagent/workflow/mainagent 三通道（记入 `config/agent_health.yaml`）：
失败 1 次记 warning；≥2 次降级 mainagent 对抗性自查并在《独立审核意见.md》标注
「独立性受损：subagent 通道 N 月连续 N 次失败」；≥3 次暂停执行，提示人工检查模型路由。

### E. 运行目录（run-id 化）
```
runs/<YYYY-MM-XXXXXX>/
├── input/      # 旧月报、用户确认.md
├── output/     # 新月报、变更摘要
├── logs/       # 门禁输出、运行日志、通道降级日志、门禁状态.json
├── download/   # 源文件 CSV/PDF
├── sources/    # 溯源.jsonl、来源记录.xlsx、通道实测.jsonl、网页快照
├── reviews/    # 独立审核意见、冲突分级报告
└── manifest.json
```
运行日志必填：起止时间/命令序列/通道降级记录/子Agent失败次数/门禁得分摘要。
> `runs/<run-id>/` 为 Skill 内部工作目录（技能基目录下）；**最终交付必须经 Step 9.5 `archive_to_workspace.py` 镜像到使用者的当前对话工作区**，二者缺一不可。

### F. 通道降级日志（logs/通道降级日志.md 必填字段）
| 通道 | 本期状态 | 降级链 | 触发原因 | 持续期数 | 下月建议 |

---

## Gotchas（实测环境事实 · 2026-09 沉淀，逐期追加勿删）

> 只收录「与合理假设相悖、且已在本 Skill 执行中实测」的环境事实。新事实随期追加，注明首遇期。

- 上交所官网导出的 ".xls"（SH_XM_LB/GP_ZRZ_XMLB/GP_BGCZ_XMLB）实为 **UTF-8 CSV 文本**，用 `pd.read_csv(path)`（逗号分隔）读，勿用 read_excel（2026-08 期）。
- 深交所 `projectrends/query` 的 `start` 分页参数失效、`pageSize` 上限 100（连续 2 期实测）——全量枚举改「top100 + 公告逐家核验」，勿反复尝试分页（2026-07/08 期）。
- 北交所 bse.cn WAF 常态化 ConnectionResetError 10054——直接走公告/媒体核验，勿重试直连（连续 2 期）。
- **申万指数码禁用 wind_stock_data.get_stock_kline**：801742.SL 被误解析为个股（返回 7-9 元股价）；申万二级/一级指数一律用 mx_index_block_finance_data（2026-08 期）。
- 东财「区间涨跌幅（月初首个交易日至月末）」口径与历史月报的指数/个股数值完全对齐（个股榜 55 只池已逐项复现验证）——月度涨跌幅统一用此口径（2026-08 期）。
- 申万国防军工成分 = 航空装备Ⅱ（46 只）∪ 航天装备Ⅱ（9 只），该 55 只池可完整复现历史个股涨跌榜；军工电子/兵器/船舶不在池内（2026-08 期审计确认）。
- qcc 必须用工商全称；简称先 `get_company_by_query` 消歧并展示候选；积分中途耗尽→已采字段降级标注，勿整体放弃（2026-08 期）。
- 行业月度合集会把上月事件转载进本月——一级市场/并购事件必须做跨月去重（对照上月报告，公告日 ≠ 转载日）（2026-08 期）。
- tushare `index_dailybasic` 需积分权限（40203）；申万指数 PE 十年分位用东财「年末 PE 序列」近似并在正文注明口径（2026-08 期）。
- docx 保格式写入必须用 P0-1 函数族；删除残句/残留段用**包含匹配**；表格重填后必须核「行数=预期、无上月残行」（2026-08 期）。
- PowerShell 下写中文脚本一律用脚本文件，勿用 `python -c` 内联（引号/编码搅碎）；console 打印中文先 `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`。

## 已知边界（如实声明，不伪装）

1. format_diff 是格式属性签名比对，不覆盖图表/图片视觉差异，含图表报告需人工补看图。
2. 原生 OOXML 图表无法重算（双轨制兜底）；跨行 vMerge 复杂表需人工复核。
3. TOC 页码域需在 Word/WPS 按 F9 刷新。
4. 门禁查「自洽 + 回读一致」，无法发现源文件本身的错误——权威源选择仍靠 Step 2 映射纪律。
9. diff_empty/verify_value 的键归一化是启发式（去括号/去公司后缀），极端同名异写需人工复核。
6. build_report.py 声明式引擎覆盖本期验证过的 op 集合（replace_range/fill_table/note_after_table/replace_image 等）；超出集合的结构操作走 exec_python 钩子或手写脚本（docx_build.py 原语库兜底）。
7. cross_month_dedup 只做名字级命中（全名/子串）；转载合集若改写公司名仍可能漏网——终审以盲审自检清单第 1 条为准。
