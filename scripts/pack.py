# -*- coding: utf-8 -*-
"""
pack.py —— 行业包管理（P2-9：通用引擎 + 可插拔行业包）

理念：SKILL 主流程是「通用引擎」，赛道定义/标的池/权威源/行业专属纪律
全部装进 packs/<行业名>/ 行业包；config/ 永远是「当前激活包」。
换行业 = activate 另一个包；新行业 = wizard 从一份旧月报反推生成初始包。

用法:
    python scripts/pack.py list
    python scripts/pack.py activate robotics          # 备份当前 config/ 后切换
    python scripts/pack.py wizard 旧月报.docx --name medtech   # 反推生成新包骨架
"""
import argparse
import datetime
import os
import re
import shutil
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CFG = os.path.join(SKILL_DIR, 'config')
PACKS = os.path.join(SKILL_DIR, 'packs')

PACK_FILES = ['口径字典.yaml', '采集清单.yaml', '权威源映射.yaml', '时点对齐策略.yaml', '标的池.yaml']
EXTRA_FILES = ['RULES.md']  # 行业专属纪律（P2 级）

# 判定「像公司名」的粗略规则（wizard 候选召回，入库仍需人工判断）
_COMPANY_HINTS = ('公司', '科技', '智能', '机器人', '股份', '集团', '实业', '技术', '生物', '医疗', '电气', '光电', '精密')
_SKIP_WORDS = ('序号', '简称', '名称', '合计', '总计', '来源', '备注', '分类', '板块', '状态', '日期', '金额')
# 业务键列表头（wizard 优先按表头定位公司列，而非盲目取首列）
_KEY_HEADERS = ('公司简称', '融资方', '公司名称', '标的公司名称', '企业名称', '证券简称', '股票简称')


def _key_col_index(table):
    """定位公司列：优先表头命中业务键名，否则回退首列。"""
    if not table.rows:
        return 0
    header = [(c.text or '').strip() for c in table.rows[0].cells]
    for name in _KEY_HEADERS:
        for ci, h in enumerate(header):
            if name in h:
                return ci
    return 0


def cmd_list():
    if not os.path.isdir(PACKS):
        print('（packs/ 目录不存在）')
        return 0
    names = [d for d in sorted(os.listdir(PACKS)) if os.path.isdir(os.path.join(PACKS, d)) and not d.startswith('_')]
    if not names:
        print('（尚无行业包）')
        return 0
    print('行业包列表（packs/）：')
    for n in names:
        files = [f for f in PACK_FILES + EXTRA_FILES if os.path.exists(os.path.join(PACKS, n, f))]
        print('  - %s（%d/%d 个核心文件）' % (n, len([f for f in files if f.endswith('.yaml')]), len(PACK_FILES)))
    return 0


def cmd_activate(args):
    src = os.path.join(PACKS, args.name)
    if not os.path.isdir(src):
        print('❌ 行业包不存在：%s（先 list 查看或 wizard 创建）' % src)
        return 2
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = os.path.join(CFG, '_backup', ts)
    os.makedirs(backup, exist_ok=True)
    moved = 0
    for f in PACK_FILES:
        cur = os.path.join(CFG, f)
        if os.path.exists(cur):
            shutil.copy2(cur, os.path.join(backup, f))
            moved += 1
    copied = 0
    for f in PACK_FILES + EXTRA_FILES:
        s = os.path.join(src, f)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(CFG, f))
            copied += 1
    print('✅ 已激活行业包 %s：备份 %d 个旧配置到 %s，拷贝 %d 个文件到 config/' % (args.name, moved, backup, copied))
    print('   下一步：跑 scripts/snapshot.py snapshot --ym <YYYY-MM> 落盘新口径快照')
    return 0


