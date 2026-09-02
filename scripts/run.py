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
    ap.add_argument('--key-col-name', default='公司简称')
    ap.add_argument('--jsonl', default=None, help='溯源.jsonl（提供则跑 verify_value + traceability）')
    ap.add_argument('--base-dir', default=None, help='源文件锚定目录（默认取 jsonl 所在目录）')
    ap.add_argument('--roster-note', default=None, help='变更摘要.md（提供则跑 reasonableness）')
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
    ap.add_argument('--only', default=None,
                    help='仅跑指定门禁（逗号分隔，如 "consistency,verify_value"）——'
                         '单项内容修改后的快速验证（P1-3），不再全量轮转')
    args = ap.parse_args()

    out = args.out_dir
    os.makedirs(out, exist_ok=True)
    state_file = args.state_file or os.path.join(out, '门禁状态.json')
    state = _load_state(state_file) if args.resume else {}

    base_dir = args.base_dir or (os.path.dirname(os.path.abspath(args.jsonl)) if args.jsonl else None)

    # (名称, 命令, 是否硬门禁)
    steps = [
        ('extract_numbers',
         [os.path.join(AUDIT, 'extract_numbers.py'), args.old_docx,
          '--out', os.path.join(out, '结论性语句清单.md'),
          '--json', os.path.join(out, '结论.jsonl')], False),
        ('config_check',
         [os.path.join(AUDIT, 'config_check.py'),
          '--out', os.path.join(out, '配置校验报告.md')], True),
        ('diff_empty',
         [os.path.join(AUDIT, 'diff_empty.py'), args.old_docx, args.new_docx,
          '--key-col-name', args.key_col_name,
          '--out', os.path.join(out, '空值对比报告.md')], True),
        ('consistency',
         [os.path.join(AUDIT, 'consistency_check.py'), args.new_docx,
          '--out', os.path.join(out, '一致性校验报告.md')], True),
        ('cross_consistency',
         [os.path.join(AUDIT, 'cross_consistency_check.py'), args.new_docx,
          '--out', os.path.join(out, '交叉一致性报告.md')], True),
    ]
    if args.roster_note:
        steps.append(('reasonableness',
                      [os.path.join(AUDIT, 'reasonableness_check.py'), args.old_docx, args.new_docx,
                       '--key-col-name', args.key_col_name,
                       '--jump-threshold', args.jump_threshold,
                       '--roster-note', args.roster_note,
                       '--out', os.path.join(out, '合理性校验报告.md')], True))
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
