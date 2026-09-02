# -*- coding: utf-8 -*-
"""Dump docx structure: paragraphs & tables with indices, for data-flow audit."""
import sys, json, io
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = sys.argv[1]
doc = Document(path)

def iter_block_items(parent):
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)

out = []
tbl_idx = 0
for block in iter_block_items(doc):
    if isinstance(block, Paragraph):
        style = block.style.name if block.style is not None else ''
        text = block.text
        if text.strip() or style.startswith('Heading') or style.lower().startswith('标题'):
            out.append(("P", style, text.strip()))
    else:
        rows = len(block.rows)
        cols = len(block.columns)
        first_row = " | ".join((c.text.strip().replace("\n", "␤")[:30]) for c in block.rows[0].cells[:12]) if rows else ""
        out.append(("T%d" % tbl_idx, "table %dx%d" % (rows, cols), first_row))
        tbl_idx += 1

for i, (kind, style, text) in enumerate(out):
    print(f"[{i:04d}] {kind:6s} [{style}] {text[:220]}")
