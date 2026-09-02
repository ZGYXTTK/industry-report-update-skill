---
name: industry-special-topic
description: "行业专题研究：基于最新月报数据与招股书原文，生成「双公司深度对比」专题（如「A 公司 vs B 公司」对比）。强约束：① 输入必须包含招股书 PDF（不可获取则强制填'未取得招股书'）；② 对比双方必须业务模式同构；③ 强依赖基础月报 Skill 的 Step 0-3 通道健康度与口径快照；④ 输出专题报告 .docx + 专题表 9-12 数据回填月报的源文件。触发词：专题研究 / 双公司对比 / 专题."
---

> 行业专题子 Skill · 仅当用户明确提出"做专题"或月报 Skill 触发专题章节时调用。
> 设计原则：把专题从大月报剥离，避免单次专题占掉 50% 以上 token 与 3 轮门禁预算。

## 与 industry-report-update 的关系

| 输入/输出 | industry-report-update (大月报) | industry-special-topic (本 Skill) |
| --- | --- | --- |
| 触发 | 每月定期 | 大月报需要"专题章节"时；或用户直接要求 |
| 输入 | 旧月报 + 5 个 YAML + 本月通道状态 | 大月报 Step 0-3 输出（口径快照、通道健康度、标的池）+ 招股书 PDF + 候选对比公司 |
| 输出 | 新月报 + 14 张表 + 溯源 | 专题报告 docx + 表 9-12 关键数字回填月报源文件 |
| 门禁 | 6 道硬卡 | 5 道（去空值/格式，但保留口径漂移/通道降级专项卡） |

---

## 调用前置检查（硬性，缺一不可）

```bash
# 0. 读 manifest（P1-7 契约：run-id 与路径不再靠猜）
python scripts/manifest.py get --run-id <run-id>

# 1. 基础月报 Step 0.5 已跑通（等价于 preconditions.channel_health_done == true）
python scripts/manifest.py get --run-id <run-id> --key preconditions.channel_health_done

# 2. 口径快照存在且与上期差异 <3 项
python scripts/snapshot.py diff --ym <YYYYMM> --prev-ym <上月>

# 3. 招股书 PDF 已落盘（manifest paths.sources_dir 指向的目录）
ls -la <sources_dir>/招股书*.pdf

# 4. 候选对比公司池业务模式同构（运行 Step 0.5）
python scripts/check_compare_compatibility.py \
  --co_a "A 公司" --co_b "B 公司"
```

任意一项缺失则暂停并向用户报错（按硬性纪律 11）。

---

## 7 步执行流

### Step 1 · 对比公司兼容性校验
- 输入：候选对比公司 A、B（注册名）
- 输出：`runs/<run-id>/专题-precheck-<对比对象>.md`，包含：
  - 业务模式同构性（人形机器人 vs 协作机器人 可比性 ✅；全形态龙头 vs 老牌视觉龙头 ❌）
  - 财务披露口径可比性（财年口径/分部口径）
  - 估值可比性（DDM vs 相对估值 vs 撮合成交价）
  - 最近 6 个月审核进度对照
- 不可比 → 拒绝执行并报告用户。

### Step 2 · 招股书原文提取
- 输入：招股书 PDF（必须已落盘 `下载资料/招股书 <公司名>.pdf`）
- 工具：`mcp__qcc-document__parse_document` 优先；`MinerU` 兜底
- 抽取字段：①公司基本情况 ②分产品/分行业收入 ③产品毛利率 ④募投项目 ⑤股东列表 ⑥专利明细 ⑦重大风险
- 缺任何字段 → 填 `未取得招股书` 而非 `以招股书为准`（硬性纪律 1 强化）

### Step 3 · 对比表生成（专题表 9-12 的核心）
- 4 个表的列结构必须根据对比双方**重新设计**，禁止套用上月模板（如"全形态龙头 vs 老牌视觉"用相同列会失真）
- 数字来源必须指向**招股书 PDF 的具体页码**（溯源.jsonl `source_file` + `source_page`）

### Step 4 · 专题报告 docx 输出
- 模板：`专题研究.skill/templates/专题报告模板.docx`（本期附简版示例）
- 章节：①摘要 ②公司画像 ③可比性分析 ④业务/技术对比 ⑤募投与财务对比 ⑥结论与对月报的影响

### Step 5 · 专题数据回填月报源文件
- 将专题表 9-12 的关键数字（如营收、净利、毛利率、募投项目金额）**回填**到月报 `下载资料/` 下对应源 CSV，并触发月报 Skill 跑一次 `consistency_check.py` + `cross_consistency_check.py`
- 不允许专题/月报出现"两份不同口径的数字"

### Step 6 · 专题独立门禁
| 门禁 | 含义 | 失败处置 |
| --- | --- | --- |
| `topic_check.py` | 对比双方至少 5 个可比维度有数字 | ❌ 不可比则不输出专题 |
| 专题数字 100% 来自招股书 PDF | `未取得招股书` ≤ 30%（其余字段必须可溯源） | 超阈值退回 Step 2 |
| 募投/分产品口径与月报口径一致 | 避免"专题≠月报" | 触发 Step 5 |

### Step 7 · subagent 优先，失败 2 次降级 mainagent
- 同 `industry-report-update` D 节兜底机制
- 专题通常 subagent 路径更多（招股书解析/可比性分析），需在 `config/agent_health.yaml` 单独计数

---

## 与 industry-report-update 的接口契约

### 输入
- `runs/<run-id>/通道健康度-<YYYYMM>.md`（必须有）
- `config/口径快照/<YYYYMM>.yaml`（必须有）
- `标的池.yaml`（必须有）
- 招股书 PDF（必须有，否则拒绝执行）

### 输出
- `专题-<对比对象>-<YYYYMM>.docx`
- `下载资料/专题-<对比对象>-<YYYYMM>.csv`（专题表 9-12 转写）
- `专题-降级日志-<YYYYMM>.md`（如专题步骤有降级）
- 月报 Skill 接收到的接口文件：`runs/<run-id>/专题-回填-<对比对象>.json`（含表 9-12 全部数字 → 月报 Step 7 写入）

---

## 硬性纪律（继承 + 专题特化）

继承 industry-report-update 全部硬性纪律。

专题特化：

1. **对比双方业务模式必须同构**（如都是"人形机器人量产化"或都是"协作机器人出海"）。全形态龙头 vs 老牌视觉龙头 这种错位比较禁止。
2. **专题表 9-12 必须基于招股书原文**，数字引用必须含 PDF 页码。`以招股书为准` 占位不允许。
3. **专题报告与月报的数字必须 100% 一致**。差异即视为口径漂移。
4. **专题概览节**（月报内的"专题章节") 只引用专题报告的**结论与关键数字**，不重复论述。
5. **专题溯源写两套**：专题报告内的溯源 + 月报引用处的溯源。
