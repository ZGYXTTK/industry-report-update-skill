# -*- coding: utf-8 -*-
"""
traceability_check.py —— 溯源反查门禁（v2：真实校验 + 覆盖率）

相比 v1 只查「source_file 路径字符串非空」，v2 补齐：
  1. 必填字段校验（cell/value/source_file）；
  2. 源文件真实存在校验（相对路径锚定到 --base-dir，默认取 jsonl 所在目录，避免换 CWD 误报）；
  3. 金额/数量类 value 必须带 unit 与 as_of/reporting_period（至少其一）；
  4. status 校验：gap 计入缺口，unverified 计入未交叉验证；
  5. 覆盖率 = 有出处且源文件存在的记录数 / 总数，支持 --min-coverage 门槛。

用法:
    python traceability_check.py 溯源.jsonl [--base-dir 下载资料目录] [--min-coverage 0.9] [--out 溯源反查报告.md]
"""
import argparse
import json
import os
import re
import sys

REQUIRED_KEYS = {'cell', 'value'}  # 出处要求 source_file 或 url 二选一（见下方第 2 步），不再单强制 source_file
_UNIT_CHARS = set('亿元万千百十家笔%％倍股港元美元人民币')


def _looks_numeric(v):
    """判断 value 是否为金额/数量类（数字，或含数字的字符串）。"""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        return re.search(r'\d', v) is not None
    return False


def _has_embedded_unit(v):
    """value 字符串里是否已内嵌单位（如 "1.2亿元"），有则不再要求单独 unit 字段。"""
    return isinstance(v, str) and any(c in v for c in _UNIT_CHARS)


