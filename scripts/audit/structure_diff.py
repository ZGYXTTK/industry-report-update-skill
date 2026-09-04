# -*- coding: utf-8 -*-
"""
structure_diff.py —— 语义结构 diff（P1 结构层：标题树 + 表清单，old vs new）

补 format_diff.py 的盲区：format_diff 度量「格式属性签名」相似度，把「专题 4 张对比表
整体删除、换成纯文本」这种**语义结构大改**也报成 100% 通过。本脚本只比**语义结构**：
  1. 标题树（层级 + 标题文本，数字归一化后比对齐）；
  2. 每个章节下的表数量与表头签名；
输出新增/删除/标题变更/表数量增减的清单，供变更摘要逐条交代。

本脚本是 P1（报告级，exit 0）：结构变化本身可能合理（专题换主题），但必须**显式可见**，
由 reasonableness / 变更摘要逐条点名，不得静默。空章节的硬拦截在 section_completeness.py。

用法:
    python structure_diff.py 旧月报.docx 新月报.docx [--out 结构对比报告.md]
"""
import argparse
import difflib
import re
import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


def _norm(s):
    return re.sub(r'\d+', '#', (s or '').strip())


def _is_heading(p):
    s = (p.style.name if p.style else '') or ''
    return s.startswith('Heading') or ('标题' in s)


def _iter_blocks(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, doc)
        elif child.tag == qn('w:tbl'):
            yield Table(child, doc)


def _tree(doc):
    """返回 (标题序列, 每章节的表头清单)。标题序列元素 = (level, norm_title)。"""
    headings = []
    tables = []           # (当前章节 norm_title, 表头签名)
    cur = ''
    for blk in _iter_blocks(doc):
        if isinstance(blk, Paragraph):
            t = (blk.text or '').strip()
            if _is_heading(blk):
                s = (blk.style.name or '')
                m = re.search(r'(\d+)', s)
                lv = int(m.group(1)) if m else 0
                cur = _norm(t)
                headings.append((lv, cur))
        elif isinstance(blk, Table):
            if blk.rows and blk.rows[0].cells:
                hdr = tuple(_norm(c.text) for c in blk.rows[0].cells if (c.text or '').strip())
            else:
                hdr = ()
            tables.append((cur, hdr))
    return headings, tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old_docx')
    ap.add_argument('new_docx')
    ap.add_argument('--roster-note', default=None,
                    help='变更摘要.md 路径。存在删章节/删表时，须在其中显式交代（含「结构/专题/删除」关键词），否则硬拦截')
    ap.add_argument('--out', default='结构对比报告.md')
    args = ap.parse_args()

    old_h, old_t = _tree(Document(args.old_docx))
    new_h, new_t = _tree(Document(args.new_docx))

    old_titles = [t for _, t in old_h]
    new_titles = [t for _, t in new_h]
    added, removed = [], []
    sm = difflib.SequenceMatcher(None, old_titles, new_titles)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'insert':
            added += new_titles[j1:j2]
        elif tag == 'delete':
            removed += old_titles[i1:i2]

    old_tbl_hdr = [h for _, h in old_t]
    new_tbl_hdr = [h for _, h in new_t]
    tbl_del = [h for h in old_tbl_hdr if h not in new_tbl_hdr]
    tbl_add = [h for h in new_tbl_hdr if h not in old_tbl_hdr]

    lines = [
        '# 结构对比报告（P1 语义结构：标题树 + 表清单）',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 旧表数 | %d |' % len(old_t),
        '| 新表数 | %d |' % len(new_t),
        '| 新增章节 | %d |' % len(added),
        '| 删除章节 | %d |' % len(removed),
        '| 删除表头 | %d |' % len(tbl_del),
        '| 新增表头 | %d |' % len(tbl_add),
        '',
        '## 删除章节（须在变更摘要交代，不得静默）',
    ]
    lines += (['- ' + t for t in removed] if removed else ['- ✅ 无'])
    lines += ['', '## 新增章节']
    lines += (['- ' + t for t in added] if added else ['- ✅ 无'])
    lines += ['', '## 删除的表（表头签名）']
    lines += (['- ' + ' | '.join(h) for h in tbl_del] if tbl_del else ['- ✅ 无'])
    lines += ['', '## 新增的表（表头签名）']
    lines += (['- ' + ' | '.join(h) for h in tbl_add] if tbl_add else ['- ✅ 无'])
    # 结构删减必须显式交代：删章节/删表存在，且变更摘要未含「结构/专题/删除」类关键词 → 硬拦截
    _STRUCT_KW = ('结构', '专题', '删除', '移除', '替换')
    acknowledged = False
    if args.roster_note:
        try:
            with open(args.roster_note, encoding='utf-8') as f:
                note = f.read()
            acknowledged = any(k in note for k in _STRUCT_KW)
        except OSError:
            acknowledged = False
    deletion = bool(removed or tbl_del)
    block = deletion and not acknowledged

    lines += ['',
              '> 删章节/删表属结构变化，必须（1）在《变更摘要.md》逐条交代，且（2）变更摘要含「结构/专题/删除」类关键词，',
              '> 否则本门禁硬拦截（P0）。本节已检测到删除：%s；变更摘要交代：%s。'
              % ('是' if deletion else '否', '是' if acknowledged else '否')]

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('结构 diff：删章节 %d / 增章节 %d / 删表 %d / 增表 %d → %s'
          % (len(removed), len(added), len(tbl_del), len(tbl_add),
             '未通过（结构删减未在变更摘要交代）' if block else '通过'))
    if block:
        sys.exit(1)


if __name__ == '__main__':
    main()
