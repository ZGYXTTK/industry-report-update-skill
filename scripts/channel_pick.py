# -*- coding: utf-8 -*-
"""
channel_pick.py —— 通道健康度 → 采集通道自动排序（P1-1）

背景：2026-08 期实测，channel_health_check 已判定 ❌ 的通道（深交所分页失效、
烯牛/IT桔子额度耗尽），Agent 仍按采集清单首通道反复尝试，浪费 ≈50min。
本工具在 Step 5 采集前输出每个采集项的「建议通道顺序」，❌ 通道自动沉底并提示降级。

用法：
  # 全量（读取 config/采集清单.yaml + 本期通道实测.jsonl）：
  python scripts/channel_pick.py --run-id runs/2026-08-aero1
  # 仅看某采集项：
  python scripts/channel_pick.py --run-id runs/2026-08-aero1 --item A股在审家数
输入约定：
  - 通道实测.jsonl 每行 {"channel": "...", "status": "✅|🟡|❌", "ts": ...}；
    同名通道取**最新**一条状态（历史多期在 state/渠道历史.jsonl，本工具只看本期）。
  - 采集清单.yaml 每个采集项可有 `通道: [A, B]` 与可选 `备选通道: [C, D]`；
    合并后按实测状态排序：✅ → 未实测(🟡) → ❌ 沉底。
输出：每个采集项的建议通道顺序（stdout + --out 可写文件）。退出码恒为 0（建议性工具）。
"""
import argparse
import io
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)

STATUS_RANK = {'✅': 0, 'ok': 0, '🟡': 1, 'degraded': 1, 'untested': 1, '❌': 2, 'fail': 2}


def _load_yaml(path):
    sys.path.insert(0, HERE)
    try:
        import yaml_lite
        return yaml_lite.load_yaml(path)
    except Exception as e:
        print('⚠️  YAML 解析失败（%s）：%s' % (path, e))
        return None


def _latest_status(jsonl_path):
    """channel → 最新 status（同通道取文件序最后一条）。"""
    latest = {}
    if not os.path.exists(jsonl_path):
        return latest
    for line in open(jsonl_path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ch = r.get('channel') or r.get('source') or r.get('name')
        if ch:
            latest[ch] = r.get('status') or 'untested'
            _NOTES[ch] = (r.get('note') or '') + ' ' + (r.get('result') or '') + ' ' + (r.get('detail') or '')
    return latest


def _channel_names(items):
    """采集项的 通道 + 备选通道 展平。"""
    out = []
    for c in items or []:
        c = str(c)
        if c not in out:
            out.append(c)
    return out


def _match_status(ch, aliases, status):
    """返回通道 ch 的实测状态：别名（含通道名本身）在实测键名/备注中命中即取该状态。
    优先精确键名命中，其次别名片段命中（键名+备注）。"""
    names = [ch] + list(aliases or [])
    # 1) 精确键名
    for n in names:
        if n in status:
            return status[n]
    # 2) 别名片段出现在实测键名或备注中（取状态最差的命中，保守降级）
    best = None
    for k, st in status.items():
        kn = k + ' ' + str(_NOTES.get(k, ''))
        for n in names:
            nn = str(n)
            if len(nn) >= 2 and nn in kn:
                r = STATUS_RANK.get(st, 1)
                if best is None or r > best[0]:
                    best = (r, st)
                break
    return best[1] if best else 'untested'


_NOTES = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', default=None, help='runs/<run-id>（读取 sources/通道实测.jsonl）')
    ap.add_argument('--shice', default=None, help='通道实测.jsonl 显式路径（优先于 --run-id）')
    ap.add_argument('--config', default=os.path.join(SKILL_DIR, 'config', '采集清单.yaml'))
    ap.add_argument('--item', default=None, help='仅看指定采集项 id')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    shice = args.shice or (os.path.join(SKILL_DIR, 'runs', args.run_id, 'sources', '通道实测.jsonl')
                           if args.run_id else None)
    status = _latest_status(shice) if shice else {}
    if not status:
        print('⚠️  未找到/为空 通道实测.jsonl（%s）——所有通道按未实测处理，请先完成 Step 0.5 实测回写'
              % (shice or '未指定'))

    cfg = _load_yaml(args.config)
    if not cfg:
        return 2
    items = cfg.get('采集项') or []

    lines = ['# 通道建议顺序（channel_pick.py · P1-1）', '',
             '> 排序依据：本期通道实测.jsonl（✅ 优先 / 🟡 降级使用 / ❌ 沉底勿试）。', '']
    for it in items:
        iid = it.get('id', '?')
        if args.item and args.item != iid:
            continue
        chans = _channel_names(it.get('通道')) + _channel_names(it.get('备选通道'))
        if not chans:
            continue
        aliases_map = cfg.get('通道别名') or {}
        ranked = sorted(chans, key=lambda c: STATUS_RANK.get(_match_status(c, aliases_map.get(c), status), 1))
        parts = []
        for c in ranked:
            st = _match_status(c, aliases_map.get(c), status)
            mark = {'✅': '✅', 'ok': '✅', '🟡': '🟡', 'degraded': '🟡', '❌': '❌', 'fail': '❌'}.get(st, '🟡')
            parts.append('%s%s' % (mark, c))
        lines.append('- **%s**：%s' % (iid, ' → '.join(parts)))

    report = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(report + '\n')
    print(report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
