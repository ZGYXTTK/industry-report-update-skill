# -*- coding: utf-8 -*-
"""
channel_health_check.py —— Step 0.5 通道健康度自检（v2 · P1-4）

v2 相对 v1 的修正（对应「脚本假装能调 MCP」与「URL 硬编码」两个短板）：
  1. 探测目标全部来自 config/endpoints.yaml —— 官网改接口只改配置，不动脚本；
  2. HTTP 通道：脚本直接探测（与 v1 相同）；
  3. MCP / agent 通道：脚本【无法】在 Python 进程内调用宿主 MCP/subagent，
     改为「Agent 实测回写 + 脚本校验」分工——
       a. Agent 按 endpoints.yaml 的 smoke_hint 真调一次各 MCP 工具/子 Agent 通道，
          把结果按行追加写入 通道实测.jsonl：
          {"channel": "...", "status": "ok|degraded|fail", "tested_at": "YYYY-MM-DD", "detail": "..."}
       b. 本脚本读取该日志，取每通道最新一条：
          记录新鲜（≤--max-age-days，默认 35 天）→ 按记录给 ✅/🟡/❌；
          记录过期或缺失 → 🟡 待实测（并列入报告"本期必须实测"清单）；
  4. 连续 ❌ 计数带时间戳：每期结果追加写入 state/渠道历史.jsonl，
     按月份统计某通道连续 ❌ 期数，≥2 期触发「续费/改接口」提示（替代 v1 人工数格子）。

用法:
    python scripts/channel_health_check.py --ym 2026-08 --run-id 2026-08-XXXXXX \
        [--mcp-log runs/<run-id>/sources/通道实测.jsonl] [--max-age-days 35] [--out 通道健康度.md]
退出码恒 0（不阻断执行），但报告与 渠道历史.jsonl 会如实记录。
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE))
from yaml_lite import load_yaml  # noqa: E402

CFG = SKILL_DIR / 'config'
STATE_DIR = SKILL_DIR / 'state'
HISTORY = STATE_DIR / '渠道历史.jsonl'
ENDPOINTS = CFG / 'endpoints.yaml'

_STATUS_MAP = {'ok': '✅', 'degraded': '🟡', 'fail': '❌'}


def probe_http(url, method, headers=None, body=None, timeout=10):
    try:
        if method.upper() == 'GET':
            r = requests.get(url, headers=headers or {}, timeout=timeout)
        else:
            r = requests.post(url, headers=headers or {}, data=body or {}, timeout=timeout)
        ok = 200 <= r.status_code < 400 and len(r.content) > 0
        return ok, 'HTTP %d, %d bytes' % (r.status_code, len(r.content))
    except Exception as e:
        return False, '%s: %s' % (type(e).__name__, e)


def load_mcp_log(path):
    """读 通道实测.jsonl，返回 {channel: 最新记录}。"""
    latest = {}
    if not path or not os.path.exists(path):
        return latest
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ch = rec.get('channel')
            ts = rec.get('tested_at', '')
            if ch and (ch not in latest or ts >= latest[ch].get('tested_at', '')):
                latest[ch] = rec
    return latest


def resolve_agent_channel(name, latest, max_age_days, today):
    """MCP/agent 通道：以 Agent 回写日志为准，脚本只做新鲜度与结论校验。"""
    rec = latest.get(name)
    if not rec:
        return '🟡', '待实测：Agent 需按 endpoints.yaml 的 smoke_hint 真调一次并回写 通道实测.jsonl', True
    ts = rec.get('tested_at', '')
    try:
        age = (today - datetime.date.fromisoformat(ts)).days
    except ValueError:
        return '🟡', '实测记录日期非法：%r，请按 YYYY-MM-DD 回写' % ts, True
    if age > max_age_days:
        return '🟡', '实测记录过期（%s，%d 天前），本期需重测' % (ts, age), True
    st = _STATUS_MAP.get(str(rec.get('status', '')).lower(), '🟡')
    return st, '实测于 %s：%s' % (ts, rec.get('detail', '')[:60]), False


def append_history(ym, results):
    STATE_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec='seconds')
    with open(HISTORY, 'a', encoding='utf-8') as f:
        for name, status, _detail, _flag in results:
            f.write(json.dumps({'ym': ym, 'channel': name, 'status': status, 'ts': ts},
                               ensure_ascii=False) + '\n')


def consecutive_fail_months(channel, ym_now):
    """统计某通道截至本期（含）连续 ❌ 的月份数。"""
    if not HISTORY.exists():
        return 0
    by_month = {}
    with open(HISTORY, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get('channel') == channel:
                by_month[rec.get('ym', '')] = rec.get('status', '')
    months = sorted(m for m in by_month if m and m <= ym_now)
    streak = 0
    for m in reversed(months):
        if by_month[m] == '❌':
            streak += 1
        else:
            break
    return streak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ym', required=True, help='YYYY-MM')
    ap.add_argument('--run-id', default='unknown')
    ap.add_argument('--mcp-log', default=None,
                    help='通道实测.jsonl 路径（默认依次尝试 runs/<run-id>/sources/ 与 state/ 下）')
    ap.add_argument('--max-age-days', type=int, default=35)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    today = datetime.date.today()

    if not ENDPOINTS.exists():
        print('❌ 缺少 %s（P1-4 引入的端点配置）' % ENDPOINTS)
        return 2
    ep = load_yaml(str(ENDPOINTS))

    mcp_log = args.mcp_log
    if not mcp_log:
        cands = [Path('runs') / args.run_id / 'sources' / '通道实测.jsonl',
                 STATE_DIR / '通道实测.jsonl']
        mcp_log = next((str(c) for c in cands if c.exists()), str(cands[0]))
    latest = load_mcp_log(mcp_log)

    out_path = Path(args.out) if args.out else (Path('runs') / args.run_id / ('通道健康度-%s.md' % args.ym))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []  # (name, status, detail, need_test)
    for ch in ep.get('http通道', []) or []:
        ok, detail = probe_http(ch['url'], ch.get('method', 'GET'),
                                ch.get('headers'), ch.get('body'))
        status = '✅' if ok else '❌'
        if not ok and ch.get('note'):
            detail += '（%s）' % ch['note']
        results.append((ch['name'], status, detail, False))

    need_test_list = []
    for group in ('mcp通道', 'agent通道'):
        for ch in ep.get(group, []) or []:
            status, detail, need = resolve_agent_channel(ch['name'], latest, args.max_age_days, today)
            if need:
                hint = ch.get('smoke_hint', '')
                need_test_list.append('%s（%s）' % (ch['name'], hint) if hint else ch['name'])
            results.append((ch['name'], status, detail, need))

    append_history(args.ym, results)

    # 连续 ❌ 统计（含本期）
    streak_notes = []
    for name, status, _d, _n in results:
        if status == '❌':
            streak = consecutive_fail_months(name, args.ym)
            if streak >= 2:
                streak_notes.append('%s 已连续 %d 期 ❌ → 触发「续费 / 改接口」提示' % (name, streak))

    lines = [
        '# 通道健康度 · %s 月（channel_health_check.py v2）' % args.ym,
        '生成时间：%s ｜ 运行 ID：%s ｜ 实测日志：%s' % (
            datetime.datetime.now().isoformat(timespec='seconds'), args.run_id, mcp_log),
        '',
        '| 通道 | 状态 | 详情 |',
        '| --- | --- | --- |',
    ]
    for name, status, detail, _n in results:
        lines.append('| %s | %s | %s |' % (name, status, detail[:90]))
    bad = [r[0] for r in results if r[1] == '❌']
    lines += ['', '## 统计：✅%d 🟡%d ❌%d' % (
        sum(1 for r in results if r[1] == '✅'),
        sum(1 for r in results if r[1] == '🟡'),
        len(bad))]
    if need_test_list:
        lines += ['', '## 本期必须实测（Agent 真调一次并回写 通道实测.jsonl）', '']
        for n in need_test_list:
            lines.append('- %s' % n)
    if streak_notes:
        lines += ['', '## 连续失败触发', '']
        for n in streak_notes:
            lines.append('- ❌ %s' % n)
    if bad:
        lines += ['', '## 失败通道（本期按降级链执行）', '']
        for n in bad:
            lines.append('- %s' % n)
    out_path.write_text('\n'.join(lines), encoding='utf-8')
    print('✅ 通道健康度报告：%s' % out_path)
    print('   ✅%d 🟡%d ❌%d ｜ 待实测 %d ｜ 连续❌触发 %d' % (
        sum(1 for r in results if r[1] == '✅'),
        sum(1 for r in results if r[1] == '🟡'),
        len(bad), len(need_test_list), len(streak_notes)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
