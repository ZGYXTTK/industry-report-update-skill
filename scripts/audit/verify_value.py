# -*- coding: utf-8 -*-
"""
verify_value.py —— 数值回读校验门禁（P0：从「自证」到「他证」）

老的 traceability_check.py 只校验「溯源记录结构完整、源文件存在」，
证明不了「月报里的数 = 源文件里的数」。本门禁把验证链条闭环：
对 溯源.jsonl 中带锚点的每条记录，回读源文件（CSV），取出锚点处的真实值，
与月报呈现值逐一比对——编一个合理来源从此过不了门禁。

锚点写法（溯源.jsonl 每行记录，满足其一即可）：
  A. source_key + source_field（+可选 source_key_col，默认取源文件首列）
       在源文件中定位「键列值 = source_key」的行，再取 source_field 列的值；
  B. source_row + source_field
       source_row 为 1-based 数据行号（不含表头），source_field 为表头列名（子串匹配）。

判定规则：
  - 两边都能解析出数字：相对误差 ≤ --rel-tol（默认 0.001）判一致；
    数值相差 10/100/10000 倍量级 → 报「单位量级疑似不一致」（硬伤，附提示）；
  - 否则做文本归一化比对（全角转半角、去空白）；
  - status=gap 的记录跳过（缺口已如实申报，不参与比对）；
  - 无锚点记录单列统计（提示级）；--require-anchor 时无锚点也判硬伤；
  - 源文件缺失 / 锚点无法解析 → 硬伤。

用法:
    python verify_value.py 溯源.jsonl [--base-dir 下载资料] [--rel-tol 0.001] \
        [--require-anchor] [--out 数值回读报告.md]
退出码：0=全部通过；1=存在硬伤；2=参数错误。
"""
import argparse
import csv
import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

_NUM_RE = re.compile(r'[-+]?\d[\d,]*\.?\d*')
_SCALE_HINTS = ((10000.0, '万↔亿'), (100.0, '相差约100倍'), (10.0, '相差约10倍'))
# 单位 → 数量级因子（单位感知比对）。**币种+数量级复合单位必须排在单纯数量级之前**（最长匹配优先），
# 使 "1.2亿美元"(标签亿美元) 与 "1.2亿元"(标签亿元) 的 label 不同，从而捕捉 USD/CNY 口径误判。
_UNITS = [
    ('万亿元', 1e12), ('万亿', 1e12),
    ('亿美元', 1e8), ('亿港元', 1e8), ('亿元人民币', 1e8), ('亿元', 1e8), ('亿', 1e8),
    ('万美元', 1e4), ('万港元', 1e4), ('万元人民币', 1e4), ('万元', 1e4), ('万', 1e4),
    ('美元', 1.0), ('港元', 1.0), ('人民币', 1.0), ('元', 1.0),
]


def _unit_factor(s):
    """从字符串提取单位数量级因子。返回 (factor, label)；无单位返回 (None, None)。'%' 视为 0.01。"""
    if not s:
        return None, None
    if '%' in s:
        return 0.01, '%'
    # 按声明顺序（复合→单纯，长→短）第一个命中的即最精确单位
    for u, f in _UNITS:
        if u in s:
            return f, u
    return None, None


def _currency_of(label):
    """从单位 label 推断币种：美元/港元/人民币；无币种标记按人民币(CNY)处理。返回 'USD'/'HKD'/'CNY'/None。"""
    if not label:
        return None
    if '美元' in label:
        return 'USD'
    if '港元' in label:
        return 'HKD'
    if '人民币' in label:
        return 'CNY'
    if any(c in label for c in ('亿元', '亿', '万元', '万', '元')):
        return 'CNY'   # 无币种标记的数量级单位，按人民币
    return None


def _read_csv(path):
    """读 CSV，自动尝试 utf-8-sig / utf-8 / gbk。文件不存在返回 None。"""
    if not os.path.exists(path):
        return None
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            with open(path, encoding=enc, newline='') as f:
                rows = [r for r in csv.reader(f) if any((c or '').strip() for c in r)]
            if rows:
                return rows
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _parse_num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = _NUM_RE.search(v)
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', ''))
    except ValueError:
        return None


def _norm_text(v):
    if v is None:
        return ''
    out = []
    for ch in str(v):
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            ch = chr(code - 0xFEE0)
        elif code == 0x3000:
            ch = ' '
        out.append(ch)
    return re.sub(r'\s+', '', ''.join(out))


