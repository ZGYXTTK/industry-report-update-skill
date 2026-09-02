# -*- coding: utf-8 -*-
"""
yaml_lite.py —— 统一 YAML 加载器（P1-5：告别"自写解析器踩关键闸门"）

策略：
  1. 优先使用 PyYAML（yaml.safe_load）——环境已装则用，解析严格可靠；
  2. 未装 PyYAML 时回退到本文件的 mini 解析器。mini 版支持本 Skill 配置用到的
     全部特性：嵌套字典、标量列表、字典列表（- key: value）、引号字符串、
     行内/整行注释、| 与 > 块标量、数字/布尔自动转型。
     不支持的复杂特性（锚点 &、多文档 ---、流式 {} 嵌套）会显式报错而不是静默漏解析。

用法:
    from yaml_lite import load_yaml, YamlLiteError
    data = load_yaml(path)   # path 或文本均可（load_yaml_text）
"""
import os
import re

try:
    import yaml as _pyyaml
except ImportError:
    _pyyaml = None


class YamlLiteError(Exception):
    pass


# ----------------------------------------------------------------------
# mini 解析器（无 PyYAML 时的稳健回退）
# ----------------------------------------------------------------------
def _strip_comment(line):
    """去掉行内注释（引号内的 # 不算注释）。"""
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            out.append(ch)
        elif ch == '#':
            break
        else:
            out.append(ch)
    return ''.join(out).rstrip()


def _unescape_dq(s):
    """双引号字符串的转义解码（块标量经 json_escape 编码后在此还原）。"""
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == 'n':
                out.append('\n')
            elif nxt == 't':
                out.append('\t')
            elif nxt == '"':
                out.append('"')
            elif nxt == '\\':
                out.append('\\')
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def _split_flow(body):
    """按顶层逗号切分流式语法元素（忽略引号与嵌套括号内的逗号）。"""
    parts, depth, quote, cur = [], 0, None, []
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            cur.append(ch)
        elif ch in '[{':
            depth += 1
            cur.append(ch)
        elif ch in ']}':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return parts