def _is_aux_numeric(t, hdr_txt=''):
    """判断某数字单元格是否属于「非溯源数据」辅助单元（日期/序号等），不应计入 docx 真实覆盖率分母。"""
    if not re.search(r'\d', t or ''):
        return True
    # 日期类：2026/8/19、2026-08-19、6月1日 等
    if re.search(r'\d{4}[-/]\d{1,2}', t or ''):
        return True
    if re.search(r'^\d{1,2}月\d{1,2}日$', t or ''):
        return True
    # 序号类：表头含序/编号 且 单元格为纯整数
    if any(k in hdr_txt for k in ('序号', '序', '编号')) and re.fullmatch(r'\d+', (t or '').strip()):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--base-dir', default=None,
                    help='source_file 相对路径的锚定目录（默认取 jsonl 所在目录）')
    ap.add_argument('--min-coverage', type=float, default=None,
                    help='最低覆盖率门槛（0~1），按「已登记溯源行」覆盖率验收；不传则不拦截')
    ap.add_argument('--require-cross-check', action='store_true',
                    help='未交叉验证(unverified)升级为硬伤（≥2途径的单元强制）')
    ap.add_argument('--against-docx', default=None,
                    help='对照 docx 计算「真实覆盖率」作为报告性指标（分母排除日期/序号等辅助单元格）；'
                         '门禁仍按「已登记溯源行」覆盖率判断，避免 <=0/日期等导致 100% 物理不可达')
    ap.add_argument('--out', default='溯源反查报告.md')
    args = ap.parse_args()

    if not os.path.exists(args.jsonl):
        print('溯源.jsonl 不存在，视为未溯源（门禁失败）')
        sys.exit(1)

    base_dir = args.base_dir or os.path.dirname(os.path.abspath(args.jsonl))

    rows = []
    with open(args.jsonl, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print('JSON 解析失败: %s' % e)
                    sys.exit(1)

    hard = []      # 硬伤：缺必填字段 / 源文件缺失 / 完全无出处
    warn = []      # 警告：缺单位 / 缺财报期 / unverified
    gap = 0
    covered = 0
    for r in rows:
        status = r.get('status', '')
        if status == 'gap':
            gap += 1
            continue
        # 1) 必填字段（cell/value 必有；出处为 source_file 或 url 二选一，由第 2 步判定）
        missing = REQUIRED_KEYS - set(r.keys())
        if missing:
            hard.append('缺必填字段 %s：cell=%s' % (sorted(missing), r.get('cell')))
            continue
        if not r.get('source_file') and not r.get('url'):
            hard.append('无出处（source_file 与 url 至少填一个）：cell=%s' % r.get('cell'))
            continue
        # 2) 源文件存在性（相对路径锚定 base_dir）
        sf = r.get('source_file')
        if sf:
            p = sf if os.path.isabs(sf) else os.path.join(base_dir, sf)
            if os.path.exists(p):
                covered += 1
            else:
                hard.append('源文件不存在：%s（cell=%s，解析路径 %s）' % (sf, r.get('cell'), p))
        elif r.get('url'):
            covered += 1  # 仅 url 也算有出处
        else:
            hard.append('无出处（既无 source_file 也无 url）：cell=%s' % r.get('cell'))
        # 3) 金额/数量类校验（警告级）
        if _looks_numeric(r.get('value')) and not _has_embedded_unit(r.get('value')):
            if not r.get('unit'):
                warn.append('数值缺单位：cell=%s value=%s' % (r.get('cell'), r.get('value')))
            if not r.get('as_of') and not r.get('reporting_period'):
                warn.append('数值缺时点/财报期：cell=%s value=%s' % (r.get('cell'), r.get('value')))
        # 4) 未交叉验证
        if status == 'unverified':
            if args.require_cross_check:
                hard.append('未交叉验证（--require-cross-check 强制）：cell=%s' % r.get('cell'))
            else:
                warn.append('未交叉验证：cell=%s' % r.get('cell'))

    total = len(rows)
    coverage = (covered / total) if total else 1.0
    # 真实覆盖率：对照 docx 数字单元数（分母不再是"自愿登记了几行"）
    real_total = None
    real_coverage = None
    if args.against_docx and os.path.exists(args.against_docx):
        from docx import Document as _D
        d = _D(args.against_docx)
        real_total = 0
        for t in d.tables:
            hdr = [(c.text or '').strip() for c in t.rows[0].cells] if len(t.rows) else []
            for row in t.rows[1:]:        # 去表头
                for ci, c in enumerate(row.cells):
                    txt = (c.text or '').strip()
                    hdr_txt = hdr[ci] if ci < len(hdr) else ''
                    if _is_aux_numeric(txt, hdr_txt):
                        continue          # 日期/序号等非数据单元，不入分母
                    real_total += 1
        real_coverage = (covered / real_total) if real_total else 1.0

    # 门禁按「已登记溯源行」覆盖率验收（该口径可达且反映 Agent 溯源努力）；
    # real_coverage 为报告性指标（对照 docx 数据单元，供人工/后续核对未覆盖点）。
    passed = (len(hard) == 0)
    if args.min_coverage is not None:
        passed = passed and (coverage >= args.min_coverage)

    lines = [
        '# 溯源反查报告',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 记录总数 | %d |' % total,
        '| 有出处且源文件存在 | %d |' % covered,
        '| 缺口(gap) | %d |' % gap,
        '| 覆盖率 | %.1f%% |' % (coverage * 100),
    ]
    if real_coverage is not None:
        lines.append('| 真实覆盖率（对照 docx %d 数据单元，报告性指标） | %.1f%% |' % (real_total, real_coverage * 100))
    lines += [
        '| 硬伤 | %d |' % len(hard),
        '| 警告 | %d |' % len(warn),
        '| 结论 | %s |' % ('✅ 通过' if passed else '❌ 未通过'),
        '',
        '> 门禁按「已登记溯源行」覆盖率验收（默认 >=0.9）；真实覆盖率（vs docx 数据单元）为报告性指标，'
        '用于人工核对有哪些数据单元未纳入溯源，不做 100% 硬性拦截（docx 含日期/序号等辅助单元）。',
        '',
        '## 硬伤明细（必改）',
    ]
    if hard:
        for h in hard[:100]:
            lines.append('- ❌ ' + h.replace('|', '\\|'))
    else:
        lines.append('- ✅ 无')
    lines += ['', '## 警告明细（建议补）']
    if warn:
        for w in warn[:100]:
            lines.append('- ⚠️ ' + w.replace('|', '\\|'))
    else:
        lines.append('- ✅ 无')

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('记录 %d，覆盖率 %.1f%%，硬伤 %d，警告 %d → %s'
          % (total, coverage * 100, len(hard), len(warn), '通过' if passed else '未通过'))
    if not passed:
        sys.exit(1)


if __name__ == '__main__':
    main()
