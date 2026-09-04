# -*- coding: utf-8 -*-
"""
section_completeness.py —— 章节完整性门禁（P0 阻断级）

堵住「只有目录/标题，没有实质内容」这类所有旧门禁都看不见的缺陷：
  1. 每个「章节标记」下必须有 ≥1 个实质内容块（非空正文 / 表格 / 子章节）。
     「空章节」= 该标记既无内容、又无子章节（被同级/更高级标记直接闭合）。
     容器标题（如「（一）IPO市场动态」下有「1、A股…」子标题）不算空。
  2. 章节标记 = Heading 样式段落 **或** 编号伪标题（「（1）」「（一）」「1、」开头的 Normal 段），
     后者正是「（2）美股IPO发行情况」这类 Normal 样式叶子标题（漏内容仍要被抓）。
  3. 「无 / 本期无 / 没有 / 未 / 暂无」**否定式结论**必须携带证据链：
     提供 --jsonl 时，凡正文出现否定式结论，溯源中须有 is_negative=true 记录
     （query_statement + empty_result_evidence），否则视为「没查却写无 / 查了没留痕」。

用法:
    python section_completeness.py 新月报.docx [--jsonl 溯源.jsonl] [--out 章节完整性报告.md]

退出码：存在空章节，或（--jsonl 提供时）否定式结论缺证据 → 1；否则 0。
"""
import argparse
import json
import re
import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


# 否定式结论识别：短句内出现「无/没有/未/暂无」且指代 企业/公司/上市/发行/申报/并购/再融资/融资/挂牌
# 「无」后加负向前瞻，排除 无锡/无线/无界/无缝 等地名/技术名词（非「没有」义）
_NEG_RE = re.compile(
    r'(?:没有|未有|暂无|未出现|无(?!锡|线|界|缝|人))[^。]{0,25}'
    r'(?:企业|公司|上市|发行|申报|并购|再融资|融资|挂牌|重组)'
)
# 「无」开头兜底（如「本期无」）；「无」后负向前瞻排除 无锡/无线/无界/无缝/无人 等地名技术词
_NEG_HEAD = re.compile(r'^(?:本期|本月|当月)?(?:，|,)?\s*(?:没有|未有|暂无|无(?!锡|线|界|缝|人))')
# 编号伪标题：全角「（1）/（一）」、半角「(1)」或「1、」
_NUM_MARK = re.compile(r'^(?:（\s*[0-9一二三四五六七八九十百]+\s*）|\(\s*[0-9]+\s*\)|\d+、)')


def _is_heading(p):
    s = (p.style.name if p.style else '') or ''
    return s.startswith('Heading') or ('标题' in s)


def _heading_level(p):
    s = (p.style.name if p.style else '') or ''
    m = re.search(r'(\d+)', s)
    return int(m.group(1)) if m else 0


def _is_numbered_marker(p):
    """编号伪标题（（1）/（一）/1、 开头）且为**短标签**（<25 字）才算章节标记。
    排除「（1）A 公司：8月3日…」这类事件叙述段（带冒号、70+ 字，是正文不是标题）。"""
    t = (p.text or '').strip()
    return bool(_NUM_MARK.match(t)) and len(t) < 25 and '：' not in t


def _iter_blocks(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, doc)
        elif child.tag == qn('w:tbl'):
            yield Table(child, doc)


def _is_negative(text):
    return bool(_NEG_RE.search(text) or _NEG_HEAD.search(text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('docx')
    ap.add_argument('--jsonl', default=None, help='溯源.jsonl（提供则否定式结论须带证据，硬校验）')
    ap.add_argument('--out', default='章节完整性报告.md')
    args = ap.parse_args()

    doc = Document(args.docx)

    empty = []          # 空章节标题
    negatives = []      # (父章节, 否定式文本)
    total_sections = 0

    stack = []  # [{level, title, content, has_child}]
    for blk in _iter_blocks(doc):
        if isinstance(blk, Paragraph):
            t = (blk.text or '').strip()
            is_marker = _is_heading(blk) or _is_numbered_marker(blk)
            if is_marker:
                lvl = _heading_level(blk) if _is_heading(blk) else (stack[-1]['level'] + 1 if stack else 1)
                # 闭合同级/更深章节
                while stack and stack[-1]['level'] >= lvl:
                    sec = stack.pop()
                    if sec['content'] == 0 and not sec['has_child']:
                        empty.append(sec['title'] or '（空标题）')
                if stack:
                    stack[-1]['has_child'] = True
                stack.append({'level': lvl, 'title': t, 'content': 0, 'has_child': False})
                total_sections += 1
                continue
            if not t:
                continue
            if stack:
                stack[-1]['content'] += 1
                if _is_negative(t):
                    negatives.append((stack[-1]['title'], t))
        elif isinstance(blk, Table):
            if stack:
                stack[-1]['content'] += 1
    while stack:
        sec = stack.pop()
        if sec['content'] == 0 and not sec['has_child']:
            empty.append(sec['title'] or '（空标题）')

    # 否定式结论证据链（仅 --jsonl 提供时硬校验）
    # 计数匹配而非全局布尔：正文否定式 N 条，溯源中带证据的 is_negative 记录须 ≥ N，
    # 否则 1 条带证据记录会「掩护」其余照抄旧报告的「无」。
    neg_missing_evidence = []
    neg_evidence_count = 0
    if args.jsonl:
        try:
            with open(args.jsonl, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (row.get('is_negative') or row.get('kind') == 'negative') and (
                            row.get('query_statement') or row.get('empty_result_evidence')):
                        neg_evidence_count += 1
        except OSError:
            pass
        if neg_evidence_count < len(negatives):
            neg_missing_evidence = [(sec, text) for sec, text in negatives]

    lines = [
        '# 章节完整性报告（P0：章节标记必须有内容或子章节；否定式结论必须带证据）',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 章节标记总数 | %d |' % total_sections,
        '| 空章节数 | %d |' % len(empty),
        '| 正文否定式结论数 | %d |' % len(negatives),
        '| 溯源带证据的 is_negative 记录 | %d |' % neg_evidence_count,
        '| 否定式结论缺证据数 | %d |' % len(neg_missing_evidence),
        '',
        '## 空章节（标记下无内容且无子章节，硬伤）',
    ]
    lines += (['- ❌ 「%s」' % t for t in empty] if empty else ['- ✅ 无'])
    lines += ['', '## 否定式结论（「无 / 没有 / 未」）']
    lines += (['- 「%s」→「%s」' % (sec, t[:50]) for sec, t in negatives] if negatives else ['- ✅ 无'])
    if neg_missing_evidence:
        lines += ['', '## 否定式结论缺证据（硬伤，须补 is_negative 溯源行）']
        for sec, t in neg_missing_evidence:
            lines.append('- ❌ 「%s」→「%s」：溯源中无 is_negative 记录（缺 query_statement / empty_result_evidence）'
                         % (sec, t[:50]))
    lines += ['',
              '> 规则：章节标记 = Heading 样式 或 编号伪标题（（1）/（一）/1、）；',
              '> 空章节 = 既无内容又无子章节；容器标题（有子标题）不算空；',
              '> 否定式结论若 --jsonl 提供则必须登记 is_negative=true 且带查询语句或空结果证据。']

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    hard = len(empty) + (len(neg_missing_evidence) if args.jsonl else 0)
    print('章节 %d，空章节 %d，否定式 %d，缺证据 %d → %s'
          % (total_sections, len(empty), len(negatives), len(neg_missing_evidence),
             '未通过' if hard else '通过'))
    if hard:
        sys.exit(1)


if __name__ == '__main__':
    main()
