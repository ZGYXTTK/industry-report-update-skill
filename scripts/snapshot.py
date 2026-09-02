# -*- coding: utf-8 -*-
"""
snapshot.py —— 口径快照与版本治理（v2 · P1-5）

v2 修正（对应「自写 YAML 解析器守关键闸门」短板）：
  1. 解析统一走 scripts/yaml_lite.py：有 PyYAML 用 PyYAML（严格），
     无 PyYAML 用 mini 解析器（支持嵌套/列表/块标量，遇到锚点等复杂特性显式报错，
     不再静默漏解析）；
  2. diff 从「只比版本号字符串」升级为「叶子级深 diff」：
     逐叶子路径对比两份快照的原始内容，字段/枚举值/通道名任一变化都计数——
     ≥3 项触发「暂停并请求用户确认」，与硬性纪律一致；
  3. 快照文件同时保存解析后的完整叶子清单（jsonl 风格注释段），供深 diff 使用。

用法:
    python scripts/snapshot.py snapshot --ym 2026-08 --run-id 2026-08-XXXXXX
    python scripts/snapshot.py diff --ym 2026-08 --prev-ym 2026-07
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE))
from yaml_lite import load_yaml, backend, YamlLiteError  # noqa: E402

CFG = SKILL_DIR / 'config'
SNAP_DIR = CFG / '口径快照'

CONFIGS = [
    ('口径字典', CFG / '口径字典.yaml'),
    ('采集清单', CFG / '采集清单.yaml'),
    ('权威源映射', CFG / '权威源映射.yaml'),
    ('时点对齐策略', CFG / '时点对齐策略.yaml'),
    ('标的池', CFG / '标的池.yaml'),
]

REQUIRED_FIELDS = {
    '口径字典': ['版本', '赛道定义', '采集通道'],
    '采集清单': ['采集项', '截至日期'],
    '权威源映射': ['权威源映射', '通用降级', '降级链'],
    '时点对齐策略': ['时点对齐', '采集日期显式化'],
    '标的池': [],
}


def flatten(obj, prefix=''):
    """把嵌套 dict/list 拍平成 {叶子路径: 值}，供深 diff。"""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, '%s/%s' % (prefix, k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, '%s[%d]' % (prefix, i)))
    else:
        out[prefix] = obj
    return out


def cmd_snapshot(ym, run_id='unknown'):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap_file = SNAP_DIR / ('%s.yaml' % ym)
    leaves_all = {}
    lines = [
        '# 口径快照 · %s 月（snapshot.py v2，解析后端：%s）' % (ym, backend()),
        '# 生成时间：%s' % datetime.datetime.now().isoformat(timespec='seconds'),
        '# 运行 ID：%s' % run_id,
        '',
    ]
    deltas = 0
    for name, path in CONFIGS:
        lines.append('%s:' % name)
        if not path.exists():
            lines.append('  状态: 缺失')
            lines.append('')
            continue
        try:
            parsed = load_yaml(str(path))
        except YamlLiteError as e:
            lines.append('  ⚠️ 解析失败: %s' % e)
            deltas += 1
            lines.append('')
            continue
        version = parsed.get('版本') or parsed.get('version') or '未声明'
        missing = [k for k in REQUIRED_FIELDS.get(name, []) if k not in parsed]
        lines.append('  版本: %s' % version)
        if missing:
            lines.append('  ⚠️ 必填字段缺失: %s' % missing)
            deltas += 1
        else:
            lines.append('  必填字段: 完整')
        leaves = flatten(parsed)
        leaves_all[name] = leaves
        lines.append('  叶子节点数: %d' % len(leaves))
        lines.append('')
    # 叶子清单作为结构化附录（深 diff 的数据基础）
    lines.append('# --- 以下为机器可读叶子清单（diff 用，勿手工编辑） ---')
    lines.append('叶子清单:')
    for name, leaves in leaves_all.items():
        for k, v in leaves.items():
            lines.append('  - %s' % json.dumps([name, k, v], ensure_ascii=False))
    snap_file.write_text('\n'.join(lines), encoding='utf-8')
    print('✅ 快照已落盘：%s（解析后端 %s）' % (snap_file, backend()))
    return deltas


def _load_leaves(snap_file):
    leaves = {}
    with open(snap_file, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if s.startswith('- ['):
                try:
                    name, k, v = json.loads(s[2:])
                    leaves.setdefault(name, {})[k] = v
                except (json.JSONDecodeError, ValueError):
                    continue
    return leaves


def cmd_diff(ym_now, ym_prev):
    f_now = SNAP_DIR / ('%s.yaml' % ym_now)
    f_prev = SNAP_DIR / ('%s.yaml' % ym_prev)
    if not f_prev.exists():
        print('⚠️ 上期快照不存在：%s，跳过 diff（首次执行）' % f_prev)
        return 0
    if not f_now.exists():
        print('❌ 本期快照不存在：%s，请先跑 snapshot' % f_now)
        return 2
    cur, prev = _load_leaves(f_now), _load_leaves(f_prev)
    if not prev:
        print('⚠️ 上期快照为 v1 格式（无叶子清单），本期起升级为深 diff，本次跳过')
        return 0
    changes = []
    for name in set(cur) | set(prev):
        c, p = cur.get(name, {}), prev.get(name, {})
        for k in sorted(set(c) | set(p)):
            if k not in p:
                changes.append('%s：新增 %s = %r' % (name, k, c[k]))
            elif k not in c:
                changes.append('%s：移除 %s（原值 %r）' % (name, k, p[k]))
            elif c[k] != p[k]:
                changes.append('%s：%s 由 %r → %r' % (name, k, p[k], c[k]))
    print('📊 口径漂移项数（叶子级）：%d' % len(changes))
    for d in changes[:50]:
        print('  - %s' % d)
    if len(changes) > 50:
        print('  …（其余 %d 项省略）' % (len(changes) - 50))
    if len(changes) >= 3:
        print('⚠️ 差异 ≥3 项，必须暂停并请求用户确认（硬性纪律 · 口径版本快照）')
    return len(changes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['snapshot', 'diff'])
    ap.add_argument('--ym', required=True)
    ap.add_argument('--prev-ym', default=None)
    ap.add_argument('--run-id', default='unknown')
    args = ap.parse_args()
    if args.action == 'snapshot':
        cmd_snapshot(args.ym, args.run_id)
    else:
        if not args.prev_ym:
            print('❌ diff 模式必须传 --prev-ym')
            sys.exit(2)
        cmd_diff(args.ym, args.prev_ym)


if __name__ == '__main__':
    main()
