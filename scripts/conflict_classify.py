# -*- coding: utf-8 -*-
"""
conflict_classify.py —— 溯源 conflict 分级（Step 7 输出）

用途：
  对 溯源.jsonl 中 conflict 字段做关键词打分，按风险等级分组输出
    P1 = 涉资金/状态/日期冲突（必须人工复核）
    P2 = 估值/规模/口径冲突（次优先级）
    P3 = 纯口径差异/来源差异（仅供参考）

依赖：仅标准库
"""
import sys, os, json, datetime, re
from pathlib import Path

P1_KEYWORDS = ["募集", "发行价", "市盈率", "申报", "受理", "过会", "注册", "上市", "申购", "日期", "有效期", "失效", "估算"]
P2_KEYWORDS = ["估值", "规模", "市值", "金额", "份额", "轮次", "投资人", "实控人"]
P3_KEYWORDS = ["披露口径", "表述", "缩写", "简称", "WAF", "降级", "媒体", "未披露"]

def classify(text):
    t = text or ""
    if any(k in t for k in P1_KEYWORDS):
        return "P1"
    if any(k in t for k in P2_KEYWORDS):
        return "P2"
    return "P3"

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", help="溯源.jsonl 路径")
    ap.add_argument("--out", default="冲突分级报告.md")
    args = ap.parse_args()

    if not Path(args.jsonl).exists():
        print(f"❌ 找不到 {args.jsonl}")
        sys.exit(2)

    buckets = {"P1": [], "P2": [], "P3": [], "无冲突": []}
    n_total = 0
    with open(args.jsonl, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            conflict = row.get("conflict", "").strip()
            cell = row.get("cell", "?")
            value = str(row.get("value", ""))[:30]
            source = row.get("source_file", "?")
            n_total += 1
            if not conflict or conflict in ("-", "—", "无"):
                buckets["无冲突"].append((cell, value, source, ""))
                continue
            buckets[classify(conflict)].append((cell, value, source, conflict))

    out_lines = [
        f"# 溯源冲突分级报告（脚本：scripts/conflict_classify.py）",
        f"生成时间：{datetime.datetime.now().isoformat(timespec='seconds')}",
        f"数据源：{args.jsonl}",
        f"总记录数：{n_total}",
        "",
        "## 分级统计",
        f"- P1（涉资金/状态/日期，必须人工复核）：{len(buckets['P1'])}",
        f"- P2（估值/规模/口径，次优先级）：{len(buckets['P2'])}",
        f"- P3（纯口径差异/降级说明，参考）：{len(buckets['P3'])}",
        f"- 无冲突：{len(buckets['无冲突'])}",
        "",
        "## 处置建议",
        "- **P1**：进入下一份月报前必须人工复核（建议写在变更摘要的「缺口清单」中）。",
        "- **P2**：可在变更摘要的「残余风险」一栏简述。",
        "- **P3**：无需处置，作为口径说明随源文件归档。",
        "",
    ]
    for level in ("P1", "P2", "P3"):
        out_lines.append(f"## {level} 冲突明细（{len(buckets[level])} 条）")
        out_lines.append("| cell | value | source_file | conflict |")
        out_lines.append("| --- | --- | --- | --- |")
        for cell, value, source, conflict in buckets[level]:
            out_lines.append(f"| {cell} | {value} | {source} | {conflict[:120]} |")
        out_lines.append("")

    Path(args.out).write_text("\n".join(out_lines), encoding="utf-8")
    print(f"✅ 冲突分级报告：{args.out}")
    print(f"   P1={len(buckets['P1'])}  P2={len(buckets['P2'])}  P3={len(buckets['P3'])}  无冲突={len(buckets['无冲突'])}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
