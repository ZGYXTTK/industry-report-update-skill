# docs/EXAMPLES.md · industry-report-update-skill 修改示例

> 8 个扩展示例，覆盖最常见的"本 Skill 出厂后用户需要自定义"场景。
> 每个示例包含：场景 → 完整命令 → 改了什么 → 验证方法。

---

## 示例 1 · 新建行业包（从零）

**场景**：你负责"医疗设备"赛道月报，旧月报是 `D:/reports/医疗设备2026.8.docx`。

**步骤**：

```bash
# 1. 用旧月报反推行业骨架
python scripts/pack.py wizard D:/reports/医疗设备2026.8.docx --name medtech
# → 生成 packs/medtech/ 目录（5 YAML + RULES.md，均含 TODO 标记）

# 2. 人工补完 packs/medtech/下的 5 个 YAML：
#    标的池.yaml  ：列出 N 家医疗设备赛道公司（逐家人工判断）
#    口径字典.yaml：定义 "III 类医疗器械" 等口径
#    采集清单.yaml：列出 采集项 id + 通道 + 类型
#    权威源映射.yaml：本赛道特有字段维度权威源
#    时点对齐策略.yaml：本赛道特有跨源时点对齐规则

# 3. 激活新行业包（自动备份旧 config/ 到 config/_backup/）
python scripts/pack.py activate medtech

# 4. 落盘本期快照
python scripts/snapshot.py snapshot --ym 2026-09 --run-id medtech-20260901
```

**验证**：

```bash
ls packs/medtech/        # 应有 5 YAML + RULES.md
ls config/               # 应有 5 YAML（与 packs/medtech/ 同名同结构）
python scripts/pack.py list   # medtech 应标 ✅
```

---

## 示例 2 · 新增采集项（IPO/科创板/已发行）

**场景**：原 `采集清单.yaml` 只有"在审"，现在要加"已发行"。

**步骤**：

1. 编辑 `packs/<行业>/采集清单.yaml`，新增：
```yaml
- id: "IPO/科创板/已发行"
  章节: "资本市场动态"
  类型: "时点型"
  通道: "上交所科创板IPO"
  枚举: true
  输出: ["公司简称", "发行价", "募资金额", "发行日期"]
  来源: "CSV"
```

2. 同步更新 `packs/<行业>/口径字典.yaml` 的 `采集通道`（如已有则跳过）：
```yaml
上交所科创板IPO:
  endpoint: "query.sse.com.cn/commonExcelKcb.do?sqlId=SH_XM_LB"
  过滤: "筛『已发行』状态"  # ← 改过滤
```

3. 重新落盘快照：
```bash
python scripts/snapshot.py snapshot --ym <YYYY-MM> --run-id <run-id>
```

4. 跑门禁：
```bash
python scripts/audit/config_check.py
# 应输出："✅ 新增项 IPO/科创板/已发行 通道合法"
```

**验证**：

```bash
python scripts/run.py 旧月报.docx 新月报.docx --jsonl 溯源.jsonl ...
# config_check 门禁 ✅；其他门禁按新增项重测
```

---

## 示例 3 · 新增门禁（"图表已更新"）

**场景**：你想新增一道门禁"图表已更新"——确保所有原生 OOXML 图表的图注都有"数据截至 YYYY-MM"。

**步骤**：

1. 创建 `scripts/audit/chart_updated.py`：

```python
"""图表已更新门禁：所有 OOXML 图表的图注必须含 '数据截至 YYYY-MM'"""
import re
from docx import Document

def check_chart_caption(docx_path, target_ym):
    doc = Document(docx_path)
    issues = []
    # 检查图注段落（含 "图 1:" / "图1：" / "图表 N" 等关键字）
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if re.match(r'^(图|图表)\s*\d+', text):
            if f"数据截至 {target_ym}" not in text and f"数据截至 {target_ym[:4]}-{target_ym[4:]}" not in text:
                issues.append(f"段落 {i+1}: 图注缺『数据截至 {target_ym}』: {text}")
    return issues

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--ym", required=True, help="目标时点 YYYYMM")
    args = ap.parse_args()
    issues = check_chart_caption(args.docx, args.ym)
    if issues:
        for x in issues: print(f"❌ {x}")
        exit(1)
    print("✅ 图表已更新")
```

2. 在 `scripts/run.py` 注册（伪代码）：
```python
# run.py 里追加
gates.append({
    "name": "chart_updated",
    "cmd": ["python", "scripts/audit/chart_updated.py", "新.docx", "--ym", args.ym],
    "blocking": True,
})
```

3. 在 `SKILL.md` 门禁速查表追加一行。

**验证**：

```bash
python scripts/audit/chart_updated.py 新月报.docx --ym 202608
# 应输出："✅ 图表已更新"
```

---

## 示例 4 · 新增端点（北交所并购重组）

**场景**：`endpoints.yaml` 缺北交所并购重组端点。

**步骤**：

1. 编辑 `config/endpoints.yaml` 的 `http通道`：
```yaml
- name: 北交所并购重组
  url: "https://www.bse.cn/projectNewsController/infoResult.do?bizType=3"
  method: POST
  kind: json
  headers:
    Referer: "https://www.bse.cn/"
    Content-Type: "application/x-www-form-urlencoded"
  body:
    page: "1"
  note: "WAF 已知问题，失败时走媒体降级"
```

