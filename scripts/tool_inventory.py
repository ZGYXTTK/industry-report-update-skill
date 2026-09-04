# -*- coding: utf-8 -*-
"""
tool_inventory.py —— Step 2 工具盘点的机器校验器（v2.1 新增）

作用：把「盘点本机全部信息源」从 Agent 的模糊自然语言动作，变成可机检的清单校验。
输入：Agent 实际执行 tools/list + smoke test 后写出的《工具清单.jsonl》。
输出：通过/警告/阻断 + 缺失项清单。

工具清单.jsonl 每行：
  {"source":"QVeris","kind":"registry","present":true,"smoke":"ok|degraded|fail|none",
   "discovered":true,"found_tools":["..."],"note":"..."}

校验规则（对应 config/tool_registry.yaml 规则）：
  1. 注册表内每个信息源都必须出现在清单里（present 标注存在/未装）。
  2. kind=registry 的源，若 present 必须 discovered=true（探查过，并记录 found_tools）。
  3. 任何 smoke=none 的源标记不得视为可用（映射表里应按 🟡 处理）。
  4. 清单里出现「注册表未列」的源 = 本机有但注册表漏（提示补注册表，不应判定为错误）。
用法：
  python scripts/tool_inventory.py --inventory runs/<run-id>/sources/工具清单.jsonl [--registry config/tool_registry.yaml] [--out 工具清单校验报告.md]
"""
import argparse
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)

# harness 层连接名 → 工具清单/tool_registry 的 source 名（机检覆盖校验的别名映射）
# 只登记「金融数据相关」连接；无关连接（Chrome DevTools/GitHub/Playwright 等）不要求覆盖。
# 新增金融数据 harness 连接时在此补一行。
_CONNECTION_ALIAS = {
    'qcc-company': '企查查(qcc)',
    'qcc-risk': '企查查(qcc)',
    'qcc-ipr': '企查查(qcc)',
    'qcc-operation': '企查查(qcc)',
    'qcc-history': '企查查(qcc)',
    'qcc-executive': '企查查(qcc)',
    'qcc-legal-regulation': '企查查(qcc)',
    'qcc-legal-case': '企查查(qcc)',
    'qcc-tender': 'qcc-tender',
    'qcc-document': 'qcc-document',
    'qcc-document-mcp': 'qcc-document',
    'hexin-ifind-ds-stock-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-fund-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-edb-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-news-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-bond-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-global-stock-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-index-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'hexin-ifind-ds-futures-mcp': 'hexin-ifind-ds (同花顺iFinD)',
    'itjuzi-mcp': 'itjuzi (IT桔子)',
    '烯牛MCP': '烯牛 mcp',
    'mx-ds-mcp': 'mx-ds-mcp (东方财富)',
    'QVerisMCP': 'QVeris',
    'Wind·股票数据': 'wind_stock_data',
    'cninfo': '上交所/深交所/北交所/证监会/港交所披露易/巨潮',
    'mcp-hkexnews': '上交所/深交所/北交所/证监会/港交所披露易/巨潮',
    'tushare': 'tushare',
    'AKShare': 'akshare',
    'Stock SDK 股票分析': 'stock-sdk',
    'Tavily': '搜索',
}


def _alias_lookup(name):
    """按名（大小写不敏感）查 _CONNECTION_ALIAS，返回映射到的 source 名或 None。"""
    if not name:
        return None
    low = name.lower()
    for k, v in _CONNECTION_ALIAS.items():
        if k.lower() == low:
            return v
    return None


def _load_discovered(path):
    """读 通道发现.jsonl（discover_channels.py 产出，每行一个 JSON 对象）。返回 (rows, err)。"""
    rows = []
    try:
        with open(path, encoding='utf-8') as f:
            txt = f.read()
    except OSError as e:
        return None, '通道发现文件读取失败: %s' % e
    txt = txt.lstrip('\ufeff').replace('\r\n', '\n')
    for ln in txt.split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            rows.append({'_parse_fail': True})
    return rows, None


def _load_yaml_lite(path):
    """统一用 yaml_lite 加载（PyYAML 优先、mini 兜底）；解析失败显式退出，勿静默返回 {} 致门禁假通过。"""
    try:
        sys.path.insert(0, HERE)
        import yaml_lite
        return yaml_lite.load_yaml(path)
    except Exception as e:
        raise SystemExit('❌ 配置文件解析失败（%s）：%s' % (path, e))


