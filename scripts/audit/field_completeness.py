# -*- coding: utf-8 -*-
"""
field_completeness.py —— 字段完整性门禁（P0 阻断级，只查「新行自身」，不依赖旧值）

补 diff_empty.py 的盲区：diff_empty 只抓「旧有值→新空值」（同业务键跨月丢字段），
抓不到「整批换血的新行自身漏填」。本脚本只读新月报表格，按表头识别必填字段：
  行业动态表 → 标的公司名称 / 所在城市 / 法定代表人（公司类）必填；
  投融资表   → 融资方 / 所在地区 必填；交易轮次 / 融资金额 / 投资方 为警告级；
  其余含「公司简称/公司名称」的表 → 键列必填。

「—/空」判定：空串、'-'、'—'、'--'、'－' 均视为空。
法定代表人允许「—」的豁免：事件分类 ∈ 展会/报告/赛事/组织/政策，或所在城市 ∈ 海外，或公司名含组织关键词。

用法:
    python field_completeness.py 新月报.docx [--out 字段完整性报告.md]

退出码：存在必填字段为空（硬伤）→ 1；仅警告级 → 0。
"""
import argparse
import re
import sys

from docx import Document

_EMPTY = ('', '-', '—', '--', '－', '－')


def _norm(s):
    """表头匹配归一化：去所有空白（含单元格内换行 ␤），'所在\n地区'→'所在地区'。"""
    return re.sub(r'\s+', '', (s or ''))

# 非公司/组织类事件（不适用「法定代表人」）
_NON_COMPANY_CLASS = ('行业展会', '数据报告', '行业赛事', '行业组织', '政策')
# 组织关键词（公司名含之则免法定代表人）
_ORG_KEYWORDS = ('大会', '百人会', '运动会', '论坛', '研究院', '协会', 'Counterpoint', 'World')
# 海外城市/地区值（免法定代表人）
_OVERSEAS = ('海外', '美国', '日本', '韩国', '德国', '英国', '新加坡')


def _cell_ok(v):
    return (v or '').strip() not in _EMPTY


def _has(header, kw):
    """精确匹配（去空白后相等），非子串——否则「融资方」⊂「融资方式」误命中。"""
    return any(_norm(h) == _norm(kw) for h in header)


def _col(header, kw):
    for i, h in enumerate(header):
        if _norm(h) == _norm(kw):
            return i
    return None


def _row_cells(row, cols):
    return [(row.cells[i].text or '').strip() if i < len(row.cells) else '' for i in range(cols)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('docx')
    ap.add_argument('--out', default='字段完整性报告.md')
    args = ap.parse_args()

    doc = Document(args.docx)
    hard, warn = [], []

    for ti, tbl in enumerate(doc.tables, 1):
        if not tbl.rows:
            continue
        header = [(c.text or '').strip() for c in tbl.rows[0].cells]
        nc = len(tbl.columns)
        data = tbl.rows[1:]

        # 投融资表：融资方 + 所在地区 必填
        if _has(header, '融资方') and _has(header, '所在地区'):
            c_name = _col(header, '融资方')
            c_area = _col(header, '所在地区')
            c_round = _col(header, '交易轮次')
            c_amt = _col(header, '融资金额')
            c_inv = _col(header, '投资方')
            for ri, row in enumerate(data, 2):
                cells = _row_cells(row, nc)
                name = cells[c_name] if c_name is not None else ''
                area = cells[c_area] if c_area is not None else ''
                if not _cell_ok(name):
                    hard.append('表%d[%d] 融资方为空' % (ti, ri))
                if not _cell_ok(area):
                    hard.append('表%d[%d] %s：所在地区为空（应可经 Wind/烯牛/IT桔子 补）'
                                % (ti, ri, name[:20]))
                for cidx, label in ((c_round, '交易轮次'), (c_amt, '融资金额'), (c_inv, '投资方')):
                    if cidx is not None and not _cell_ok(cells[cidx]):
                        warn.append('表%d[%d] %s：%s为空（可能媒体未披露）'
                                    % (ti, ri, name[:20], label))
            continue

        # 行业动态表：标的公司名称 / 所在城市 / 法定代表人(公司类) 必填
        if _has(header, '标的公司名称') and _has(header, '法定代表人'):
            c_name = _col(header, '标的公司名称')
            c_city = _col(header, '所在城市')
            c_legal = _col(header, '法定代表人')
            c_cls = _col(header, '事件分类') or _col(header, '公司分类')
            for ri, row in enumerate(data, 2):
                cells = _row_cells(row, nc)
                name = cells[c_name] if c_name is not None else ''
                city = cells[c_city] if c_city is not None else ''
                legal = cells[c_legal] if c_legal is not None else ''
                cls = cells[c_cls] if c_cls is not None else ''
                if not _cell_ok(name):
                    hard.append('表%d[%d] 标的公司名称为空' % (ti, ri))
                if not _cell_ok(city):
                    hard.append('表%d[%d] %s：所在城市为空' % (ti, ri, name[:20]))
                # 法定代表人豁免：非公司类事件 / 海外 / 组织名
                exempt = (cls in _NON_COMPANY_CLASS or city in _OVERSEAS
                          or any(k in name for k in _ORG_KEYWORDS))
                if not exempt and not _cell_ok(legal):
                    hard.append('表%d[%d] %s（城市=%s）：法定代表人为空（应可经 qcc 补）'
                                % (ti, ri, name[:20], city[:10]))
            continue

        # 其余结构化表（发行/在审/辅导/再融资/并购）：键列必填
        if _has(header, '公司简称') or _has(header, '公司名称'):
            c_key = _col(header, '公司简称') or _col(header, '公司名称')
            for ri, row in enumerate(data, 2):
                cells = _row_cells(row, nc)
                key = cells[c_key] if c_key is not None else ''
                if not _cell_ok(key):
                    hard.append('表%d[%d] 公司简称/名称为空' % (ti, ri))

    lines = [
        '# 字段完整性报告（P0：新行自身必填字段非空，不依赖旧值）',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 必填缺失（硬伤） | %d |' % len(hard),
        '| 警告级缺失 | %d |' % len(warn),
        '',
        '## 必填缺失（硬伤，必补）',
    ]
    lines += (['- ❌ ' + s for s in hard] if hard else ['- ✅ 无'])
    lines += ['', '## 警告级缺失（可能媒体未披露，人工确认）']
    lines += (['- ⚠️ ' + s for s in warn] if warn else ['- ✅ 无'])
    lines += ['',
              '> 规则：投融资表 融资方/所在地区 必填；行业动态表 标的公司名称/所在城市/法定代表人(公司类) 必填；',
              '> 法定代表人豁免 = 展会/报告/赛事/组织/政策 或 海外 或 组织名；「—」= 空。']

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('必填缺失 %d，警告 %d → %s' % (len(hard), len(warn), '未通过' if hard else '通过'))
    if hard:
        sys.exit(1)


if __name__ == '__main__':
    main()