2. 在 `packs/<行业>/口径字典.yaml` 的 `采集通道` 追加：
```yaml
北交所并购重组:
  endpoint: "bse.cn/projectNewsController/infoResult.do?bizType=3"
  注意: "WAF 已知问题"
```

3. 在 `packs/<行业>/采集清单.yaml` 引用新端点：
```yaml
- id: "并购重组/北交所"
  章节: "资本市场动态"
  类型: "时点型"
  通道: "北交所并购重组"  # ← 引用新通道名
  枚举: true
  输出: ["公司简称", "交易类型", "审核状态"]
  来源: "CSV"
```

4. 重新落盘快照 + 跑门禁。

**验证**：

```bash
python scripts/channel_health_check.py --ym <YYYY-MM> --run-id <run-id>
# 应输出："✅ 北交所并购重组"
```

---

## 示例 5 · 新增工具盘点源（聚合类 MCP）

**场景**：你新装了 `mcp__xxx-registry__discover`，必须加入 `tool_registry.yaml`。

**步骤**：

1. 编辑 `config/tool_registry.yaml` 的 `信息源`：
```yaml
信息源:
  - name: xxx-registry
    kind: registry  # ← 关键：聚合类必须标 registry
    discover: mcp__xxx-registry__discover
    call: mcp__xxx-registry__call
    说明: "聚合类 MCP，先 discover 再 call；按量计费"
```

2. Step 2 工具盘点时执行 `discover`：
```bash
# Agent 在 Step 2 必跑：
python scripts/tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl
```

3. 在 `runs/<run-id>/sources/工具清单.jsonl` 追加：
```json
{"source":"xxx-registry","kind":"registry","present":true,"smoke":"ok","discovered":true,"found_tools":["mcp__xxx-registry__tool1","mcp__xxx-registry__tool2"]}
```

**验证**：

```bash
python scripts/tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl
# 应输出："✅ 聚合器已探查：xxx-registry (found 2 tools)"
```

---

## 示例 6 · 修复"运行 docx 被占用"

**场景**：Word 打开了 `新月报.docx`，脚本无法覆盖。

**处置**：

1. 脚本自动输出到 `.tmp.docx`
2. 用户在 Word 中关闭文件
3. 用户手动 `Move-Item 新月报.tmp.docx 新月报.docx`

**预防**：在脚本中加自动重试逻辑（`scripts/docx_build.py` 已实现）。

---

## 示例 7 · 跨月复用配置

**场景**：每月只需改"截至日期"。

**步骤**：

1. 9 月改 `packs/<行业>/口径字典.yaml` 的 `目标时点.规则`：
```yaml
目标时点:
  规则: "2026-09-30 23:59:59（默认本月最后一天）"
```

2. 9 月改 `packs/<行业>/采集清单.yaml` 的每条 `id` 加 `截至` 字段：
```yaml
- id: "IPO/科创板/在审"
  ...
  截至: "2026-09-30"  # ← 新增
```

3. 落盘快照 + 跑门禁：
```bash
python scripts/snapshot.py snapshot --ym 2026-09 --run-id <run-id>
python scripts/run.py 旧月报.docx 新月报.docx ... --out-dir runs/<run-id>/logs
```

---

## 示例 8 · 评估 fixtures（防回归）

**场景**：跑 `run_evals.py --rollout` 验证门禁不误杀也不漏杀。

**步骤**：

```bash
# 生成 fixtures
python evals/cases/make_fixtures.py
# → 生成 evals/cases/fixtures_positive/ (new.docx 格式正确)
# → 生成 evals/cases/fixtures_negative/ghost_entity.docx (含幽灵条目)
# → 生成 evals/cases/fixtures_negative/value_mismatch.docx (金额矛盾)

# 跑评估
python scripts/run_evals.py --rollout
# 应输出：
#   正向 5/5 ✅ 不误杀
#   负向 2/2 ❌ 已拦截
#   门禁结构 9+ 道全 ✓

# 推广为基线（首次绿色）
python scripts/run_evals.py --promote

# 后续对比基线（防回归）
python scripts/run_evals.py --rollout --against-baseline
```

**验证**：

```bash
# 应输出："✅ all gates pass" + "fixtures: 5 positive / 2 negative / 9+ gates"
```

---

## 反推案例（行业包 wizard）

**场景**：用旧月报 docx 反推行业骨架。

**输入**：`旧月报.docx`（任一行业的月报）

**输出**：`packs/<反推名>/` 目录，含 5 YAML + RULES.md + README.md

**关键点**：
- 反推结果为**候选召回骨架**，标的需逐家人工判断是否属于赛道后才能启用
- 反推名 = 行业名（英文/拼音），如 `medtech` / `consumer-electronics` / `new-energy`

---

## 跨月口径漂移（深 diff ≥3 项暂停）

**场景**：9 月跑 `snapshot.py diff` 发现 ≥3 项差异。

**处置**：

1. 看 `口径快照/2026-08.yaml` vs `口径快照/2026-09.yaml`
2. 差异项（如新增赛道、新增采集通道）必须用户确认后才能继续
3. 在变更摘要中说明哪些字段改了