def _load_inv(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    # 去掉可能的 BOM 与 CR
    txt = txt.lstrip('\ufeff').replace('\r\n', '\n')
    for ln in txt.split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            rows.append({'raw': ln, '_parse_fail': True})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inventory', required=True)
    ap.add_argument('--registry', default=os.path.join(BASE, 'config', 'tool_registry.yaml'))
    ap.add_argument('--discovered', default=None,
                    help='通道发现.jsonl 路径（discover_channels.py 产出），提供时校验 harness 连接覆盖 + ❌证据门槛')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    inv = _load_inv(a.inventory)
    inv_by_source = {r.get('source'): r for r in inv if r.get('source')}

    registry = _load_yaml_lite(a.registry)
    sources = registry.get('信息源', []) if isinstance(registry.get('信息源'), list) else []

    problems = []      # 阻断级（必须补）
    warnings = []      # 警告级
    uncovered = []     # 本机有、注册表未列（提示补注册表）

    # ① 注册表内源是否都在清单内
    for s in sources:
        name = s.get('name') if isinstance(s, dict) else str(s)
        kind = (s.get('kind') if isinstance(s, dict) else '') or 'api'
        rec = inv_by_source.get(name)
        if rec is None:
            problems.append('注册表源「%s」未在清单中盘点（present 缺失）' % name)
            continue
        present = rec.get('present', True)
        if present is False:
            warnings.append('注册表源「%s」标记为未安装' % name)
            continue
        smoke = rec.get('smoke', 'none')
        if kind == 'registry' and not rec.get('discovered'):
            problems.append('聚合/仓库源「%s」未探查（discover 缺失，须 discover 一次并记录 found_tools）' % name)
        elif kind == 'registry' and rec.get('discovered') and not rec.get('found_tools'):
            warnings.append('聚合/仓库源「%s」discovered=true 但未记录 found_tools' % name)
        if smoke == 'none':
            warnings.append('源「%s」未 smoke test（按 🟡 处理，不得标 ✅）' % name)

    # ② 清单中注册表未列的源（本机有、注册表漏 → 提示）
    listed = {s.get('name') if isinstance(s, dict) else str(s) for s in sources}
    for name in inv_by_source:
        if name not in listed:
            uncovered.append(name)

    # ③ 清单解析失败行
    parse_fail = [r for r in inv if r.get('_parse_fail')]
    if parse_fail:
        problems.append('清单 %d 行 JSON 解析失败（编码/格式问题，需重写为 UTF-8）' % len(parse_fail))

    # ④ harness 层连接覆盖校验（--discovered 提供时）：金融数据连接必须被盘点
    disc_conn_count = 0
    if a.discovered:
        disc_rows, disc_err = _load_discovered(a.discovered)
        if disc_err:
            problems.append(disc_err)
        elif disc_rows:
            conns = [r for r in disc_rows
                     if r.get('layer') == 'harness-connection'
                     and r.get('enabled') and not r.get('error') and not r.get('_parse_fail')]
            disc_conn_count = len(conns)
            for c in conns:
                src = _alias_lookup(c.get('name')) or _alias_lookup(c.get('key'))
                if src is None:
                    continue  # 无关连接（Chrome DevTools/GitHub 等），不要求覆盖
                rec = inv_by_source.get(src)
                if rec is None:
                    problems.append('发现的 harness 连接「%s」未在清单中盘点（应映射到源「%s」）' % (c.get('name'), src))
                elif rec.get('present') is False:
                    problems.append('发现的 harness 连接「%s」在清单标记 present=false，但 harness 层 enabled=true（需实测确认）' % c.get('name'))

    # ⑤ ❌ 证据门槛：smoke=fail 必须附实测失败证据（未探测不得标 ❌）
    for src, rec in inv_by_source.items():
        if rec.get('smoke') == 'fail' and not rec.get('evidence'):
            problems.append('源「%s」smoke=fail 但缺 evidence 字段（需附实测探测命令+原始返回）' % src)

    ok = not problems
    lines = ['# 工具清单校验报告（tool_inventory.py）', '',
             '| 指标 | 值 |', '| --- | --- |',
             '| 清单源数 | %d |' % len(inv),
             '| 注册表源数 | %d |' % len(sources),
             '| 阻断 | %d |' % len(problems),
             '| 警告 | %d |' % len(warnings),
             '| 本机有/注册表未列 | %d |' % len(uncovered),
             '| 结论 | %s |' % ('✅ 通过' if ok else '❌ 未通过'), '']
    if problems:
        lines.append('## 阻断（必补）')
        for p in problems:
            lines.append('- ❌ ' + p)
    if warnings:
        lines.append('## 警告')
        for w in warnings:
            lines.append('- ⚠️ ' + w)
    if uncovered:
        lines.append('## 本机有 / 注册表未列（提示补 tool_registry.yaml）')
        for u in uncovered:
            lines.append('- 💡 ' + str(u))

    report = '\n'.join(lines)
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(report)
        print(report)
        print('\n报告已写出：%s' % a.out)
    else:
        print(report)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
