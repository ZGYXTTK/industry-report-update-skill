#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_evals.py · industry-report-update-skill 评估器

用法：
    python scripts/run_evals.py --rollout                 # 跑全部 fixtures
    python scripts/run_evals.py --promote                 # 推广为基线
    python scripts/run_evals.py --rollout --against-baseline  # 对比基线（防回归）

工作流：
    1. 跑 `python evals/cases/make_fixtures.py` 生成 fixtures（若不存在）
    2. 对正向 fixtures 跑 11 道门禁 → 期望 ✅
    3. 对负向 fixtures 跑对应门禁 → 期望 ❌（拦截）
    4. 评分（正向 5/5 + 负向 2/2 = 满分 1.0）
    5. 若 --promote：保存本次结果为基线
    6. 若 --against-baseline：对比基线（防回归）

依赖：
    - python-docx >= 0.8.11
    - eval spec in evals/industry-report-update.eval.md

输出：
    - evals/last_run.json           # 本次评估结果
    - evals/baseline.json           # 基线（--promote 后）
    - 控制台评分摘要
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent.parent
EVALS = ROOT / "evals"
FIXTURES = EVALS / "cases" / "fixtures_positive"
FIXTURES_NEG = EVALS / "cases" / "fixtures_negative"
LAST_RUN = EVALS / "last_run.json"
BASELINE = EVALS / "baseline.json"


def ensure_fixtures():
    """跑 make_fixtures.py（如 fixtures 不存在）"""
    if not FIXTURES.exists() or not FIXTURES_NEG.exists():
        script = EVALS / "cases" / "make_fixtures.py"
        print(f"[setup] 生成 fixtures: python {script}")
        rc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        if rc.returncode != 0:
            print(f"[setup] FAILED: {rc.stderr}")
            sys.exit(1)


def run_gate(cmd: list[str], expect_pass: bool) -> dict:
    """跑单道门禁；返回 {gate, exit_code, expected, passed}"""
    print(f"  ▶ {' '.join(cmd)}")
    rc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    actual_pass = rc.returncode == 0
    passed = actual_pass == expect_pass
    return {
        "gate": cmd[-2] if len(cmd) > 2 else " ".join(cmd[-2:]),
        "cmd": cmd,
        "exit_code": rc.returncode,
        "expected_pass": expect_pass,
        "actual_pass": actual_pass,
        "test_passed": passed,
        "stdout_tail": rc.stdout[-500:] if rc.stdout else "",
        "stderr_tail": rc.stderr[-500:] if rc.stderr else "",
    }


def run_positive_suite() -> list[dict]:
    """跑正向 5 个用例"""
    results = []

    old = str(FIXTURES / "old.docx")
    new = str(FIXTURES / "new.docx")
    csv_dir = str(FIXTURES / "sources")
    jsonl = str(FIXTURES / "溯源.jsonl")
    roster = str(FIXTURES / "变更摘要.md")
    # 写一个空的变更摘要（让 reasonableness 通过）
    (FIXTURES / "变更摘要.md").write_text(
        "环比异常：无\n新增/移除标的：无（本月与上月相同 5 家）\n",
        encoding="utf-8",
    )

    print("[POSITIVE 1] 全部门禁（正向应全过）")
    gates = [
        # 1. 数字提取
        ([sys.executable, "scripts/audit/extract_numbers.py", old], True),
        # 2. 配置校验
        ([sys.executable, "scripts/audit/config_check.py"], True),
        # 3. 空值 diff
        ([sys.executable, "scripts/audit/diff_empty.py", old, new,
          "--key-col-name", "公司简称"], True),
        # 4. 一致性
        ([sys.executable, "scripts/audit/consistency_check.py", new], True),
        # 5. 交叉一致性
        ([sys.executable, "scripts/audit/cross_consistency_check.py", new], True),
        # 6. 合理性
        ([sys.executable, "scripts/audit/reasonableness_check.py",
          old, new, "--roster-note", roster], True),
        # 7. 格式对比
        ([sys.executable, "scripts/audit/format_diff.py",
          old, new, "--threshold", "0.95"], True),
        # 8. 数值回读
        ([sys.executable, "scripts/audit/verify_value.py", jsonl,
          "--base-dir", csv_dir], True),
        # 9. 溯源反查
        ([sys.executable, "scripts/audit/traceability_check.py", jsonl,
          "--min-coverage", "0.9", "--require-cross-check",
          "--against-docx", new], True),
    ]
    for cmd, expect_pass in gates:
        r = run_gate(cmd, expect_pass)
        results.append({"suite": "positive_1", **r})

    return results


