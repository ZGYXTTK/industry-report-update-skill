# -*- coding: utf-8 -*-
"""
metrics.py —— 跨月度量（P2-12：用数据证明 Skill 自己越用越稳）

每期月报结束后把质量指标追加写入 runs/metrics.json（JSON 数组），
trend 命令输出跨月趋势表：门禁得分、人工修正条数、通道降级数、token 成本。

用法:
    python scripts/metrics.py record --ym 2026-08 --run-id 2026-08-AG88f7d \
        [--gate format_diff=0.978] [--gate verify_value=pass] \
        [--manual-fixes 3] [--tokens 420000] [--downgrades 2] [--notes "IT桔子续费"]
    python scripts/metrics.py trend [--runs-root runs]
"""
import argparse
import datetime
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def _path(runs_root):
    return os.path.join(runs_root, 'metrics.json')


def _load(runs_root):
    p = _path(runs_root)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def cmd_record(args):
    rec = {
        'ym': args.ym,
        'run_id': args.run_id,
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'gates': {},
        'manual_fixes': args.manual_fixes,
        'tokens': args.tokens,
        'downgrades': args.downgrades,
        'notes': args.notes,
    }
    for g in args.gate or []:
        k, _, v = g.partition('=')
        if k:
            try:
                rec['gates'][k] = float(v)
            except ValueError:
                rec['gates'][k] = v
    data = _load(args.runs_root)
    data.append(rec)
    os.makedirs(args.runs_root, exist_ok=True)
    with open(_path(args.runs_root), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('✅ 度量已记录：%s（累计 %d 期）' % (_path(args.runs_root), len(data)))
    return 0


def cmd_trend(args):
    data = _load(args.runs_root)
    if not data:
        print('（暂无度量数据：%s）' % _path(args.runs_root))
        return 0
    gate_names = sorted({n for r in data for n in r.get('gates', {})})
    header = ['月份', 'run_id'] + gate_names + ['人工修正', 'tokens', '降级', '备注']
    lines = ['| ' + ' | '.join(header) + ' |',
             '|' + ' --- |' * len(header)]
    for r in data:
        row = [r.get('ym', ''), r.get('run_id', '')]
        for n in gate_names:
            v = r.get('gates', {}).get(n, '')
            row.append(('%.3f' % v) if isinstance(v, float) else str(v))
        row += [str(r.get('manual_fixes') or 0),
                str(r.get('tokens') or ''),
                str(r.get('downgrades') or 0),
                (r.get('notes') or '')[:20]]
        lines.append('| ' + ' | '.join(row) + ' |')
    report = '\n'.join(lines)
    print(report)
    # 简单趋势提示：门禁通过率是否收敛、人工修正是否下降
    if len(data) >= 2:
        fixes = [r.get('manual_fixes') for r in data if isinstance(r.get('manual_fixes'), int)]
        if len(fixes) >= 2 and fixes[-1] > fixes[0]:
            print('\n⚠️ 人工修正条数较首期上升（%d → %d），建议复盘门禁漏检项' % (fixes[0], fixes[-1]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    sp = sub.add_parser('record')
    sp.add_argument('--ym', required=True)
    sp.add_argument('--run-id', required=True)
    sp.add_argument('--gate', action='append')
    sp.add_argument('--manual-fixes', type=int, default=0)
    sp.add_argument('--tokens', type=int, default=None)
    sp.add_argument('--downgrades', type=int, default=0)
    sp.add_argument('--notes', default='')
    sp.add_argument('--runs-root', default='runs')
    sp2 = sub.add_parser('trend')
    sp2.add_argument('--runs-root', default='runs')
    args = ap.parse_args()
    return cmd_record(args) if args.action == 'record' else cmd_trend(args)


if __name__ == '__main__':
    sys.exit(main())
