# -*- coding: utf-8 -*-
"""
build_report.py —— 声明式月报构建引擎（P2-1/P2-2）

把「内容 JSON → 月报 docx」从每期手写 500 行构建脚本，变为声明式操作列表。
行业包/研究子 Agent 把采到的内容写进 content/ 目录，本引擎按 ops 顺序执行。

用法：
  python scripts/build_report.py --template 旧月报.docx \
      --content runs/<run-id>/content --out runs/<run-id>/output/新月报.docx

content/ 目录约定（P2-2）：
  meta.json          必需，结构见 templates/content-schema-example.json
  *.png/jpg          可选，replace_image 引用的重生成图表
  hooks.py           可选，行业包自定义 op（def run(ed: DocEditor, content: dict)）

ops 操作类型（按序执行）：
  set_text_prefix     {prefix, text}          前缀定位段落，run 保留式改写
  set_text_contains   {sub, text}             包含定位段落，run 保留式改写
  replace_range       {start, end, items[]}   start~end 锚点间段落整体替换
  insert_after_para   {prefix, text}          段落后插入（继承格式）
  delete_contains     {patterns[], start_prefix?}  包含匹配删除残句/残留段
  strip_vmerge        {table}
  fill_table          {table: {index|header_contains}, rows[[]], start_row?}
  note_after_table    {table, text}           表后插入说明段
  replace_image       {target, path}          word/media 字节替换
  exec_python         {file}                  行业包自定义钩子（def run(ed, content)）

全局开关（meta.json → build_options 覆盖；CLI flag 覆盖 meta）：
  --auto-fmt-narrative / 默认开
    描述类 item（X 月 Y 日 开头的字符串）自动包裹为 {text, fmt:{b:False, rFonts:anchor_font}}
    以消除 replace_range 从 anchor 继承粗体导致的「叙述段被强制加粗」问题；
    新模板/新手作者无需手动为每条叙述 item 加 fmt override。
  --no-auto-fmt-narrative 关闭
"""
import argparse
import importlib.util
import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from docx import Document  # noqa: E402  (保留以备后续 anchor 字体探测)
from docx.oxml.ns import qn  # noqa: E402
from docx_build import DocEditor  # noqa: E402


# 叙述类日期段判定（与 gen_meta1.py 中一致）
NARRATIVE_PAT = re.compile(r"^\s*\d{1,2}\s*[月]\s*\d{1,2}\s*日")


def _peek_anchor_font(ed, start_prefix):
    """从 anchor 段（以 start_prefix 开头的段落）抽取首个 run 的 rFonts ascii 属性。"""
    for p in ed.paras():
        if not p.text.strip().startswith(start_prefix):
            continue
        for r in p.runs:
            rpr = r._element.find(qn("w:rPr"))
            if rpr is None:
                continue
            rf = rpr.find(qn("w:rFonts"))
            if rf is None:
                continue
            ascii = rf.get(qn("w:ascii"))
            if ascii:
                return ascii
        return None
    return None


def annotate_narrative_fmt(content, ed, enable=True):
    """把 content['ops'] 中所有 replace_range items 里的「日期 X 月 Y 日 开头」字符串项
    自动包裹为 {text, fmt:{b:False, rFonts:anchor_font}}，以关闭 anchor 继承的粗体并补字体 hint。
    已存在的 dict 项（含 fmt override）原样保留。
    """
    if not enable:
        return content
    for op in content.get("ops") or []:
        if op.get("op") != "replace_range":
            continue
        items = op.get("items")
        if not items:
            continue
        anchor_font = _peek_anchor_font(ed, op.get("start", "")) or None
        new_items = []
        for it in items:
            if isinstance(it, dict):
                new_items.append(it)
                continue
            if isinstance(it, str) and NARRATIVE_PAT.match(it.strip()):
                fmt = {"b": False}
                if anchor_font:
                    fmt["rFonts"] = anchor_font
                new_items.append({"text": it, "fmt": fmt})
            else:
                new_items.append(it)
        op["items"] = new_items
    return content


def _resolve_table(ed, spec):
    return ed.find_table(index=spec.get('index'),
                         header_contains=spec.get('header_contains'))


def apply_ops(ed, ops, content_dir):
    for op in ops:
        kind = op.get('op')
        if kind == 'set_text_prefix':
            assert ed.rep_prefix(op['prefix'], op['text'])
        elif kind == 'set_text_contains':
            assert ed.rep_contains(op['sub'], op['text'])
        elif kind == 'replace_range':
            ed.replace_range(op['start'], op['end'], op['items'])
        elif kind == 'insert_after_para':
            ps = ed.paras()
            i = ed.find_para(op['prefix'])
            ed.insert_after(ps[i], op['text'])
        elif kind == 'delete_contains':
            killed = ed.delete_contains(op['patterns'], start_prefix=op.get('start_prefix'))
            print('  delete_contains: 删除 %d 段' % killed)
        elif kind == 'strip_vmerge':
            ed.strip_vmerge(_resolve_table(ed, op['table']))
        elif kind == 'fill_table':
            tbl = _resolve_table(ed, op['table'])
            ed.fill_table(tbl, op['rows'], start_row=op.get('start_row', 1))
        elif kind == 'note_after_table':
            tbl = _resolve_table(ed, op['table'])
            ed.insert_note_after_table(tbl, op['text'])
        elif kind == 'replace_image':
            p = os.path.join(content_dir, op['path'])
            ed.replace_image_part(op['target'], p)
        elif kind == 'exec_python':
            spec = importlib.util.spec_from_file_location(
                'content_hook', os.path.join(content_dir, op['file']))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run(ed, ops)
        else:
            raise ValueError('未知 op：%r' % kind)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--template', required=True, help='上月月报 docx（格式模板）')
    ap.add_argument('--content', required=True, help='content 目录（含 meta.json）')
    ap.add_argument('--out', required=True, help='输出 docx 路径')
    ap.add_argument('--auto-fmt-narrative', dest='auto_fmt_narrative', action='store_true', default=None,
                    help='为 replace_range 中的「日期 X 月 Y 日」开头叙述类 item 自动加 b:False + rFonts 覆盖（默认开）')
    ap.add_argument('--no-auto-fmt-narrative', dest='auto_fmt_narrative', action='store_false', default=None,
                    help='关闭叙述类自动 fmt 覆盖')
    args = ap.parse_args()

    meta_path = os.path.join(args.content, 'meta.json')
    content = json.load(open(meta_path, encoding='utf-8'))
    ed = DocEditor(args.template)

    # auto_fmt_narrative 三级优先级：CLI flag > meta build_options.auto_fmt_narrative > 默认 True
    bo = content.get("build_options") or {}
    if args.auto_fmt_narrative is not None:
        auto = args.auto_fmt_narrative
    elif "auto_fmt_narrative" in bo:
        auto = bool(bo["auto_fmt_narrative"])
    else:
        auto = True
    content = annotate_narrative_fmt(content, ed, enable=auto)
    n_replaced = sum(1 for op in content.get("ops", []) if op.get("op") == "replace_range")
    print(f"apply_ops: {n_replaced} replace_range ops  | auto_fmt_narrative={auto}")

    for k, v in (content.get('cover') or {}).items():
        pass  # 封面由 set_text_prefix op 声明，保持引擎单一职责

    apply_ops(ed, content.get('ops') or [], args.content)
    ed.save(args.out)
    print('✅ 构建完成：%s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
