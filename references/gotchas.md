# references/gotchas.md · 12 条避坑手册

> 来源：本 Skill 在 2026-07 ~ 2026-09 三次真实期执行中踩过的坑 + 同期 gfreport-renew-skill 与原始 industry-report-update v2.1 的实战沉淀。
> 原则：只收录"与合理假设相悖、且已实测"的环境事实。

---

## 高危坑（P0 · 必看）

### 1. 禁止 `cell.text = value` / `p.text = value` 覆写

**症状**：改写后字号丢失（变 inherit）、对齐/垂直居中丢失、首行缩进丢失、加粗/字体丢失

**根因**：`cell.text =` 重建 paragraph，会丢失原 `tcPr / pPr / rPr` 全部格式属性

**正解**：必须用 `docx_utils.set_cell_keep(cell, value)` 或 `set_para_keep(p, text)`

```python
from docx_utils import set_cell_keep, set_para_keep
set_cell_keep(cell, value)         # 单元格
set_para_keep(p, text)             # 段落
```

### 2. 必须用 v2 函数族

```python
from docx_utils import (
    set_cell_keep,       # 单元格：保留 run 结构
    fill_table,          # 表格回填：自动删多余/克隆补足
    strip_vmerge,        # 重填前清 vMerge 残留
    set_para_keep,       # 段落：首 run 写、其余清空
    add_row_copy_fmt,    # 新增行：克隆格式（含 gridSpan）
    set_para_segments_keep_fmt,  # 多格式 run 标题段
)
```

旧 API（`cell.text`、`add_paragraph`、`add_table`）会丢格式、不保留结构。

### 3. 删除残句用包含匹配，不用前缀匹配

**症状**：用 `startswith` 删除章节时残留半个字或半个 run

**正解**：用 `in` 包含匹配，或按完整段落删除

```python
# ❌ 错
if p.text.startswith("上月残句"):
    p._element.getparent().remove(p._element)

# ✅ 对
if "上月残句" in p.text:  # 包含匹配
    p._element.getparent().remove(p._element)
```

### 4. 锚点统一 CSV，不用 `.xls`/`xlsx`

**症状**：源文件是 `.xls` 后缀但实为 UTF-8 CSV 文本（如上交所 commonExcelKcb 导出的 `.xls`），用 `pd.read_excel` 报错

**正解**：用 `pd.read_csv(path)`（逗号分隔），不要用 `read_excel`

涉及源：上交所 SH_XM_LB / GP_ZRZ_XMLB / GP_BGCZ_XMLB

### 5. 申万指数码禁用 `wind_stock_data.get_stock_kline`

**症状**：`801742.SL`（申万二级行业指数）被误解析为个股，返回 7-9 元股价

**正解**：申万二级/一级指数一律用 `mx_index_block_finance_data`（mx-ds-mcp）

### 6. 工作区归档脚本不跑 = 未交付

**症状**：门禁全过、产出在 `runs/<run-id>/`，但用户找不到

**正解**：Step 9.5 必须执行 `archive_to_workspace.py`，全产出镜像到**当前对话工作区**

```bash
# 任何 harness 都可移植：用输入旧月报路径作锚点
python scripts/archive_to_workspace.py --run-id <run-id> --anchor "<旧月报路径>" --product "<产品名>"
```

---

## 中危坑（P1 · 必看）

### 7. 删除章节跳过 `<w:sectPr>`

**症状**：删除整个章节时把 `<w:sectPr>` 也删了 → 页边距丢失

**正解**：遍历 `<w:p>` 时跳过含 `<w:sectPr>` 的段落（页眉/页脚/分节符）

### 8. 锚点识别 CSV 列名

**症状**：CSV 列名"公司名" vs "公司简称" vs "公司全称" 不统一 → 键匹配失败

**正解**：

- 默认 `source_key` 在**首列**匹配
- 可用 `source_key_col` 指定列名（`--source-key-col 公司简称`）
- 键归一化启发式：去括号 / 去公司后缀 / 半角化

