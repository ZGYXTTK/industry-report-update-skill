# -*- coding: utf-8 -*-
"""
cross_consistency_check.py —— 交叉一致性门禁（段落结论数字 vs 表格行数）

背景：consistency_check.py 只查「表内合计=分项和」，不查「段落写的『共 N 家』
与表格实际行数是否一致」。本次月报就出现「正文写 23 家港股在审，表里却 30 行」。
本脚本补齐这一盲区：抽取正文「共 N 家/N 笔/N 条」类结论，与紧随其后的表格
数据行数比对，不一致即硬伤。

匹配策略：按文档顺序遍历 body 元素；遇到「共 N 家/N 笔/N 条」段落，记录 N，
再找其后**第一个**表格，用其数据行数（去表头）与 N 比较。容忍 ±1（部分表含脚注行）。

v2 增补：
  1. 模糊量词：≥ / ≤ / 至少 / 超过 / 不足 → 用区间匹配（表格行数 ∈ [N, N+tolerance]）
  2. 「增」「多」「新增」等动词开头的句子 → N 仅做下限校验

用法:
    python cross_consistency_check.py 新月报.docx [--out 交叉一致性报告.md]
"""
import argparse
import re
import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

# 「(共)有 N 家/N 笔/N 条」结论句（含 共计/总计/一共/累计 前缀）
NUM_UNIT = re.compile(r'(?<!拥)(?<!具)(?<!含)(?:共计|总计|一共|累计|共有?|有)\s*(\d+)\s*(家|笔|条)')
# 「N 家 公司/企业/事件/交易/项目」或「N 家 在审/辅导/过会/受理/终止 等状态」
NUM_UNIT2 = re.compile(r'(\d+)\s*(家|笔|条)\s*(?:公司|企业|事件|交易|项目|在审|辅导|过会|受理|终止|申报|发行)')
# 模糊量词区间匹配：≥ / 至少 / 超过 / ≥X家以上 → 表格行数 ≥ N 即可（允许小幅上浮）
FUZZY_GE = re.compile(r'(?:≥|至少|超过|不少于)\s*(\d+)\s*(家|笔|条)')
FUZZY_LE = re.compile(r'(?:≤|不超过|至多|不多于)\s*(\d+)\s*(家|笔|条)')
# 「增 X 家」/「多 X 家」类：仅校验下限
ADD_COUNT = re.compile(r'(?:增|多|新增|净增)\s*(\d+)\s*(家|笔|条)')

# 只保留「家/笔/条」三个真正映射到表格行数的量词；
# 排除「项/个」（"7项国标""88个自由度""50个场景"是政策/事件量词，不是表格行数）
_UNITS = set('家笔条')


def _iter_block_items(doc):
    """按文档顺序产出段落与表格（python-docx 的 paragraphs/tables 是分列的，这里合并）。"""
    from docx.oxml.ns import qn
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, doc)
        elif child.tag == qn('w:tbl'):
            yield Table(child, doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('docx')
    ap.add_argument('--out', default='交叉一致性报告.md')
    args = ap.parse_args()

    doc = Document(args.docx)
    pending = []        # 待匹配的 (N, 量词, 段落文本摘要)
    issues = []
    matches = []

    for blk in _iter_block_items(doc):
        if isinstance(blk, Paragraph):
            t = blk.text.strip()
            if not t:
                continue
            # 优先级 1：精确匹配（含 "共有 X 家" / "X 家企业"）
            m = NUM_UNIT.search(t)
            if not m:
                m = NUM_UNIT2.search(t)
            # 优先级 2：≥ / ≤ 类模糊量词
            if not m:
                m = FUZZY_GE.search(t) or FUZZY_LE.search(t)
            # 优先级 3：「增 X 家」类（仅做下限）
            if not m:
                m = ADD_COUNT.search(t)
            if m and m.group(2) in _UNITS:
                kind = 'exact'
                if m.re.pattern == FUZZY_GE.pattern:
                    kind = 'ge'
                elif m.re.pattern == FUZZY_LE.pattern:
                    kind = 'le'
                elif m.re.pattern == ADD_COUNT.pattern:
                    kind = 'add'
                pending.append((int(m.group(1)), m.group(2), t[:40], kind))
        elif isinstance(blk, Table):
            if pending:
                # 数据行数 = 总行 - 表头 - 合计/小计/来源/注脚行
                skip = 1  # 表头
                for r in blk.rows[1:]:
                    first = r.cells[0].text.strip() if r.cells else ''
                    if any(k in first for k in ('合计', '总计', '小计', '来源', '数据来源', '注')):
                        skip += 1
                data_rows = max(len(blk.rows) - skip, 0)
                n, unit, snippet, kind = pending.pop(0)
                # 模糊匹配规则：
                #  exact: |data_rows - n| ≤ 1
                #  ge: data_rows ≥ n（允许上浮 2）
                #  le: data_rows ≤ n（允许下浮 2）
                #  add: data_rows ≥ n（"增 X 家" 不能少）
                ok = False
                if kind == 'exact':
                    ok = abs(data_rows - n) <= 1
                    msg = '正文「%s…（共 %d%s）」↔ 表格 %d 行' % (snippet, n, unit, data_rows)
                elif kind == 'ge':
                    ok = data_rows >= n
                    msg = '正文「%s…（≥%d%s）」↔ 表格 %d 行' % (snippet, n, unit, data_rows)
                elif kind == 'le':
                    ok = data_rows <= n
                    msg = '正文「%s…（≤%d%s）」↔ 表格 %d 行' % (snippet, n, unit, data_rows)
                elif kind == 'add':
                    ok = data_rows >= n
                    msg = '正文「%s…（增%d%s）」↔ 表格 %d 行' % (snippet, n, unit, data_rows)
                if ok:
                    matches.append(msg + ' ✅')
                else:
                    issues.append('❌ ' + msg + '（超出容忍）')

    lines = [
        '# 交叉一致性报告（正文结论数字 vs 表格行数，v2 模糊量词区间匹配）',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 结论句匹配数 | %d |' % len(matches),
        '| 不一致数 | %d |' % len(issues),
        '| 未匹配到表格的结论 | %d |' % len(pending),
        '',
        '## 命中（一致）',
    ]
    if matches:
        lines += ['- ' + m for m in matches]
    else:
        lines.append('- 无')
    lines += ['', '## 不一致（硬伤，必改）']
    if issues:
        lines += ['- ❌ ' + s for s in issues]
    else:
        lines.append('- ✅ 无')
    if pending:
        lines += ['', '## 未匹配到后续表格的结论（提示）']
        for item in pending:
            n, unit, sn = item[0], item[1], item[2]
            lines.append('- 「%s…（共 %d%s）」未找到其后表格，请人工核对' % (sn, n, unit))

    lines += ['', '> 匹配规则：exact=容忍±1；ge/le=单边容忍2；add=下限匹配（≥N）。']
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('结论匹配 %d，不一致 %d，未匹配 %d → %s'
          % (len(matches), len(issues), len(pending), '通过' if not issues else '未通过'))
    if issues:
        sys.exit(1)


if __name__ == '__main__':
    main()