def _norm_key(v):
    """键归一化（与 diff_empty.py 对齐）：半角化、去括号内容、去公司后缀。"""
    t = _norm_text(v)
    t = re.sub(r'[（(][^）)]*[）)]', '', t)
    t = re.sub(r'(股份有限公司|有限责任公司|有限公司|控股集团|集团)', '', t)
    return t.strip()


def _find_col(header, field):
    if not field:
        return None
    nf = _norm_text(field)
    for i, h in enumerate(header):
        if nf and nf in _norm_text(h):
            return i
    return None


def _resolve(rows, rec):
    """返回 (源值, 源列头, 错误信息)。错误信息非 None 表示锚点无法解析。"""
    header, data = rows[0], rows[1:]
    row = None
    if rec.get('source_key') not in (None, ''):
        kc = _find_col(header, rec.get('source_key_col'))
        if kc is None:
            kc = 0
        nk = _norm_key(rec['source_key'])
        for r in data:
            if kc < len(r) and _norm_key(r[kc]) == nk:
                row = r
                break
        if row is None:
            return None, None, '键未命中：%s（键列=%s）' % (rec['source_key'], rec.get('source_key_col') or '首列')
    elif rec.get('source_row') not in (None, ''):
        try:
            ri = int(rec['source_row']) - 1
        except (TypeError, ValueError):
            return None, None, 'source_row 非法：%r' % rec.get('source_row')
        if 0 <= ri < len(data):
            row = data[ri]
        else:
            return None, None, 'source_row 越界：%d（数据行数 %d）' % (ri + 1, len(data))
    else:
        return None, None, '无锚点'

    ci = _find_col(header, rec.get('source_field'))
    if ci is None:
        if rec.get('source_field'):
            return None, None, '列未命中：%s' % rec['source_field']
        # 未指定字段：与键列单元格比对（验证该行确实存在于源文件）
        ci = _find_col(header, rec.get('source_key_col')) or 0
    if ci >= len(row):
        return None, None, '列越界：%d' % ci
    return row[ci], (header[ci] if ci < len(header) else ''), None