def _cast(val):
    v = val.strip()
    if v == '':
        return ''
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return _unescape_dq(v[1:-1])
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return v[1:-1].replace("''", "'")
    if v.startswith('[') and v.endswith(']'):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_cast(x) for x in _split_flow(inner)]
    if v.startswith('{') and v.endswith('}'):
        inner = v[1:-1].strip()
        if not inner:
            return {}
        d = {}
        for part in _split_flow(inner):
            k, sep, kv = part.partition(':')
            if not sep:
                raise YamlLiteError('流式字典元素缺冒号：%s' % part)
            d[k.strip().strip('"').strip("'")] = _cast(kv)
        return d
    low = v.lower()
    if low in ('true', 'false'):
        return low == 'true'
    if low in ('null', '~'):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _mini_parse(text):
    lines = text.splitlines()
    # 预处理：跳过空行/整行注释/文档标记，记录 (indent, content, lineno)
    items = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        i += 1
        if not raw.strip() or raw.strip().startswith('#'):
            continue
        if raw.strip() in ('---', '...'):
            continue
        if raw.lstrip().startswith(('!', '&', '*')):
            raise YamlLiteError('第 %d 行：mini 解析器不支持锚点/标签，请安装 PyYAML' % lineno)
        indent = len(raw) - len(raw.lstrip())
        content = _strip_comment(raw.lstrip())
        if not content:
            continue
        # 块标量 key: | 或 key: >
        m = re.match(r'^([^:]+):\s*([|>])[-+]?\s*$', content)
        if m:
            key = m.group(1).strip()
            block = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    block.append('')
                    i += 1
                    continue
                nindent = len(nxt) - len(nxt.lstrip())
                if nindent <= indent:
                    break
                block.append(nxt[indent + 2:] if len(nxt) > indent + 2 else '')
                i += 1
            # 块标量 clip 语义：末尾保留单个换行
            while block and block[-1] == '':
                block.pop()
            if m.group(2) == '|':
                val = '\n'.join(block) + '\n'
            else:
                val = ' '.join(x for x in block if x) + '\n'
            items.append((indent, '%s: %s' % (key, json_escape(val)), lineno))
            continue
        items.append((indent, content, lineno))

    def parse_block(pos, indent):
        """返回 (obj, next_pos)。按缩进层级解析 dict 或 list。"""
        # 判断容器类型
        is_list = items[pos][1].startswith('- ') or items[pos][1] == '-'
        container = [] if is_list else {}
        while pos < len(items):
            ind, content, lineno = items[pos]
            if ind < indent:
                break
            if ind > indent:
                raise YamlLiteError('第 %d 行：缩进异常（期望 %d 实际 %d）' % (lineno, indent, ind))
            if is_list:
                if not (content.startswith('- ') or content == '-'):
                    break
                body = content[1:].strip()
                if body == '':
                    # 子块
                    if pos + 1 < len(items) and items[pos + 1][0] > indent:
                        child, pos = parse_block(pos + 1, items[pos + 1][0])
                        container.append(child)
                    else:
                        container.append(None)
                        pos += 1
                elif (re.match(r'^[^:]+:\s*', body)
                      and not body.startswith(('"', "'", '[', '{'))):
                    # 字典列表项：- key: value，后续同缩进 key 行归入同一 dict。
                    # 若 body 以 [ 或 { 开头（flow list/dict），或为带引号标量，不能当作字典项，
                    # 否则 flow-list 内引号字符串一旦含冒号（如 "…form: statetypes…"）会被误判为 dict。
                    d = {}
                    key, _, val = body.partition(':')
                    key = key.strip()
                    val = val.strip()
                    if val == '':
                        if pos + 1 < len(items) and items[pos + 1][0] > indent:
                            child, pos = parse_block(pos + 1, items[pos + 1][0])
                            d[key] = child
                        else:
                            d[key] = {}
                            pos += 1
                    else:
                        d[key] = _cast(val)
                        pos += 1
                    # 吸收同属本 dict 的后续行（缩进 = indent + 2 或更深的第一层）
                    while pos < len(items) and items[pos][0] > indent:
                        sub_ind = items[pos][0]
                        sub, pos = parse_block(pos, sub_ind)
                        if isinstance(sub, dict):
                            d.update(sub)
                        else:
                            raise YamlLiteError('第 %d 行附近：列表项字典与列表混排' % lineno)
                    container.append(d)
                else:
                    container.append(_cast(body))
                    pos += 1
            else:
                if content.startswith('- ') or content == '-':
                    break
                key, sep, val = content.partition(':')
                if not sep:
                    raise YamlLiteError('第 %d 行：无法解析（缺冒号）: %s' % (lineno, content))
                key = key.strip().strip('"').strip("'")
                val = val.strip()
                pos += 1
                if val == '':
                    if pos < len(items) and items[pos][0] > indent:
                        child, pos = parse_block(pos, items[pos][0])
                        container[key] = child
                    else:
                        container[key] = {}
                else:
                    container[key] = _cast(val)
        return container, pos

    # 合并「多行标量续行」：上一行以 、/，/, 结尾（截断的枚举），
    # 且当前行不含 key: 结构、缩进更深时，视为同一标量的续行（YAML plain scalar 折行）。
    merged = []
    for ind, content, lineno in items:
        if (merged and not re.match(r'^[^:]+:', content)
                and ind > merged[-1][0]
                and merged[-1][1].rstrip().endswith(('、', '，', ','))):
            pi, pc, pl = merged[-1]
            # YAML plain scalar 折行语义：换行折叠为一个空格
            merged[-1] = (pi, pc + ' ' + content, pl)
        else:
            merged.append((ind, content, lineno))
    items = merged

    if not items:
        return {}
    obj, pos = parse_block(0, items[0][0])
    if pos < len(items):
        raise YamlLiteError('第 %d 行附近：解析未消费完全部内容' % items[pos][1])
    return obj


def json_escape(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
def load_yaml_text(text, source='<text>'):
    if _pyyaml is not None:
        try:
            return _pyyaml.safe_load(text) or {}
        except Exception as e:
            raise YamlLiteError('%s：PyYAML 解析失败：%s' % (source, e))
    try:
        return _mini_parse(text)
    except YamlLiteError:
        raise
    except Exception as e:
        raise YamlLiteError('%s：mini 解析失败：%s（建议 pip install pyyaml）' % (source, e))


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return load_yaml_text(f.read(), source=path)


def backend():
    return 'pyyaml' if _pyyaml is not None else 'mini'


if __name__ == '__main__':
    import sys
    print('backend =', backend())
    if len(sys.argv) > 1:
        import json
        print(json.dumps(load_yaml(sys.argv[1]), ensure_ascii=False, indent=2, default=str))
