# -*- coding: utf-8 -*-
"""
format_diff.py —— 格式对比门禁（v3：run 级 rPr + 序列对齐 + 结构/格式分离 + 图片/关系ID豁免）

v3 相对 v2 的改进（对应「门禁失真」优化项）：
  1. --ignore-images（默认开启）：跳过 <w:drawing>/<mc:AlternateContent>/<w:pict>/<a:blip>
     等嵌入图片/对象的子树，避免封面图/产品图的 base64 二进制被逐字节比对，
     造成海量「格式回归」噪音；
  2. 跳过关系 ID（r:id/r:embed/r:link）与随机 ID（w14:paraId/textId）属性——
     这些值在不同 docx 之间必然不同，与「格式」无关；
  3. 跳过疑似二进制属性值（长度 > 200，如 gfxdata 的 base64）。
  结构变化（增删块/行）仍单独列示、不计入相似度；相似度只衡量「格式属性」。

用法:
    python format_diff.py 旧月报.docx 新月报.docx [--threshold 0.95] [--no-ignore-images] [--out 格式对比报告.md]
"""
import argparse
import difflib
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TOTAL_KEYS = ('合计', '总计', '小计')

# 嵌入图片/对象容器：子树整体跳过（不计入格式比对）
SKIP_TAGS = {
    'drawing', 'pict', 'blip', 'imagedata', 'AlternateContent', 'Fallback',
    'object', 'OLEObject', 'shape', 'group', 'fldData', 'binData',
}
# 关系 ID / 随机 ID / 二进制数据属性：值跨文档必然不同，与格式无关
SKIP_ATTRS = {
    'id', 'embed', 'link', 'relid', 'paraId', 'textId', 'gfxdata', 'uid',
    'dm', 'loext', 'durableId', 'w14:textId', 'w14:paraId',
}


def _local(tag):
    return tag.split('}')[-1]


def _text(el):
    return ''.join((t.text or '') for t in el.iter(W + 't'))


def _norm(s):
    """数字归一化：'截至6月末共16家' -> '截至#月末共#家'，让同段落数值更新仍能对齐。"""
    return re.sub(r'\d+', '#', (s or '').strip())


def _is_binary(v):
    """判定属性值是否为二进制（base64 等），避免逐字节比对。"""
    return v is not None and len(v) > 200


def _skip_subtree(el):
    return _local(el.tag) in SKIP_TAGS


def _diff_fmt_stats(el_a, el_b, path, diffs, ignore_images):
    """递归比较两棵「已对齐」元素树的格式。返回 (compared, matched)。"""
    compared = 0
    matched = 0
    ta, tb = _local(el_a.tag), _local(el_b.tag)
    if ta != tb:
        diffs.append((path, 'tag', ta, tb))
        return 0, 0
    attrs_a = {k.split('}')[-1]: v for k, v in el_a.attrib.items()}
    attrs_b = {k.split('}')[-1]: v for k, v in el_b.attrib.items()}
    for k in sorted(set(attrs_a) | set(attrs_b)):
        va, vb = attrs_a.get(k), attrs_b.get(k)
        # 跳过关系ID/随机ID/二进制属性
        if k in SKIP_ATTRS or (ignore_images and (_is_binary(va) or _is_binary(vb))):
            continue
        compared += 1
        if va == vb:
            matched += 1
        else:
            diffs.append((path, 'attr:' + k, str(va), str(vb)))
    children_a = [c for c in el_a if _local(c.tag) != 't' and not _skip_subtree(c)]
    children_b = [c for c in el_b if _local(c.tag) != 't' and not _skip_subtree(c)]
    for i in range(min(len(children_a), len(children_b))):
        c, m = _diff_fmt_stats(children_a[i], children_b[i],
                               '%s/%s[%d]' % (path, _local(children_a[i].tag), i), diffs, ignore_images)
        compared += c
        matched += m
    if len(children_a) != len(children_b):
        compared += 1
        diffs.append((path, 'children-count', str(len(children_a)), str(len(children_b))))
    return compared, matched


def _para_token(p):
    return ('p', _norm(_text(p)))


def _tbl_row_token(tr):
    cells = tr.findall(W + 'tc')
    return _norm(_text(cells[0])) if cells else ''


def _describe(a_blocks, b_blocks):
    def one(blocks):
        out = []
        for b in blocks[:3]:
            t = _norm(_text(b))[:15]
            out.append('%s:%s' % (_local(b.tag), t or '…'))
        return '、'.join(out) + ('…' if len(blocks) > 3 else '')
    return '旧[%s] → 新[%s]' % (one(a_blocks), one(b_blocks))