def cmd_wizard(args):
    from docx import Document
    if not os.path.exists(args.docx):
        print('❌ 找不到 %s' % args.docx)
        return 2
    dst = os.path.join(PACKS, args.name)
    if os.path.exists(dst):
        print('❌ 包已存在：%s（换个名字或先人工删除）' % dst)
        return 2
    os.makedirs(dst)

    # 1) 从旧月报表格首列召回候选公司名
    doc = Document(args.docx)
    candidates = {}
    for t in doc.tables:
        if not t.rows:
            continue
        kc = _key_col_index(t)
        for r in t.rows[1:]:
            if not r.cells or kc >= len(r.cells):
                continue
            text = r.cells[kc].text.strip()
            if (2 <= len(text) <= 12
                    and any(h in text for h in _COMPANY_HINTS)
                    and not any(s in text for s in _SKIP_WORDS)
                    and re.match(r'^[\u4e00-\u9fffA-Za-z0-9（）()]+$', text)):
                candidates[text] = candidates.get(text, 0) + 1
    names = sorted(candidates, key=lambda k: -candidates[k])

    # 2) 生成骨架（全部 TODO 标注，强制人工确认后才可用）
    today = datetime.date.today().isoformat()
    pool_lines = [
        '# 标的池（pack.py wizard 由 %s 反推生成 · %s）' % (os.path.basename(args.docx), today),
        '# ⚠️ 以下为「候选召回」，逐家人工判断是否属于本赛道后再启用！',
        '版本: "0.1-wizard"',
        '最后更新: "%s"' % today,
        '',
        '候选标的:',
    ]
    for n in names[:100]:
        pool_lines.append('  - 公司: %s' % n)
        pool_lines.append('    分类: TODO')
        pool_lines.append('    是否上市: TODO')
        pool_lines.append('    板块: TODO')
        pool_lines.append('    法人: TODO')
    if not names:
        pool_lines.append('  - 公司: TODO（未从表格首列召回到候选，请人工补充）')
    _w(dst, '标的池.yaml', '\n'.join(pool_lines))

    _w(dst, '口径字典.yaml', '\n'.join([
        '# 口径字典（wizard 骨架 · 待人工补全）',
        '版本: "0.1-wizard"',
        '赛道定义: "TODO：一句话定义本行业赛道边界（哪些公司算、哪些不算）"',
        '赛道分类: [TODO子赛道1, TODO子赛道2]',
        '状态码映射:',
        '  在审: "TODO：哪些审核状态计入在审"',
        '采集通道:',
        '  TODO字段: [TODO权威源, TODO兜底源]',
    ]))
    _w(dst, '采集清单.yaml', '\n'.join([
        '# 采集清单（wizard 骨架 · 通用项已预填，行业特有项标 TODO；每月只改截至日期）',
        '截至日期: "YYYY-MM-DD"',
        '采集日: "YYYY-MM-DD"',
        '# 通道别名：采集通道名 → 通道实测.jsonl 键名片段（channel_pick.py 匹配用，按行业补全）',
        '通道别名: {}',
        '采集项:',
        '  - id: A股在审家数',
        '    类型: 时点型',
        '    通道: [上交所IPO, 深交所IPO, 北交所IPO, 证监会]',
        '    备选通道: [东财IPO审核列表, iFinD, 公告检索]',
        '    口径: 在审（剔除已上市/终止/中止），按赛道口径过滤',
        '    输出: "交易所官网-IPO在审-YYYYMM.csv"',
        '  - id: IPO发行企业',
        '    类型: 时点型',
        '    通道: [交易所新股, iFinD, mx-ds-mcp]',
        '    备选通道: [web_search]',
        '    口径: 本月新发行/新上市赛道企业（可能为0）',
        '    输出: "采集记录-IPO发行-YYYYMM.md"',
        '  - id: 辅导备案家数',
        '    类型: 时点型',
        '    通道: [证监会辅导备案]',
        '    备选通道: [iFinD]',
        '    口径: 本月新增辅导备案（赛道口径）',
        '    输出: "证监会官网-辅导备案-YYYYMM.csv"',
        '  - id: 再融资审核家数',
        '    类型: 时点型',
        '    通道: [上交所再融资, 深交所再融资]',
        '    备选通道: [公告检索]',
        '    口径: 再融资',
        '    输出: "交易所官网-再融资审核-YYYYMM.csv"',
        '  - id: 再融资预案',
        '    类型: 时点型',
        '    通道: [公告检索]',
        '    口径: 本月披露的再融资预案公告（可能为0）',
        '    输出: "采集记录-再融资预案-YYYYMM.md"',
        '  - id: 并购重组动态',
        '    类型: 时点型',
        '    通道: [公告检索, wind/iFinD公告]',
        '    备选通道: [交易所并购列表]',
        '    口径: A股上市公司赛道相关并购重组公告（最新披露日在本月）',
        '    输出: "采集记录-并购重组-YYYYMM.md"',
        '  - id: 二级市场指数',
        '    类型: 时点型',
        '    通道: [行情主源]',
        '    备选通道: [行情备源]',
        '    口径: "TODO：行业板块指数（申万二级等）月度涨跌幅/高低点/成交额"',
        '    输出: "指数月度数据-YYYYMM.csv"',
        '  - id: 个股涨跌幅前10',
        '    类型: 时点型',
        '    通道: [行情主源]',
        '    口径: "TODO：板块个股池（行业成分∪上月涨跌前20）月度区间涨跌幅"',
        '    输出: "个股月度涨跌幅-YYYYMM.csv"',
        '  - id: 全A行业轮动',
        '    类型: 时点型',
        '    通道: [行情主源]',
        '    口径: 申万一级行业月度涨跌幅完整枚举（上涨/下跌家数+领涨领跌）',
        '    输出: "申万一级行业月度涨跌-YYYYMM.csv"',
        '  - id: 市场估值',
        '    类型: 时点型',
        '    通道: [行情主源]',
        '    备选通道: [iFinD, tushare]',
        '    口径: 宽基指数与行业指数 PE-TTM + 近十年分位（口径注明）',
        '    输出: "指数估值-YYYYMM.csv"',
        '  - id: 一级市场融资',
        '    类型: 时点型',
        '    通道: [媒体多源检索]',
        '    备选通道: [IT桔子, 烯牛, QVeris]',
        '    口径: 非上市公司获投事件完整枚举，逐条双源交叉，公告披露口径',
        '    输出: "投融资产出-YYYYMM.md"',
        '  - id: 重要政策',
        '    类型: 时点型',
        '    通道: [官方发布, web_search]',
        '    口径: 影响本行业的国家级与地方政策，事件日期在本月',
        '    输出: "采集记录-重要政策-YYYYMM.md"',
        '  # TODO：行业特有采集项（如发射统计/热点事件细分/eVTOL动态等）',
    ]))
    _w(dst, '权威源映射.yaml', '\n'.join([
        '# 权威源映射（wizard 骨架 · 通用字段已预填，行业字段标 TODO）',
        '版本: "0.1-wizard"',
        '权威源映射:',
        '  IPO在审:       [交易所审核官网]',
        '  辅导备案:      [证监会官网]',
        '  再融资审核:    [交易所审核官网, 公司公告]',
        '  并购重组:      [上市公司公告, iFinD/Wind]',
        '  财务数据:      [上市公司财报/申报稿, iFinD, Wind]',
        '  行情:          [交易所, iFinD, Wind, 东方财富]',
        '  政策:          [官方发布, 可信搜索, 媒体]',
        '  一级市场融资:  [公司公告/招股书, 数据商（IT桔子/烯牛）, 媒体多源]',
        '  TODO行业字段:  [TODO首选源, TODO兜底源]',
        '通用降级:',
        '  - 官方一手源（交易所/证监会/公司公告/招股书/官方通报）',
        '  - 权威金融数据（Wind/iFinD/东方财富）',
        '  - 专业数据（企查查工商/数据商）',
        '  - 媒体报道/新闻（逐条双源交叉）',
        '降级链:',
        '  IPO在审: "交易所审核官网 → iFinD/数据商 → 公告检索 → 标注无法获取"',
        '  辅导备案: "证监会官网 → iFinD → 标注无法获取"',
        '  TODO行业字段: "首选 → 兜底 → 标注无法获取"',
    ]))
    _w(dst, '时点对齐策略.yaml', '\n'.join([
        '# 时点对齐策略（wizard 骨架）',
        '时点对齐:',
        '  行情类: "截至上月最后交易日"',
        '  审核类: "截至采集日"',
        '  财务类: "各公司最近披露财报期（源文件标期 + 正文表格脚注）"',
        '采集日期显式化: "月报首页脚注写明采集日与目标时点"',
    ]))
    _w(dst, 'RULES.md', '\n'.join([
        '# %s 行业包 · 行业专属纪律（P2 级）' % args.name,
        '',
        '> 本文件承接 SKILL.md 纪律分级中的 P2 层：只写本行业特有的硬性规则。',
        '> 通用纪律（禁止编造/重新采集/溯源/格式）在 SKILL.md，不要重复。',
        '',
        '## 通用硬性规则（预填，随期修订）',
        '- 一级市场/并购事件必须跨月去重（cross_month_dedup.py + 公告日核对：公告日≠转载日）。',
        '- 表格行数缩减后必须删残行；表格重填前 strip_vmerge（防合并伪影）。',
        '- 通道降级必须在正文注脚可见（不只写变更摘要）。',
        '- 「无法获取/未核实」标注必须真实（抽查源文件）。',
        '',
        '- TODO：本行业特有的时点规则（如港股 6 个月有效期之类的监管口径）',
        '- TODO：本行业特有的分类/事件类型口径（如发射统计三类口径、eVTOL 取证阶段口径等）',
        '- TODO：本行业预测数据的呈现要求（如卖方一致预期独立小表）',
    ]))
    print('✅ 新行业包骨架已生成：%s' % dst)
    print('   候选标的 %d 家（已写入 标的池.yaml，需人工逐家确认）' % len(names))
    print('   全部 YAML 带 TODO 标记——补全后执行 pack.py activate %s' % args.name)
    return 0


def _w(dst, name, content):
    with open(os.path.join(dst, name), 'w', encoding='utf-8') as f:
        f.write(content + '\n')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    sp = sub.add_parser('activate')
    sp.add_argument('name')
    sp2 = sub.add_parser('wizard')
    sp2.add_argument('docx')
    sp2.add_argument('--name', required=True)
    args = ap.parse_args()
    if args.action == 'list':
        return cmd_list()
    if args.action == 'activate':
        return cmd_activate(args)
    return cmd_wizard(args)


if __name__ == '__main__':
    sys.exit(main())
