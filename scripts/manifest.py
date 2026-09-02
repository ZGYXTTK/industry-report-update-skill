# -*- coding: utf-8 -*-
"""
manifest.py —— runs/<run-id>/manifest.json 生成与查询（P1-7：子 Skill 接口契约）

解决「子 Skill 之间靠模型自觉传 run-id」的断链风险：
每次月报执行开局跑一次 init，生成 manifest.json；专题子 Skill（及其他下游）
只认 manifest 读取本期路径与前置状态，不再猜目录。

manifest.json 结构：
{
  "run_id": "2026-08-AG88f7d",
  "ym": "2026-08",
  "pack": "robotics",
  "created_at": "...",
  "paths": {                       # 相对 runs/<run-id>/ 的标准路径
    "old_report": "input/旧月报.docx",
    "channel_health": "通道健康度-2026-08.md",
    "snapshot_diff": "logs/口径diff.txt",
    "new_report": "output/新月报.docx",
    "sources_dir": "download/",
    "traceability": "sources/溯源.jsonl",
    "mcp_log": "sources/通道实测.jsonl",
    "change_summary": "output/变更摘要.md",
    "review": "reviews/独立审核意见.md",
    "metrics": "../../metrics.json"
  },
  "preconditions": {               # 子 Skill 前置检查（专题研究 Skill 读这里）
    "channel_health_done": false,
    "snapshot_diff_lt3": null,
    "prospectus_pdfs": []
  },
  "steps": {}                      # 各 Step 完成状态（run.py / checkpoint 回写）
}

用法:
    python scripts/manifest.py init --ym 2026-08 --run-id 2026-08-AG88f7d [--pack robotics] [--runs-root runs]
    python scripts/manifest.py set --run-id 2026-08-AG88f7d --key preconditions.channel_health_done --value true
    python scripts/manifest.py get --run-id 2026-08-AG88f7d [--key paths.new_report]
"""
import argparse
import datetime
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def _manifest_path(runs_root, run_id):
    return os.path.join(runs_root, run_id, 'manifest.json')


def _load(runs_root, run_id):
    p = _manifest_path(runs_root, run_id)
    if not os.path.exists(p):
        return None, p
    with open(p, encoding='utf-8') as f:
        return json.load(f), p


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def cmd_init(args):
    p = _manifest_path(args.runs_root, args.run_id)
    data = {
        'run_id': args.run_id,
        'ym': args.ym,
        'pack': args.pack,
        'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'input': {
            # 输入旧月报的「原始路径」（user 给的文件位置），供 Step 9.5 归档自动锚定工作区；
            # 由 agent 传入（--old-doc），或事后 manifest.py set input.old_doc <路径>
            'old_doc': getattr(args, 'old_doc', None) or None,
        },
        'paths': {
            # 说明：old_report / new_report 为相对 runs/<run-id>/ 的目录（文件名随月份/产品而变）；
            # traceability / change_summary / review / channel_health 为文件路径。子 Skill 读取时区分目录/文件。
            'old_report': 'input/',
            'new_report': 'output/',
            'channel_health': '通道健康度-%s.md' % args.ym,
            'snapshot_diff': 'logs/口径diff.txt',
            'sources_dir': 'download/',
            'traceability': 'sources/溯源.jsonl',
            'mcp_log': 'sources/通道实测.jsonl',
            'change_summary': 'output/变更摘要.md',
            'review': 'reviews/独立审核意见.md',
        },
        'preconditions': {
            'channel_health_done': False,
            'snapshot_diff_lt3': None,
            'prospectus_pdfs': [],
        },
        'steps': {},
    }
    _save(p, data)
    print('✅ manifest 已初始化：%s' % p)
    if data['input']['old_doc']:
        print('   input.old_doc = %s' % data['input']['old_doc'])


def cmd_set(args):
    data, p = _load(args.runs_root, args.run_id)
    if data is None:
        print('❌ manifest 不存在，请先 init：%s' % p)
        return 2
    cur = data
    keys = args.key.split('.')
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    val = args.value
    if val.lower() in ('true', 'false'):
        val = val.lower() == 'true'
    else:
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, ValueError):
            pass
    cur[keys[-1]] = val
    _save(p, data)
    print('✅ %s = %r' % (args.key, val))
    return 0


def cmd_get(args):
    data, p = _load(args.runs_root, args.run_id)
    if data is None:
        print('❌ manifest 不存在：%s' % p)
        return 2
    if not args.key:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    cur = data
    for k in args.key.split('.'):
        if not isinstance(cur, dict) or k not in cur:
            print('❌ 键不存在：%s' % args.key)
            return 2
        cur = cur[k]
    print(json.dumps(cur, ensure_ascii=False) if not isinstance(cur, str) else cur)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    for name in ('init', 'set', 'get'):
        sp = sub.add_parser(name)
        sp.add_argument('--runs-root', default='runs')
        if name == 'init':
            sp.add_argument('--ym', required=True)
            sp.add_argument('--run-id', required=True)
            sp.add_argument('--pack', default='robotics')
            sp.add_argument('--old-doc', default=None,
                            help='输入旧月报原始路径（供归档自动锚定工作区，open-source 通用）')
        else:
            sp.add_argument('--run-id', required=True)
            if name == 'set':
                sp.add_argument('--key', required=True)
                sp.add_argument('--value', required=True)
            else:
                sp.add_argument('--key', default=None)
    args = ap.parse_args()
    if args.action == 'init':
        cmd_init(args)
        return 0
    if args.action == 'set':
        return cmd_set(args)
    return cmd_get(args)


if __name__ == '__main__':
    sys.exit(main())