def _compare_tables(tbl_a, tbl_b, path, diffs, struct, ignore_images):
    """对齐表格行（按首列键），对齐行内递归比格式。返回 (compared, matched)。"""
    compared = matched = 0
    tblPr_a = tbl_a.find(W + 'tblPr')
    tblPr_b = tbl_b.find(W + 'tblPr')
    if tblPr_a is not None and tblPr_b is not None:
        c, m = _diff_fmt_stats(tblPr_a, tblPr_b, path + '/tblPr', diffs, ignore_images)
        compared += c
        matched += m
    grid_a = tbl_a.find(W + 'tblGrid')
    grid_b = tbl_b.find(W + 'tblGrid')
    if grid_a is not None and grid_b is not None:
        c, m = _diff_fmt_stats(grid_a, grid_b, path + '/tblGrid', diffs, ignore_images)
        compared += c
        matched += m
    rows_a = tbl_a.findall(W + 'tr')
    rows_b = tbl_b.findall(W + 'tr')
    keys_a = [_tbl_row_token(r) for r in rows_a]
    keys_b = [_tbl_row_token(r) for r in rows_b]
    sm = difflib.SequenceMatcher(None, keys_a, keys_b)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for a, b in zip(range(i1, i2), range(j1, j2)):
                c, m = _diff_fmt_stats(rows_a[a], rows_b[b], '%s/行%d' % (path, a), diffs, ignore_images)
                compared += c
                matched += m
        else:
            struct.append('%s 行（%s）：%s'
                          % (tag, path, _describe(list(rows_a[i1:i2]), list(rows_b[j1:j2]))))
    return compared, matched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old_docx')
    ap.add_argument('new_docx')
    ap.add_argument('--threshold', type=float, default=0.95)
    ap.add_argument('--no-ignore-images', action='store_true',
                    help='关闭图片豁免（恢复 v2 逐字节比对，仅调试用）')
    ap.add_argument('--out', default='格式对比报告.md')
    args = ap.parse_args()
    ignore_images = not args.no_ignore_images

    def load(path):
        with zipfile.ZipFile(path) as z:
            return ET.fromstring(z.read('word/document.xml'))

    old_root = load(args.old_docx)
    new_root = load(args.new_docx)

    old_body = old_root.find(W + 'body')
    new_body = new_root.find(W + 'body')
    old_blocks = [el for el in old_body if _local(el.tag) in ('p', 'tbl')] if old_body is not None else []
    new_blocks = [el for el in new_body if _local(el.tag) in ('p', 'tbl')] if new_body is not None else []

    old_tokens = [_para_token(b) if _local(b.tag) == 'p' else ('tbl',) for b in old_blocks]
    new_tokens = [_para_token(b) if _local(b.tag) == 'p' else ('tbl',) for b in new_blocks]

    compared = 0
    matched = 0
    diffs = []
    struct = []

    sm = difflib.SequenceMatcher(None, old_tokens, new_tokens)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for a, b in zip(range(i1, i2), range(j1, j2)):
                oa, ob = old_blocks[a], new_blocks[b]
                if _local(oa.tag) == 'p' and _local(ob.tag) == 'p':
                    c, m = _diff_fmt_stats(oa, ob, '段落%d' % a, diffs, ignore_images)
                    compared += c
                    matched += m
                elif _local(oa.tag) == 'tbl' and _local(ob.tag) == 'tbl':
                    c, m = _compare_tables(oa, ob, '表%d' % a, diffs, struct, ignore_images)
                    compared += c
                    matched += m
        else:
            struct.append('%s 块：%s' % (tag, _describe(old_blocks[i1:i2], new_blocks[j1:j2])))

    sect_old = old_body.find(W + 'sectPr') if old_body is not None else None
    sect_new = new_body.find(W + 'sectPr') if new_body is not None else None
    if sect_old is not None and sect_new is not None:
        c, m = _diff_fmt_stats(sect_old, sect_new, 'sectPr', diffs, ignore_images)
        compared += c
        matched += m
    elif (sect_old is None) != (sect_new is None):
        struct.append('sectPr 存在性不一致（页边距可能丢失）')

    score = (matched / compared) if compared else 1.0
    passed = score >= args.threshold

    lines = [
        '# 格式对比报告（v3：run级 + 序列对齐 + 结构/格式分离 + 图片/关系ID豁免）',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 相似度评分 | %.1f%% |' % (score * 100),
        '| 比对属性数 | %d |' % compared,
        '| 匹配数 | %d |' % matched,
        '| 结构变化（增删块/行，不计分） | %d |' % len(struct),
        '| 格式回归（属性差异） | %d |' % len(diffs),
        '| 图片豁免 | %s |' % ('开启' if ignore_images else '关闭'),
        '| 阈值 | %.0f%% |' % (args.threshold * 100),
        '| 结论 | %s |' % ('✅ 通过' if passed else '❌ 未通过'),
        '',
        '## 结构变化（不计入相似度）',
    ]
    if struct:
        for s in struct[:50]:
            lines.append('- ' + s.replace('|', '\\|'))
    else:
        lines.append('- ✅ 无')
    lines += ['', '## 格式回归明细（计入相似度，前 100 条）']
    if diffs:
        for d in diffs[:100]:
            lines.append('- %s %s：旧=%s 新=%s' % (d[0], d[1], d[2], d[3]))
    else:
        lines.append('- ✅ 无')

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('相似度 %.1f%%（阈值 %.0f%%，图片豁免%s）→ %s；结构变化 %d，格式回归 %d'
          % (score * 100, args.threshold * 100, '开启' if ignore_images else '关闭',
             '通过' if passed else '未通过', len(struct), len(diffs)))
    if not passed:
        sys.exit(1)


if __name__ == '__main__':
    main()
