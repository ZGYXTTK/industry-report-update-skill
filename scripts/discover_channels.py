# -*- coding: utf-8 -*-
"""
discover_channels.py —— 通道三层自动发现（Step 2 硬性前置 · 2026-09 新增）

根因背景（2026-09 实测）：Agent 曾三连误判金融数据工具「不可用」（iFinD/Wind/qcc），
只因它们不在 function list 里。实际上本机金融数据 MCP 存在三种形态：
  ① function list 里的 mcp__* 工具 —— Agent 直连（本脚本读不到，由 Agent 回填）
  ② skill 目录下的本地脚本通道（call-node.js / cli.mjs / call.py —— iFinD/Wind 靠这个）
  ③ harness 层 MCP 连接（storages/mcp_connector.json → tables.connections —— qcc 靠这个）

本脚本穷尽 ②③ 两层，外加 ④ config/endpoints.yaml 的 http/mcp 端点，输出合并清单，
供 Step 2 直接覆盖，杜绝「只看 function list 就判不可用」。

纪律：本脚本只「发现 + 报告」通道的存在与元信息，不做真取数（真取数由 Step 2 的
smoke test 完成）。发现的通道一律不带 ✅/❌ 结论——结论必须经实测后由 Agent 填。

用法：
  python scripts/discover_channels.py [--out runs/<run-id>/sources/通道发现.jsonl]
                                      [--harness <harness根目录>] [--skills-dir <额外skill目录>]
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)

# 敏感 query 参数名（URL 里可能夹带 api_key/token 等，必须脱敏，不得回显/落盘）
_SENSITIVE_QUERY_KEY = re.compile(
    r'(api[_-]?key|token|secret|password|passwd|auth|credential|signature|access[_-]?key)',
    re.IGNORECASE,
)


def _redact_url(url):
    """对 URL query 中疑似凭证的参数值脱敏（只显示 key=***）。"""
    if not url:
        return url
    if '?' not in url:
        return url
    base, _, qs = url.partition('?')
    parts = []
    for kv in qs.split('&'):
        k = kv.split('=', 1)[0]
        if _SENSITIVE_QUERY_KEY.search(k):
            parts.append(k + '=***')
        else:
            parts.append(kv)
    return base + '?' + '&'.join(parts)


_SENSITIVE_FLAG = re.compile(
    r'^--?(api[_-]?key|token|secret|password|passwd|auth|credential|signature|access[_-]?key)$',
    re.IGNORECASE,
)


def _redact_command(command):
    """对 command 中 KEY=value / --flag value 的疑似凭证值脱敏（防御性；当前 command 均干净）。"""
    if not command:
        return command
    toks = command.split()
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if '=' in t:
            k, _, _v = t.partition('=')
            if _SENSITIVE_QUERY_KEY.search(k):
                out.append(k + '=***')
            else:
                out.append(t)
        elif _SENSITIVE_FLAG.match(t):
            out.append(t)
            if i + 1 < len(toks):
                out.append('***')
                i += 1
        else:
            out.append(t)
        i += 1
    return ' '.join(out)


_SECRET_KEYS = ('bearerToken', 'accessToken', 'token', 'apiKey', 'apiKeyValue', 'grantKey')
_SECRET_HEADER_KEYS = ('authorization', 'x-api-key', 'api-key', 'em_api_key')


def _has_secret(d):
    """判断一个 dict 是否含凭证（只看键名，绝不回显值）。"""
    return any(k in d for k in _SECRET_KEYS)


# 本地脚本通道的标记文件（skill 目录下出现这些，即视为「封装了外部 MCP/数据服务的本地脚本通道」）
LOCAL_SCRIPT_MARKERS = (
    'call-node.js', 'call.py', 'call-http.py', 'cli.mjs', 'mcp_config.json',
)


def _candidate_harness_dirs(explicit=None):
    """返回候选 harness 根目录（含 storages/mcp_connector.json 的父级父级）。"""
    cands = []
    if explicit:
        cands.append(explicit)
    cands.append(os.environ.get('DSH_HOME'))
    apd = os.environ.get('APPDATA')
    if apd:
        cands.append(os.path.join(apd, 'dsh-desktop', 'harness'))
    cands.append(os.path.join(os.path.expanduser('~'), '.dsh'))
    cands.append(os.path.join(os.path.expanduser('~'), '.config', 'dsh-desktop', 'harness'))
    seen = []
    for c in cands:
        if not c:
            continue
        c = os.path.abspath(os.path.expanduser(c))
        if c in seen:
            continue
        seen.append(c)
    return seen


def _locate_mcp_connector(harness_dirs):
    """在候选 harness 目录里找 storages/mcp_connector.json。"""
    for h in harness_dirs:
        p = os.path.join(h, 'storages', 'mcp_connector.json')
        if os.path.isfile(p):
            return p
    return None


def discover_harness_connections(mcp_connector_path):
    """读 mcp_connector.json 的 tables.connections，返回 harness 层连接清单。"""
    rows = []
    try:
        with open(mcp_connector_path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        rows.append({'layer': 'harness-connection', 'name': '(读取失败)', 'status': 'error',
                     'error': 'mcp_connector.json 解析失败: %s' % e})
        return rows, None
    conns = {}
    try:
        conns = data.get('tables', {}).get('connections', {}) or {}
    except AttributeError:
        pass
    for key, c in conns.items():
        if not isinstance(c, dict):
            continue
        auth = c.get('auth') or {}
        headers = c.get('headers') or {}
        # 凭证存在性：auth 的凭证键 + headers 的凭证键（只判键名，绝不回显值）
        has_token = _has_secret(auth) or any(
            str(k).lower() in _SECRET_HEADER_KEYS for k in headers)
        rows.append({
            'layer': 'harness-connection',
            'key': key,
            'name': c.get('name') or key,
            'transport': c.get('transport'),
            'url': _redact_url(c.get('url')),
            'command': _redact_command(c.get('command')),
            'enabled': c.get('enabled'),
            'auth_mode': auth.get('mode'),
            'has_token': has_token,
        })
    return rows, conns


def _candidate_skill_dirs(harness_dirs, extra=None):
    """返回候选 skill 目录。"""
    dirs = []
    for h in harness_dirs:
        dirs.append(os.path.join(h, 'skills'))
    dirs.append(os.path.join(os.path.expanduser('~'), '.agents', 'skills'))
    if extra:
        dirs.extend(extra)
    out = []
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(d))
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def discover_skill_local_scripts(skill_dirs):
    """扫描 skill 目录，找出封装了外部 MCP/数据服务的本地脚本通道。"""
    rows = []
    seen = set()  # 去重：同一 skill 可能出现在多个 skill 目录
    for sd in skill_dirs:
        try:
            names = os.listdir(sd)
        except OSError as e:
            rows.append({'layer': 'skill-local-script', 'name': sd, 'status': 'error',
                         'error': 'listdir 失败: %s' % e})
            continue
        for nm in names:
            if nm in seen:
                continue
            sp = os.path.join(sd, nm)
            if not os.path.isdir(sp):
                continue
            markers = []
            walk_errs = []

            def _onerror(err):
                walk_errs.append(str(err))

            for root, _dirs, files in os.walk(sp, onerror=_onerror):
                for fn in files:
                    if fn in LOCAL_SCRIPT_MARKERS or fn.startswith('call-'):
                        markers.append(os.path.relpath(os.path.join(root, fn), sp))
                # 不深挖 node_modules/__pycache__
                if '__pycache__' in _dirs:
                    _dirs.remove('__pycache__')
                if 'node_modules' in _dirs:
                    _dirs.remove('node_modules')
            if walk_errs:
                rows.append({'layer': 'skill-local-script', 'name': nm, 'status': 'error',
                             'error': '遍历部分失败: %s' % '; '.join(walk_errs[:3])})
            if markers:
                seen.add(nm)
                rows.append({
                    'layer': 'skill-local-script',
                    'name': nm,
                    'dir': sp,
                    'markers': sorted(set(markers)),
                })
    return rows


def discover_endpoints():
    """读 config/endpoints.yaml 的 http/mcp/agent 通道。"""
    sys.path.insert(0, HERE)
    from yaml_lite import load_yaml
    rows = []
    ep_path = os.path.join(SKILL_DIR, 'config', 'endpoints.yaml')
    if not os.path.isfile(ep_path):
        rows.append({'layer': 'endpoint', 'name': '(endpoints.yaml 缺失)', 'status': 'error', 'error': ep_path})
        return rows
    try:
        ep = load_yaml(ep_path)
    except Exception as e:
        rows.append({'layer': 'endpoint', 'name': '(endpoints.yaml 解析失败)', 'status': 'error', 'error': str(e)})
        return rows
    for section, label in (('http通道', 'http-endpoint'), ('mcp通道', 'mcp-endpoint'),
                           ('agent通道', 'agent-endpoint')):
        for item in ep.get(section) or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                'layer': label,
                'name': item.get('name'),
                'url': _redact_url(item.get('url')),
                'method': item.get('method'),
                'smoke_hint': item.get('smoke_hint'),
                'note': item.get('note'),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None, help='输出 JSONL 路径（如 runs/<run-id>/sources/通道发现.jsonl）')
    ap.add_argument('--harness', default=None, help='harness 根目录（含 storages/ 的目录）')
    ap.add_argument('--skills-dir', action='append', default=None, help='额外 skill 目录（可多次）')
    args = ap.parse_args()

    harness_dirs = _candidate_harness_dirs(args.harness)
    mcp_connector = _locate_mcp_connector(harness_dirs)
    skill_dirs = _candidate_skill_dirs(harness_dirs, args.skills_dir)

    # ② harness 层连接
    harness_rows = []
    if mcp_connector:
        harness_rows, _ = discover_harness_connections(mcp_connector)
    else:
        harness_rows.append({'layer': 'harness-connection', 'name': '(未找到 mcp_connector.json)',
                             'status': 'error', 'error': '未找到 mcp_connector.json',
                             'searched': harness_dirs})

    # ③ skill 本地脚本通道
    skill_rows = discover_skill_local_scripts(skill_dirs)

    # ④ endpoints.yaml
    endpoint_rows = discover_endpoints()

    all_rows = harness_rows + skill_rows + endpoint_rows

    # 人类可读摘要
    print('=== 通道发现（discover_channels.py）===')
    print('harness 候选目录: %s' % harness_dirs)
    print('mcp_connector.json: %s' % (mcp_connector or '未找到'))
    print('skill 目录: %s' % skill_dirs)
    print()
    print('harness 层连接: %d' % sum(1 for r in harness_rows
                                     if r.get('layer') == 'harness-connection' and not r.get('error')))
    print('skill 本地脚本通道: %d' % sum(1 for r in skill_rows if not r.get('error')))
    print('endpoints 端点: %d' % sum(1 for r in endpoint_rows if not r.get('error')))
    print()
    for r in all_rows:
        if r.get('error') or r.get('status') == 'error':
            print('  [error] %s: %s' % (r.get('name'), r.get('error') or ''))
        elif r.get('layer') == 'harness-connection':
            flag = 'enabled' if r.get('enabled') else 'disabled'
            tok = 'token' if r.get('has_token') else 'no-token'
            print('  [%s] %s (%s, %s, %s) url=%s' % (flag, r.get('name'), r.get('transport'),
                                                    r.get('auth_mode'), tok, r.get('url') or r.get('command') or ''))
        elif r.get('layer') == 'skill-local-script':
            print('  [skill] %s -> %s' % (r.get('name'), ', '.join(r.get('markers') or [])))
        elif r.get('layer') in ('http-endpoint', 'mcp-endpoint', 'agent-endpoint'):
            print('  [%s] %s url=%s' % (r.get('layer'), r.get('name'), r.get('url') or ''))
    print()
    print('提示：本清单只「发现」通道存在性，不带可用性结论。真取数 smoke test 由 Step 2 完成，')
    print('      未实测通道只能标 🟡；标 ❌ 必须附实测失败证据。')

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            for r in all_rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print('\nJSONL 已写出: %s' % args.out)


if __name__ == '__main__':
    main()