def _compare(report_val, src_val, src_field='', rel_tol=0.001):
    """返回 (是否一致, 说明, 是否硬伤级不一致)。

    v2 单位感知：若两侧都识别出单位因子，则按「数字×单位」折算后比对，
    并显式提示单位差异（修复'1亿元 vs 1万元 但因数字同为 1 而误判通过'的漏检）。
    任一侧无单位则退化为纯数字比对（并保留量级 hint）。"""
    a, b = _parse_num(report_val), _parse_num(src_val)
    if a is not None and b is not None:
        # 单位因子：月报取自身字符串；源文件取「源单元格 + 源列头」合起来推断
        fa, ua = _unit_factor(report_val)
        fb, ub = _unit_factor('%s %s' % (src_val, src_field or ''))
        if fa is not None and fb is not None:
            # 币种维度：两侧都识别出币种且不同 → 无论换算值是否相等都判"币种口径不一致"(硬伤)
            ca, cb = _currency_of(ua), _currency_of(ub)
            if ca and cb and ca != cb:
                return False, '币种口径不一致：月报 %.6g%s(%s) vs 源 %.6g%s(%s)' % (a, ua or '', ca, b, ub or '', cb), True
            va, vb = a * fa, b * fb
            denom = max(abs(va), abs(vb), 1.0)
            if abs(va - vb) <= rel_tol * denom:
                note = '折算一致：月报 %.6g%s ≈ 源 %.6g%s' % (a, ua or '', b, ub or '')
                return True, note, False
            if a == b and (ua or ub):
                return False, '单位不一致：月报 %.6g%s vs 源 %.6g%s（数字相同但单位不同）' % (a, ua or '', b, ub or ''), True
            return False, '折算不一致：月报 %.6g%s vs 源 %.6g%s' % (a, ua or '', b, ub or ''), True
        # 无单位（或仅一侧含单位）：退化为纯数字比对
        if abs(a - b) <= rel_tol * max(abs(a), abs(b), 1.0):
            return True, '数值一致（%.6g）' % a, False
        if a and b:
            ratio = abs(a / b)
            for factor, name in _SCALE_HINTS:
                if abs(ratio - factor) / factor < 0.02 or abs(ratio - 1.0 / factor) * factor < 0.02:
                    return False, '单位量级疑似不一致（%s）：月报 %.6g vs 源 %.6g' % (name, a, b), True
        return False, '数值不一致：月报 %.6g vs 源 %.6g' % (a, b), True
    ok = _norm_text(report_val) == _norm_text(src_val)
    return ok, '文本' + ('一致' if ok else '不一致：月报「%s」vs 源「%s」' % (report_val, src_val)), not ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl', help='溯源.jsonl 路径')
    ap.add_argument('--base-dir', default=None, help='source_file 相对路径锚定目录（默认取 jsonl 所在目录）')
    ap.add_argument('--rel-tol', type=float, default=0.001, help='数值相对误差容忍（默认 0.001）')
    ap.add_argument('--require-anchor', action='store_true', help='无锚点记录也判硬伤')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    if not os.path.exists(args.jsonl):
        print('❌ 找不到 %s' % args.jsonl)
        sys.exit(2)
    base_dir = args.base_dir or os.path.dirname(os.path.abspath(args.jsonl))

    recs = []
    with open(args.jsonl, encoding='utf-8') as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print('❌ 第 %d 行 JSON 解析失败：%s' % (ln, e))
                sys.exit(2)

    csv_cache = {}
    results = []  # (cell, value, src_value, verdict, note) verdict ∈ ok/bad/warn/skip
    for rec in recs:
        cell = str(rec.get('cell', '?'))
        val = rec.get('value')
        if rec.get('status') == 'gap':
            results.append((cell, val, None, 'skip', 'gap（已申报缺口）'))
            continue
        sf = rec.get('source_file') or ''
        if not sf:
            results.append((cell, val, None, 'warn', '无 source_file'))
            continue
        path = sf if os.path.isabs(sf) else os.path.join(base_dir, sf)
        if path not in csv_cache:
            csv_cache[path] = _read_csv(path)
        rows = csv_cache[path]
        if rows is None:
            results.append((cell, val, None, 'bad', '源文件缺失或不可读：%s' % sf))
            continue
        if not rec.get('source_field') and rec.get('source_key') in (None, '') and rec.get('source_row') in (None, ''):
            results.append((cell, val, None, 'warn', '无锚点（未回读比对）'))
            continue
        src_val, src_field, err = _resolve(rows, rec)
        if err:
            verdict = 'warn' if err == '无锚点' and not args.require_anchor else 'bad'
            results.append((cell, val, None, verdict, err))
            continue
        ok, note, hard = _compare(val, src_val, src_field or '', args.rel_tol)
        results.append((cell, val, src_val, 'ok' if ok else 'bad', note))

    n_ok = sum(1 for r in results if r[3] == 'ok')
    n_bad = sum(1 for r in results if r[3] == 'bad')
    n_warn = sum(1 for r in results if r[3] == 'warn')
    n_skip = sum(1 for r in results if r[3] == 'skip')

    icon = {'ok': '✅', 'bad': '❌', 'warn': '🟡', 'skip': '➖'}
    lines = [
        '# 数值回读校验报告（verify_value.py）',
        '',
        '- 溯源记录：%d 条（%s）' % (len(recs), args.jsonl),
        '- 判定：✅ 回读一致 %d / ❌ 不一致或锚点失败 %d / 🟡 未回读 %d / ➖ 缺口跳过 %d' % (n_ok, n_bad, n_warn, n_skip),
        '- 数值相对误差容忍：%.4f' % args.rel_tol,
        '',
        '| 单元 | 月报值 | 源文件回读值 | 判定 | 说明 |',
        '| --- | --- | --- | --- | --- |',
    ]
    for cell, val, src_val, verdict, note in results:
        lines.append('| %s | %s | %s | %s | %s |' % (
            cell, str(val)[:24], ('' if src_val is None else str(src_val)[:24]), icon[verdict], note))
    lines += [
        '',
        '## 结论',
        '❌ 存在 %d 处硬伤：月报数字与源文件回读值不一致（或锚点失效）。逐条修正后重跑。' % n_bad if n_bad else
        '✅ 全部带锚点记录回读一致。' + ('（另有 %d 条无锚点未比对，建议补锚点）' % n_warn if n_warn else ''),
    ]

    report = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(report)
    print(report[:4000])
    print('\n===== verify_value 汇总：✅%d ❌%d 🟡%d ➖%d =====' % (n_ok, n_bad, n_warn, n_skip))
    sys.exit(1 if n_bad else 0)


if __name__ == '__main__':
    main()
