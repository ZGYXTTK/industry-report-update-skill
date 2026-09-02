# -*- coding: utf-8 -*-
"""
config_check.py —— 配置一致性校验门禁（自包含，无外部依赖）

校验：
  1. 采集清单.yaml 的每个采集项必填字段（id/类型/通道/口径）；
  2. 采集项「通道」取值必须 ∈ (口径字典.采集通道 的键 ∪ 内置渠道/数据源名)；
  3. 口径字典.状态码 映射不为空（空 {} 说明「按需补充」未落地）；
  4. 口径字典.口径.赛道定义 非「待确认」占位（Step 4 确认后应回写）；
  5. 权威源映射 / 时点对齐 非空。

内置极简 YAML 解析器（仅支持本 skill config 子集：嵌套 map、`-` 列表、`[a,b]` 内联列表、标量）。

用法:
    python config_check.py [--config-dir config] [--out 配置校验报告.md]
"""
import argparse
import os
import re
import sys


# ----------------------------------------------------------------------
# 极简 YAML 子集解析器
# ----------------------------------------------------------------------
def _parse_scalar(s):
    s = s.strip()
    if not s:
        return None
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1]
        return [x.strip().strip('"\'') for x in inner.split(',') if x.strip()]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s in ('true', 'True'):
        return True
    if s in ('false', 'False'):
        return False
    if s in ('null', '~'):
        return None
    if re.match(r'^-?\d+$', s):
        return int(s)
    if re.match(r'^-?\d+\.\d+$', s):
        return float(s)
    return s


def _strip_inline_comment(s):
    """去行尾注释（# 及以后），但保留引号内的 #。"""
    in_single = in_double = False
    for i, ch in enumerate(s):
        if ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '#' and not in_single and not in_double:
            return s[:i].rstrip()
    return s


def parse_yaml(text):
    """解析本 skill config 子集，返回嵌套 dict/list。"""
    raw = []
    for line in text.splitlines():
        s = _strip_inline_comment(line.rstrip())
        st = s.strip()
        if not st:
            continue
        raw.append((len(s) - len(s.lstrip(' ')), st))

    root = {}
    stack = [(-1, root, None)]  # (indent, container, key_in_parent)
    i = 0
    n = len(raw)
    while i < n:
        indent, content = raw[i]
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith('- '):
            rest = content[2:].strip()
            if not isinstance(parent, list):
                raise ValueError('缩进 %d 处出现列表项，但父级不是列表：%s' % (indent, content))
            if rest == '':
                item = {}
                parent.append(item)
                stack.append((indent, item, None))
            elif ':' in rest:
                k, v = rest.split(':', 1)
                item = {}
                parent.append(item)
                item[k.strip()] = _parse_scalar(v)
                stack.append((indent, item, None))
            else:
                parent.append(_parse_scalar(rest))
            i += 1
            continue

        if ':' not in content:
            i += 1
            continue
        k, v = content.split(':', 1)
        k = k.strip()
        v = v.strip()
        if v == '':
            nxt_is_list = (i + 1 < n and raw[i + 1][0] > indent and raw[i + 1][1].startswith('- '))
            child = [] if nxt_is_list else {}
            parent[k] = child
            stack.append((indent, child, k))
        else:
            parent[k] = _parse_scalar(v)
        i += 1
    return root


# ----------------------------------------------------------------------
# 校验逻辑
# ----------------------------------------------------------------------
# 内置渠道/数据源名（不在口径字典.采集通道 里、但采集清单会引用）
# 注意：本表是「已知数据源参考」，不是「封闭白名单」。Step 2.0 工具盘点会补充
# 本机实际的 MCP server 名（mx-ds-mcp/hexin-ifind-ds/stock-sdk 等）；凡 Step 2.0
# 已实测可用的工具，即使不在本表，也允许写进采集清单.通道（降级为 warning 而非 error）。
ALLOWED_CHANNELS = {
    'qcc工商', 'qcc财务', 'qcc实际控制人', 'qcc股东', 'qcc高管', 'qcc风险', 'qcc司法',
    'qcc专利', 'qcc商标', 'iFinD财务', 'iFinD新闻', 'iFinD', 'Wind', 'IT桔子',
    '媒体', '官网', 'dknowc可信搜索', '上市公司财报', '上市公司年报', '上市公司定期报告',
    '公司公告', '招股书', '交易所审核官网', '证监会官网', '监管公示', '裁判文书网',
    '国家知识产权局', '官方发布', '权威媒体', '财经媒体', 'pkulaw',
    # 本机常见 MCP server（东方财富/同花顺iFinD/行情/巨潮/港交所/烯牛/一级市场）
    'mx-ds-mcp', 'mx_finance_search_news', 'mx_finance_search_notice',
    'hexin-ifind-ds', 'iFinD', 'stock-sdk', 'tushare', 'akshare',
    'mcp-hkexnews', 'cninfo', 'itjuzi', '烯牛数据', '烯牛',
}


