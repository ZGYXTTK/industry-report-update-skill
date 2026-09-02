# evals/industry-report-update.eval.md · industry-report-update-skill 评估 spec

> 给 `scripts/run_evals.py` 消费的评估 spec。fixtures 正负双向冒烟，防止门禁误杀也防漏杀。

## 评估目标

1. **正向用例**（fixtures_positive/）：格式合规、数值一致、格式保真 ≥95%——必须全部通过 11 道门禁
2. **负向用例**（fixtures_negative/）：含幽灵条目 / 金额矛盾 / 格式退化——必须被对应门禁拦截
3. **门禁结构**：11 道门禁（9 主 + 2 扩展）必须全部跑通

## 评估套件结构

```
evals/
├── industry-report-update.eval.md   # 本文件（spec）
└── cases/
    ├── make_fixtures.py             # 生成 fixtures（正向 5 / 负向 2）
    ├── fixtures_positive/
    │   ├── old.docx                 # 旧月报（合规）
    │   ├── new.docx                 # 新月报（保真改写 + 数值正确）
    │   ├── sources/
    │   │   ├── 章节-上交所.csv
    │   │   └── 章节-深交所.csv
    │   └── 溯源.jsonl               # 带锚点
    ├── fixtures_negative/
    │   ├── ghost_entity.docx        # 含幽灵条目（不应出现）
    │   └── value_mismatch.docx      # 月报数字 ≠ 源 CSV
    └── ...
```

## 评估用例（详细）

### 正向用例（5 个，必须全部 ✅）

| # | 输入 | 期望 |
| --- | --- | --- |
| 1 | `fixtures_positive/old.docx` + `new.docx` + `溯源.jsonl` | 9 道门禁 ✅ 不误杀 |
| 2 | 同一对 + 无 `--roster-note` 变更摘要 | 6 道硬门禁 ✅；3 道软门禁（03/06/07）有 ⚠️ 但不阻断 |
| 3 | 同一对 + `--soft-gates 03_diff_empty,06_reasonableness_check,07_format_diff` | 全部 ✅（软门禁显式降级） |
| 4 | 同一对 + `--resume`（首次 --resume 跳过已通过门禁） | 第二次跑 ✅（无重复门禁输出） |
| 5 | 跨月迁移：用上月 new.docx 作"旧"，用新 new.docx 作"新" | 9 道门禁 ✅（格式保真可迁移） |

### 负向用例（2 个，必须被对应门禁拦截）

| # | 输入 | 期望 | 拦截门禁 |
| --- | --- | --- | --- |
| 1 | `fixtures_negative/ghost_entity.docx` | ❌ 必须失败 | `cross_consistency_check.py`（"共 N 家" ≠ 表格行数） |
| 2 | `fixtures_negative/value_mismatch.docx` + `溯源_mismatch.jsonl` | ❌ 必须失败 | `verify_value.py`（月报数字 ≠ 源 CSV） |

## 门禁断言

### 硬门禁（11 道，失败即阻断）

| # | 门禁 | 命令 | 期望 |
| --- | --- | --- | --- |
| 1 | 数字提取 | `audit/extract_numbers.py 旧.docx` | exit 0，输出数字清单 |
| 2 | 配置校验 | `audit/config_check.py` | exit 0，无 ERROR |
| 3 | 空值 diff | `audit/diff_empty.py 旧.docx 新.docx --key-col-name 公司简称` | exit 0（无"旧有值→新空值"） |
| 4 | 一致性 | `audit/consistency_check.py 新.docx` | exit 0（合计 = 分项和） |
| 5 | 交叉一致性 | `audit/cross_consistency_check.py 新.docx` | exit 0（正文"共 N 家" = 表格行数） |
| 6 | 合理性 | `audit/reasonableness_check.py 旧.docx 新.docx --roster-note 变更摘要.md` | exit 0（环比/名单已交代） |
| 7 | 格式对比 | `audit/format_diff.py 旧.docx 新.docx --threshold 0.95` | exit 0（相似度 ≥ 0.95） |
| 8 | 数值回读 | `audit/verify_value.py 溯源.jsonl --base-dir 下载资料` | exit 0（月报数字 = 源 CSV） |
| 9 | 溯源反查 | `audit/traceability_check.py 溯源.jsonl --min-coverage 0.9 --require-cross-check` | exit 0（覆盖率 ≥ 90% + 交叉验证） |
| 10 | 锚点自检 | `audit/anchor_check.py 溯源.jsonl` | exit 0（dry-run 无 anchor 错误） |
| 11 | 跨月去重 | `audit/cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv` | exit 0（无转载重复） |

### 软门禁（可选降级）

`--soft-gates` 显式降级（记 ⚠️ 转盲审，绝不静默放行）：
- `03_diff_empty`：从零重建 docx 时必然失败
- `06_reasonableness_check`：从零重建时无对比基线
- `07_format_diff`：从零重建时无格式基线

降级失败 → 转盲审人工复核

## 评分公式

```
score = (正向 ✅ 数 / 5) × 0.6 + (负向 ❌ 拦截数 / 2) × 0.4
```

| 分数 | 状态 |
| --- | --- |
| ≥ 0.95 | ✅ 一切就绪 |
| 0.80 ~ 0.95 | 🟡 可发布但需修复 |
| < 0.80 | ❌ 不可发布 |

## 已知边界的"已知"标签

每个 fixture 必须显式声明它"测试什么 / 不测试什么"：

- **format_diff** 测 rPr/pPr/gridSpan 签名比对，不测图表视觉差异 → 含图表 fixture 需人工复核
- **verify_value** 测"月报数字 = 源 CSV"，不测源 CSV 本身 → 源数据权威性靠 Step 2 映射纪律
- **diff_empty** 启发式键归一化（去括号/去公司后缀），极端同名异写漏网 → 盲审兜底

## 执行方式

```bash
# 1. 生成 fixtures
python evals/cases/make_fixtures.py

# 2. 跑评估
python scripts/run_evals.py --rollout

# 3. 推广为基线（首次绿色）
python scripts/run_evals.py --promote

# 4. 对比基线（防回归）
python scripts/run_evals.py --rollout --against-baseline
```

## 已知失败模式（如实记录）

跑过 N 期后，以下模式可能未覆盖：
- 跨月转版（如旧 docx 是 2019 模板，新 docx 是 2026 模板）→ 格式 diff 必然失败
- 多语言（中英双语月报）→ cross_consistency 中文「共 N 家」vs 英文"total N companies"
- 巨型表格（> 1000 行）→ 性能问题（脚本需 ≥30 秒）

如发现新失败模式，记录到本文件末尾"扩展用例"段。