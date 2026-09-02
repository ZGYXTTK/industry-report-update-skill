# -*- coding: utf-8 -*-
"""
anchor_check.py —— 溯源锚点自检（run.py 门禁前置 dry-run，P0-2）

目的：verify_value/traceability 对溯源.jsonl 锚点的解析规则此前只存在于脚本源码，
首次构造 100% 踩坑（2026-08 期实测 3 轮返工）。本脚本在 run.py 之前本地自检，
把锚点错误前置为一次 dry-run。

《溯源锚点约定》（与 verify_value.py 语义逐条对齐）：
1. 出处二选一：source_file 或 url 至少填一个；两者都缺 = 硬伤。
2. source_file 相对 --base-dir（默认 jsonl 所在目录）解析；文件必须存在且可读。
3. 锚点文件统一用 **CSV**（逗号分隔，首行表头；支持 utf-8-sig/utf-8/gbk）；
   .xls 若实为 CSV 文本亦可。JSON/JSONL/MD 不作为锚点文件（MD 可作 url 的
   补充说明，但不参与回读）。
4. source_key 在「键列」中按 _norm_key 匹配（半角化、去括号内容、去公司后缀）；
   键列默认首列，可用 source_key_col 指定列名（如 "公司名称"、"cmpnm"）。
5. source_field 指定取值列（列名）；未指定时与键列单元格做文本比对。
6. 数值比对取 value 与源单元格的**首个数字**（容差 0.1%），并做单位感知
   （万元/亿元/美元/% 混用会被判「单位不一致」——value 前缀段不要混入无关数字/单位）。
7. 文本比对用 _norm_text 全等——value 应写成与源单元格一致的短语，不要写长句。
8. 「—/–/空」视为空值：旧值→新空值会被 diff_empty 判必补，源锚点同样回读不出。
9. url-only 的记录不参与回读（警告级），但 traceability 仍认可其为出处。

用法：
  python scripts/audit/anchor_check.py runs/<run-id>/sources/溯源.jsonl \
      --base-dir runs/<run-id>/sources/anchors
退出码：存在硬伤 → 1；否则 0。报告写 --out（默认打屏）。
"""
import argparse
import importlib.util
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_verify_value():
    """复用 verify_value.py 的 _read_csv/_resolve/_compare/_norm_*，保证语义一致。"""
    vv_path = os.path.join(HERE, 'verify_value.py')
    spec = importlib.util.spec_from_file_location('verify_value', vv_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--base-dir', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    vv = _load_verify_value()
    base_dir = args.base_dir or os.path.dirname(os.path.abspath(args.jsonl))

    if not os.path.exists(args.jsonl):
        print('❌ 找到不到 %s' % args.jsonl)
        return 2
    recs = []
    for ln, line in enumerate(open(args.jsonl, encoding='utf-8-sig'), 1):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError as e:
            print('❌ 第 %d 行 JSON 解析失败：%s（先修 jsonl 再自检）' % (ln, e))
            return 2

    csv_cache = {}
    hard, warn = [], []
    for rec in recs:
        cell = str(rec.get('cell', '?'))
        val = rec.get('value')
        if rec.get('status') == 'gap':
            continue
        sf = rec.get('source_file') or ''
        url = rec.get('url') or ''
        if not sf and not url:
            hard.append('%s：无出处（source_file 与 url 至少填一个）' % cell)
            continue
        if not sf:
            warn.append('%s：url-only（未回读比对）' % cell)
            continue
        path = sf if os.path.isabs(sf) else os.path.join(base_dir, sf)
        if not os.path.exists(path):
            hard.append('%s：源文件不存在（相对 --base-dir 解析不到）：%s' % (cell, sf))
            continue
        if path not in csv_cache:
            csv_cache[path] = vv._read_csv(path)
        rows = csv_cache[path]
        if rows is None:
            hard.append('%s：源文件存在但不可解析为表格（确认是 CSV 文本而非二进制 xls）：%s' % (cell, sf))
            continue
        if rec.get('source_key') in (None, '') and rec.get('source_row') in (None, ''):
            warn.append('%s：有 source_file 但无 source_key/source_row（未回读）' % cell)
            continue
        src_val, src_field, err = vv._resolve(rows, rec)
        if err:
            hint = ''
            if '键未命中' in err:
                hint = '（检查 source_key 是否等于键列单元格文本；或用 source_key_col 指定键列名）'
            elif '列未命中' in err:
                hint = '（检查 source_field 是否为表头列名）'
            hard.append('%s：%s%s' % (cell, err, hint))
            continue
        ok, note, is_hard = vv._compare(val, src_val, src_field or '')
        if not ok:
            hard.append('%s：%s' % (cell, note))
        else:
            pass

    lines = ['# 溯源锚点自检（anchor_check.py · dry-run）', '',
             '| 指标 | 值 |', '| --- | --- |',
             '| 记录数 | %d |' % len(recs),
             '| 硬伤 | %d |' % len(hard),
             '| 警告 | %d |' % len(warn),
             '| 结论 | %s |' % ('✅ 通过（可进 run.py 门禁）' if not hard else '❌ 存在硬伤，先修锚点'), '']
    if hard:
        lines.append('## 硬伤（必改）')
        lines += ['- ❌ ' + h for h in hard]
        lines.append('')
    if warn:
        lines.append('## 警告（url-only / 无键，不阻断）')
        lines += ['- ⚠️ ' + w for w in warn]
    lines.append('')
    lines.append('> 锚点约定见本脚本 docstring；锚点文件一律用 CSV（首行表头），键列默认首列。')
    report = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(report)
    print(report)
    return 1 if hard else 0


if __name__ == '__main__':
    sys.exit(main())