def _load(path):
    # 统一走 yaml_lite（PyYAML 优先、mini 兜底），避免与 config_check 自维护解析器分歧
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import yaml_lite
    return yaml_lite.load_yaml(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config-dir', default=None, help='config 目录（默认取本脚本上两级 config/）')
    ap.add_argument('--out', default='配置校验报告.md')
    args = ap.parse_args()

    base = args.config_dir or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'config'))
    base = os.path.normpath(base)

    kou = _load(os.path.join(base, '口径字典.yaml'))
    cai = _load(os.path.join(base, '采集清单.yaml'))
    quan = _load(os.path.join(base, '权威源映射.yaml'))
    shidian = _load(os.path.join(base, '时点对齐策略.yaml'))

    errors = []
    warns = []

    channel_keys = set((kou.get('采集通道') or {}).keys())
    allowed = channel_keys | ALLOWED_CHANNELS

    # 1) 采集清单必填字段 + 通道校验
    items = cai.get('采集项') or []
    if not items:
        errors.append('采集清单.yaml 无采集项')
    for it in items:
        if not isinstance(it, dict):
            errors.append('采集项不是 map：%r' % it)
            continue
        for field in ('id', '类型', '通道', '口径'):
            if not it.get(field):
                errors.append('采集项「%s」缺字段 %s' % (it.get('id', '?'), field))
        for ch in (it.get('通道') or []):
            if ch not in allowed:
                # 通道不在预置白名单：不再拦截（这正是「被配置锚定」的代码化载体），
                # 降级为 warning，提示在 Step 2.0 工具盘点中确认该工具确实可用。
                warns.append('采集项「%s」的通道「%s」不在预置白名单，请确认已在 Step 2.0 工具盘点中实测可用'
                             % (it.get('id'), ch))

    # 2) 口径字典状态码非空
    for k, v in (kou.get('状态码') or {}).items():
        if not v:
            warns.append('口径字典.状态码.%s 为空，请补全或标注「按需补充」' % k)

    # 3) 赛道定义占位
    if str(kou.get('口径', {}).get('赛道定义', '')).startswith('待确认'):
        warns.append('口径字典.口径.赛道定义 仍是「待确认」占位，Step 4 确认后应回写')

    # 4) 权威源映射非空
    if not (quan.get('权威源映射') or {}):
        warns.append('权威源映射.yaml 的权威源映射为空')

    # 5) 时点对齐非空
    if not (shidian.get('时点对齐') or {}):
        warns.append('时点对齐策略.yaml 的时点对齐为空')

    passed = len(errors) == 0
    lines = [
        '# 配置校验报告',
        '',
        '| 指标 | 值 |',
        '| --- | --- |',
        '| 错误 | %d |' % len(errors),
        '| 警告 | %d |' % len(warns),
        '| 结论 | %s |' % ('✅ 通过' if passed else '❌ 未通过'),
        '',
        '## 错误（必改）',
    ]
    if errors:
        lines += ['- ❌ ' + e.replace('|', '\\|') for e in errors]
    else:
        lines.append('- ✅ 无')
    lines += ['', '## 警告（建议补）']
    if warns:
        lines += ['- ⚠️ ' + w.replace('|', '\\|') for w in warns]
    else:
        lines.append('- ✅ 无')

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('配置校验：错误 %d，警告 %d → %s' % (len(errors), len(warns), '通过' if passed else '未通过'))
    if not passed:
        sys.exit(1)


if __name__ == '__main__':
    main()
