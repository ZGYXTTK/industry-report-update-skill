# -*- coding: utf-8 -*-
"""
run.py —— 统一入口 v2（P1-6：真·一键全部门禁 + 断点续跑）

v2 相对 v1 的修正：
  1. 收编 v1 漏掉的 config_check / traceability_check，并接入 P0 新增的
     reasonableness_check（环比异常+名单交代）与 verify_value（数值回读）——
     「一键」现在真的是全部门禁；
  2. 断点续跑：每道门禁结果落盘 --state-file（默认 <out-dir>/门禁状态.json），
     中断后加 --resume 自动跳过已通过的门禁，长流程不再前功尽弃；
  3. Windows 下全链路 UTF-8（沿用 v1）。

用法:
    python scripts/run.py 旧月报.docx 新月报.docx \
        [--key-col-name 公司简称] [--threshold 0.95] \
        [--jsonl 溯源.jsonl] [--base-dir 下载资料] [--roster-note 变更摘要.md] \
        [--out-dir runs/<run-id>/logs] [--resume]
退出码：任一硬门禁失败 → 1；全部通过 → 0。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, 'audit')
BASE = os.path.dirname(HERE)  # skill 基目录


def _derive_run_dir(out_dir):
    """从 --out-dir 反推 run 目录：runs/<run-id>/logs → runs/<run-id>；runs/<run-id> → 自身。
    无法识别（非 runs/ 结构）时返回 None，跳过流程前置门禁（ad-hoc 用法）。"""
    p = os.path.abspath(out_dir)
    if os.path.basename(p) == 'logs':
        p = os.path.dirname(p)
    if os.path.basename(os.path.dirname(p)) == 'runs':
        return p
    return None


def _process_precheck(out_dir, run_id=None, release=False, skip=False):
    """流程前置门禁（P0 #15 专题主题按月重选 + Step 1/4/8 落地，fail-closed）：
    软性流程步骤（征询意见/盲审/口径快照）不能靠 agent 自觉，改为机器硬拦截——缺失即 exit 1。
    定位 run 目录：--run-id 优先，其次从 --out-dir 反推；两者都失败 → 硬拦截（除非显式 --skip-process-gate）。
    只做「结构化标记」校验（存在 + 含固定关键词），不做语义判真——语义真伪由独立盲审/人工把关（见 SKILL Step 9.6）。
    """
    if skip:
        print('⚠️  已显式 --skip-process-gate，跳过流程前置门禁（仅限 ad-hoc，正式交付禁用）')
        return 0
    run_dir = None
    if run_id:
        r = os.path.join(BASE, 'runs', run_id)
        if os.path.isdir(r):
            run_dir = r
    if run_dir is None:
        run_dir = _derive_run_dir(out_dir)
    if run_dir is None:
        print('❌ 流程前置门禁无法定位 run 目录（--run-id 未给/无效，--out-dir 亦非 runs/<run-id>/logs）')
        print('   正式交付必须显式传 --run-id；确为 ad-hoc 快检请显式传 --skip-process-gate')
        return 1
    rid = os.path.basename(run_dir)
    yyyy_mm = rid[:7] if (len(rid) >= 7 and rid[4] == '-') else ''
    missing = []
    if yyyy_mm:
        snap = os.path.join(BASE, 'config', '口径快照', '%s.yaml' % yyyy_mm)
        if not (os.path.exists(snap) and os.path.getsize(snap) > 0):
            missing.append('Step 1 口径快照：%s 不存在（先跑 scripts/snapshot.py snapshot --ym %s）'
                           % (snap, yyyy_mm))
    else:
        missing.append('Step 1 口径快照：run-id 前缀非 YYYY-MM-*，无法定位快照（run-id=%s）' % rid)
    confirm = os.path.join(run_dir, 'input', '用户确认.md')
    if not (os.path.exists(confirm) and os.path.getsize(confirm) > 0):
        missing.append('Step 4 征询意见：%s 不存在（先落盘确认清单，禁止跳过用户确认）' % confirm)
    else:
        with open(confirm, encoding='utf-8') as f:
            if '专题主题' not in f.read():
                missing.append('Step 4 征询意见：%s 未含「专题主题」确认项（禁止沿用上月主题，须经使用者选择）' % confirm)
    if release:
        review = os.path.join(run_dir, 'reviews', '独立审核意见.md')
        if not (os.path.exists(review) and os.path.getsize(review) > 0):
            missing.append('Step 8 独立盲审：%s 不存在（禁止跳过盲审）' % review)
        else:
            with open(review, encoding='utf-8') as f:
                rt = f.read()
            if not any(k in rt for k in ('通过', 'PASS', '阻断', '🔴', '🟡', '返工')):
                missing.append('Step 8 独立盲审：%s 未含审核结论标记（通过/阻断/返工）' % review)
    if missing:
        print('❌ 流程前置门禁未通过（软性流程步骤不得跳过；机器只验结构，语义真伪由盲审/人工把关）：')
        for m in missing:
            print('   - ' + m)
        return 1
    return 0


def _run(args, label):
    print('\n===== %s =====' % label, flush=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    r = subprocess.run([sys.executable] + args, env=env)
    return r.returncode


def _load_state(path):
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(path, state):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old_docx')
    ap.add_argument('new_docx')
    ap.add_argument('--threshold', default='0.95')
    ap.add_argument('--key-col-name', default='',
                    help='diff_empty/reasonableness 的键列名（留空则按表头自动识别业务键，勿传固定「公司简称」——'
                         '2026-09 修复：固定值会覆盖 diff_empty 的 _AUTO_KEY_NAMES 按表自动识别，导致行业动态表退回序号对齐）')
    ap.add_argument('--jsonl', default=None, help='溯源.jsonl（提供则跑 verify_value + traceability）')
    ap.add_argument('--base-dir', default=None, help='源文件锚定目录（默认取 jsonl 所在目录）')
    ap.add_argument('--roster-note', default=None, help='变更摘要.md（提供则跑 reasonableness + structure_diff 结构删减交代校验）')
    ap.add_argument('--candidates', default=None, help='本期候选名单 CSV/JSONL（提供则跑 cross_month_dedup 跨月去重，阻断级）')
    ap.add_argument('--old-period', default=None, help='上月周期（YYYY-MM，cross_month_dedup --names 模式用）')
    ap.add_argument('--jump-threshold', default='0.5')
    ap.add_argument('--min-coverage', default='0.9',
                    help='溯源反查最低覆盖率（默认 0.9；100% 为理想值，docx 含日期/序号等非溯源辅助单元格，按 0.9 验收 + 报告列未覆盖清单）')
    ap.add_argument('--inventory', default=None,
                    help='Step 2 工具清单.jsonl 路径（提供则额外跑 tool_inventory.py 机检，阻断级）')
    ap.add_argument('--tool-registry', default=None,
                    help='tool_inventory 使用的注册表（默认 config/tool_registry.yaml）')
    ap.add_argument('--out-dir', default='.')
    ap.add_argument('--state-file', default=None)
    ap.add_argument('--resume', action='store_true', help='跳过此前已通过的门禁')
    ap.add_argument('--release', action='store_true',
                    help='最终交付门禁：除数据门禁外，额外校验 Step 8 独立盲审意见已落盘（交付前必加）')
    ap.add_argument('--run-id', default=None,
                    help='运行 ID（如 2026-08-robotics-r3）；流程前置门禁用它定位 runs/<run-id>，优先于 --out-dir 反推')
    ap.add_argument('--skip-process-gate', action='store_true',
                    help='显式跳过流程前置门禁（仅限 ad-hoc 快检；正式交付禁用）')
    ap.add_argument('--only', default=None,
                    help='仅跑指定门禁（逗号分隔，如 "consistency,verify_value"）——'
                         '单项内容修改后的快速验证（P1-3），不再全量轮转')
    args = ap.parse_args()

    out = args.out_dir
    os.makedirs(out, exist_ok=True)
    # P0 #15 流程前置门禁：征询意见/口径快照/盲审 缺失即硬拦截（先于数据门禁执行）；
    # --only 为单项快检，豁免前置门禁（降级为提示）
    if args.only:
        print('⚠️  --only 快检模式：跳过流程前置门禁（仅验单项数据门禁，不视为交付）')
    elif _process_precheck(out, run_id=args.run_id, release=args.release,
                           skip=args.skip_process_gate):
        sys.exit(1)
    state_file = args.state_file or os.path.join(out, '门禁状态.json')
    state = _load_state(state_file) if args.resume else {}

    base_dir = args.base_dir or (os.path.dirname(os.path.abspath(args.jsonl)) if args.jsonl else None)

    # 空值 diff：键列名留空时让 diff_empty 按表头自动识别业务键（勿退回序号）
    diff_empty_cmd = [os.path.join(AUDIT, 'diff_empty.py'), args.old_docx, args.new_docx]
    if args.key_col_name:
        diff_empty_cmd += ['--key-col-name', args.key_col_name]
    diff_empty_cmd += ['--out', os.path.join(out, '空值对比报告.md')]

    # 章节完整性：--jsonl 提供时，正文否定式结论（无/没有/未）须带 is_negative 证据
    section_cmd = [os.path.join(AUDIT, 'section_completeness.py'), args.new_docx]
    if args.jsonl:
        section_cmd += ['--jsonl', args.jsonl]
    section_cmd += ['--out', os.path.join(out, '章节完整性报告.md')]

    # 结构 diff：--roster-note 提供时，删章节/删表须在变更摘要交代，否则硬拦截
    structure_diff_cmd = [os.path.join(AUDIT, 'structure_diff.py'), args.old_docx, args.new_docx]
    if args.roster_note:
        structure_diff_cmd += ['--roster-note', args.roster_note]
    structure_diff_cmd += ['--out', os.path.join(out, '结构对比报告.md')]

    # 跨月去重：候选名单 vs 上月报告（采集后，Step 5 已跑；此处提供 --candidates 时补跑一次）
    dedup_cmd = None
    if args.candidates:
        dedup_cmd = [os.path.join(AUDIT, 'cross_month_dedup.py'), '--old', args.old_docx,
                     '--candidates', args.candidates]
        if args.old_period:
            dedup_cmd += ['--old-period', args.old_period]
        dedup_cmd += ['--out', os.path.join(out, '去重报告.md')]

    # (名称, 命令, 是否硬门禁)
    steps = [
        ('extract_numbers',
         [os.path.join(AUDIT, 'extract_numbers.py'), args.old_docx,
          '--out', os.path.join(out, '结论性语句清单.md'),
          '--json', os.path.join(out, '结论.jsonl')], False),
        ('config_check',
         [os.path.join(AUDIT, 'config_check.py'),
          '--out', os.path.join(out, '配置校验报告.md')], True),
        ('section_completeness', section_cmd, True),
        ('field_completeness',
         [os.path.join(AUDIT, 'field_completeness.py'), args.new_docx,
          '--out', os.path.join(out, '字段完整性报告.md')], True),
        ('diff_empty', diff_empty_cmd, True),
        ('consistency',
         [os.path.join(AUDIT, 'consistency_check.py'), args.new_docx,
          '--out', os.path.join(out, '一致性校验报告.md')], True),
        ('cross_consistency',
         [os.path.join(AUDIT, 'cross_consistency_check.py'), args.new_docx,
          '--out', os.path.join(out, '交叉一致性报告.md')], True),
        ('structure_diff', structure_diff_cmd, True),
    ]
    if dedup_cmd:
        steps.append(('cross_month_dedup', dedup_cmd, True))
    if args.roster_note:
        reason_cmd = [os.path.join(AUDIT, 'reasonableness_check.py'), args.old_docx, args.new_docx]
        if args.key_col_name:
            reason_cmd += ['--key-col-name', args.key_col_name]
        reason_cmd += ['--jump-threshold', args.jump_threshold,
                       '--roster-note', args.roster_note,
                       '--out', os.path.join(out, '合理性校验报告.md')]
        steps.append(('reasonableness', reason_cmd, True))
    if args.inventory:
        inv_cmd = [os.path.join(HERE, 'tool_inventory.py'), '--inventory', args.inventory,
                   '--out', os.path.join(out, '工具清单校验报告.md')]
        if args.tool_registry:
            inv_cmd += ['--registry', args.tool_registry]
        steps.append(('tool_inventory', inv_cmd, True))
    steps.append(('format_diff',
                  [os.path.join(AUDIT, 'format_diff.py'), args.old_docx, args.new_docx,
                   '--threshold', args.threshold,
                   '--out', os.path.join(out, '格式对比报告.md')], True))
    if args.jsonl:
        steps.append(('verify_value',
                      [os.path.join(AUDIT, 'verify_value.py'), args.jsonl,
                       '--out', os.path.join(out, '数值回读报告.md')]
                      + (['--base-dir', base_dir] if base_dir else []), True))
        steps.append(('traceability',
                      [os.path.join(AUDIT, 'traceability_check.py'), args.jsonl,
                       '--min-coverage', args.min_coverage,
                       '--require-cross-check',
                       '--against-docx', args.new_docx,
                       '--out', os.path.join(out, '溯源反查报告.md')]
                      + (['--base-dir', base_dir] if base_dir else []), True))

    # P1-3：--only 过滤（保留原顺序）
    if args.only:
        wanted = [s.strip() for s in args.only.split(',') if s.strip()]
        steps = [s for s in steps if s[0] in wanted]
        unknown = set(wanted) - {s[0] for s in steps}
        if unknown:
            print('⚠️  --only 中未知门禁（忽略）：%s' % '、'.join(sorted(unknown)))
        if not steps:
            print('❌ --only 过滤后无可执行门禁')
            sys.exit(2)

    fails, skipped = [], []
    timings = {}
    for name, cmd, hard in steps:
        if args.resume and state.get(name, {}).get('code') == 0:
            skipped.append(name)
            print('⏭️  跳过已通过门禁：%s（--resume）' % name)
            continue
        t0 = datetime.datetime.now()
        code = _run(cmd, name)
        dur = (datetime.datetime.now() - t0).total_seconds()
        timings[name] = round(dur, 1)
        state[name] = {'code': code, 'ts': datetime.datetime.now().isoformat(timespec='seconds'),
                       'secs': round(dur, 1)}
        _save_state(state_file, state)
        if code and hard:
            fails.append(name)

    print('\n================ 门禁汇总 ================')
    if timings:
        print('⏱️  门禁耗时（秒）：' + '、'.join('%s %.1f' % (k, v) for k, v in timings.items()))
        try:
            with open(os.path.join(out, '门禁耗时.json'), 'w', encoding='utf-8') as f:
                json.dump({'run_ts': datetime.datetime.now().isoformat(timespec='seconds'),
                           'timings': timings, 'fails': fails}, f,
                          ensure_ascii=False, indent=1)
        except OSError:
            pass
    if skipped:
        print('⏭️  续跑跳过：%s' % '、'.join(skipped))
    if fails:
        print('❌ 未通过：%s' % '、'.join(fails))
        sys.exit(1)
    print('✅ 全部通过（共 %d 道门禁）' % len(steps))


if __name__ == '__main__':
    main()