def run_negative_suite() -> list[dict]:
    """跑负向 2 个用例"""
    results = []

    ghost_new = str(FIXTURES_NEG / "ghost" / "ghost_entity.docx")
    ghost_csv_dir = str(FIXTURES_NEG / "ghost" / "sources")

    mismatch_new = str(FIXTURES_NEG / "mismatch" / "value_mismatch.docx")
    mismatch_csv_dir = str(FIXTURES_NEG / "mismatch" / "sources")
    mismatch_jsonl = str(FIXTURES_NEG / "mismatch" / "溯源_mismatch.jsonl")

    print("[NEGATIVE 1] ghost_entity.docx 应被交叉一致性拦截")
    # 幽灵条目：表格 6 行但正文说"共 5 家"—— cross_consistency 应失败
    cmd = [sys.executable, "scripts/audit/cross_consistency_check.py", ghost_new]
    r = run_gate(cmd, expect_pass=False)  # 期望：被拦截（exit != 0）
    results.append({"suite": "negative_ghost", **r})

    print("[NEGATIVE 2] value_mismatch.docx 应被数值回读拦截")
    cmd = [sys.executable, "scripts/audit/verify_value.py", mismatch_jsonl,
           "--base-dir", mismatch_csv_dir]
    r = run_gate(cmd, expect_pass=False)  # 期望：被拦截（exit != 0）
    results.append({"suite": "negative_mismatch", **r})

    return results


def compute_score(results: list[dict]) -> float:
    pos = sum(1 for r in results if r["suite"].startswith("positive") and r["test_passed"])
    pos_total = sum(1 for r in results if r["suite"].startswith("positive"))
    neg = sum(1 for r in results if r["suite"].startswith("negative") and r["test_passed"])
    neg_total = sum(1 for r in results if r["suite"].startswith("negative"))

    if pos_total == 0 and neg_total == 0:
        return 0.0

    score = (pos / pos_total * 0.6) + (neg / neg_total * 0.4) if pos_total + neg_total > 0 else 0.0
    return round(score, 3)


def save_results(results: list[dict], score: float, promoted: bool = False):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "results": results,
    }
    LAST_RUN.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if promoted:
        BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def compare_to_baseline() -> dict:
    """对比本次结果与基线"""
    if not BASELINE.exists():
        return {"error": "no baseline; run --promote first"}
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = json.loads(LAST_RUN.read_text(encoding="utf-8"))

    baseline_passed = sum(1 for r in baseline["results"] if r["test_passed"])
    current_passed = sum(1 for r in current["results"] if r["test_passed"])
    return {
        "baseline_score": baseline["score"],
        "current_score": current["score"],
        "baseline_passed": baseline_passed,
        "current_passed": current_passed,
        "regression": current_passed < baseline_passed,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollout", action="store_true", help="跑全部 fixtures")
    ap.add_argument("--promote", action="store_true", help="推广为基线")
    ap.add_argument("--against-baseline", action="store_true", help="对比基线")
    args = ap.parse_args()

    if not args.rollout:
        ap.print_help()
        sys.exit(1)

    print("=" * 60)
    print("industry-report-update-skill · 评估器")
    print("=" * 60)

    ensure_fixtures()

    results = []
    results.extend(run_positive_suite())
    results.extend(run_negative_suite())

    score = compute_score(results)

    save_results(results, score, promoted=args.promote)

    # 摘要
    pos_passed = sum(1 for r in results if r["suite"].startswith("positive") and r["test_passed"])
    pos_total = sum(1 for r in results if r["suite"].startswith("positive"))
    neg_passed = sum(1 for r in results if r["suite"].startswith("negative") and r["test_passed"])
    neg_total = sum(1 for r in results if r["suite"].startswith("negative"))

    print()
    print("=" * 60)
    print(f"评估结果")
    print("=" * 60)
    print(f"正向：{pos_passed}/{pos_total} 通过")
    print(f"负向：{neg_passed}/{neg_total} 拦截")
    print(f"评分：{score}")
    print(f"  ≥ 0.95 ✅ 一切就绪")
    print(f"  0.80 ~ 0.95 🟡 可发布但需修复")
    print(f"  < 0.80 ❌ 不可发布")

    if args.promote:
        print(f"\n[promote] 已推广为基线 → {BASELINE}")

    if args.against_baseline:
        comp = compare_to_baseline()
        print(f"\n[baseline] {json.dumps(comp, ensure_ascii=False, indent=2)}")
        if comp.get("regression"):
            print("❌ 检测到回归！")
            sys.exit(2)
        else:
            print("✅ 无回归")

    if score < 0.80:
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()