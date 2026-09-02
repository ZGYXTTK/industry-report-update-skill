# -*- coding: utf-8 -*-
"""
checkpoint.py —— 采集状态持久化 / 检查点

解决「上下文耗尽即丢失」：每完成一个采集项立即 record()，中断后可 resume() 续跑。
状态追加写 state/采集进度.jsonl，幂等（同 item_id 重复记录取最后一条）。

用法:
    from checkpoint import record, resume, mark_done
    record('A股在审', 'done', '下载资料/xx.csv', rows=18, collected_at='2026-08-27', fallback_used='')
    resume()   # 打印 剩余待采 / 失败待降级 / 已完成
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, '..', 'state')
STATE_FILE = os.path.join(STATE_DIR, '采集进度.jsonl')


def _ensure():
    os.makedirs(STATE_DIR, exist_ok=True)


def record(item_id, status, output_file='', rows=None, collected_at=None, fallback_used=''):
    """status: done / failed / skipped。追加一条状态。"""
    _ensure()
    rec = {
        'item_id': item_id,
        'status': status,          # done / failed / skipped
        'output_file': output_file,
        'rows': rows,
        'collected_at': collected_at or time.strftime('%Y-%m-%d %H:%M:%S'),
        'fallback_used': fallback_used,   # 用了哪条降级链
    }
    with open(STATE_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def _load():
    if not os.path.exists(STATE_FILE):
        return []
    rows = []
    with open(STATE_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    # 同 item_id 去重，保留最后一条
    last = {}
    for r in rows:
        last[r['item_id']] = r
    return list(last.values())


def resume(plan_item_ids):
    """对比采集清单的 item_id 集合，打印断点状态。返回 (剩余待采, 失败待降级, 已完成)。"""
    done = {r['item_id']: r for r in _load() if r['status'] == 'done'}
    failed = {r['item_id']: r for r in _load() if r['status'] == 'failed'}
    remaining = [i for i in plan_item_ids if i not in done]
    failed_list = [i for i in plan_item_ids if i in failed]
    print('=== 采集断点状态 ===')
    print('已完成 %d 项、失败待降级 %d 项、剩余待采 %d 项' % (len(done), len(failed_list), len(remaining)))
    if failed_list:
        print('失败待降级：%s' % '、'.join(failed_list))
    if remaining:
        print('剩余待采：%s' % '、'.join(remaining))
    return remaining, failed_list, list(done.keys())


if __name__ == '__main__':
    # 演示：无参数时列出已有状态
    recs = _load()
    if not recs:
        print('暂无采集状态。用法：from checkpoint import record; record(item_id, status, ...)')
    else:
        for r in recs:
            print('[%s] %s %s' % (r['status'], r['item_id'], r.get('output_file') or ''))