### 9. 数值回读单位识别

**症状**：`1亿元` vs `1万元`（同数字误判通过）

**正解**：`verify_value._UNITS` 按"币种 + 数量级"最长匹配

- `亿美元` ≠ `亿元`（必须先匹配币种）
- `1亿港元` vs `1亿元人民币`（币种不同）

### 10. 跨行 vMerge 复杂表门禁识别不到

**症状**：表头跨行 vMerge，门禁按"未知结构"标记

**正解**：落"未知结构"标记 → 由盲审人工复核

### 11. 子公司 vs 集团合并口径混用

**症状**：同表内"营业收入"字段，子公司报表口径 vs 集团合并报表口径不一致

**正解**：`口径字典.yaml` 中 `法人统一工商名` 强制规则（统一字段命名）

### 12. 港股 IPO 6 个月未聆讯 = 失效条目

**症状**：把 7 月递表的港股条目沿用到 12 月（已超过 6 个月），但旧月报口径把"基线 N 家"沿用

**正解**：

- 港股在审表加 `是否仍在 6 个月有效期内` 列（✅/❌ + 失效日期）
- 不允许"基线 - 变化"高估在审数
- `packs/robotics/RULES.md` 规则 1（具体行业包 RULES.md）

---

## 实战沉淀（补充）

### 13. 北交所 WAF 常态化

**症状**：ConnectionResetError 10054（连续多期）

**正解**：直接走公告/媒体核验，勿重试直连

### 14. 跨月转载合集必须做去重

**症状**：行业月度合集会把上月事件转载进本月

**正解**：

- `cross_month_dedup.py --old 旧月报.docx --candidates 候选.csv`
- 公告日 vs 转载日，±45 天窗口
- 盲审自检清单第 1 条为准

### 15. 内容重建模式下 03/06/07 必然失败

**症状**：从零重建 docx 时，`diff_empty / reasonableness_check / format_diff` 必然失败

**正解**：

- 默认硬失败 → 走 `build_report.py` 声明式引擎（基于旧月报复制 + 就地改写）
- 若必须重建 → 用 `--soft-gates` 显式降级（记 ⚠️ 转盲审，绝不静默放行）

### 16. PowerShell 下写中文脚本

**症状**：`python -c "print('中文')"` 引号/编码搅碎

**正解**：

- 一律用脚本文件，勿用 `-c` 内联
- console 打印中文先 `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`

### 17. subagent 通道连续失败 ≥3 次必须暂停

**症状**：模型路由问题，盲审子 Agent 反复失败

**正解**：

- ≥2 次降级 mainagent + 标注"独立性受损"
- ≥3 次暂停执行，提示人工检查模型路由
- 不允许主 Agent 静默接管后无标注

### 18. TOC 页码域

**症状**：TOC 页码仍是上月

**正解**：在 Word/WPS 中按 F9 刷新（脚本无法刷新）

### 19. 原生 OOXML 图表

**症状**：图表数据无法重算

**正解**：双轨制 —— 保留原图 + 图下脚注"数据截至 YYYY-MM，最新见表 X" + 对应数据表列为必更新项

### 20. docx 被 Word/WPS 占用

**症状**：脚本输出覆盖失败

**正解**：先输出 `.tmp.docx`，等用户关闭后覆盖

---

## 每月更新原则

新坑随期追加，**注明首遇期**。**不删旧坑**——保留作为历史教训。

```
2026-07：坑 1 / 2 / 3 / 4 / 7 / 8 / 10 / 11 / 13 / 18 / 20
2026-08：坑 5 / 6 / 9 / 14 / 15 / 16 / 17 / 19
2026-09：坑 12（港股 6 个月）
```

---

## 已知边界（如实声明）

- 避坑手册是"经验沉淀"，不是"自动门禁"
- 任何门禁脚本都有边界，必须配合盲审兜底
- 坑的复发率 = （本期是否落入坑）/ （历史落入坑次数）—— 新坑往往源于新通道/新工具接入