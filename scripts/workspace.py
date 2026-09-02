# -*- coding: utf-8 -*-
"""
workspace.py —— 解析「Skill 使用者当前对话工作区」路径（open-source 可移植版）。

本模块解决：Skill 的脚本默认把产物写进 skill 基目录（AppData 缓存），
但要求所有产出出现在「使用者的当前对话工作区」。

★ 可移植性原则：不依赖任何特定运行环境的专属信号。工作区识别优先级：
  1. 显式 --ws 参数（agent 传入，最可靠，任何环境通用）
  2. --anchor / 输入旧月报所在目录（从 agent 已加载的输入文件目录反推，任何环境通用）
  3. 环境变量 DSH_WORKSPACE（若宿主注入则用）
  4. 从 DSH_SESSION_JSONL 解码（仅 DeepSeek Harness 生效，作兜底）
  5. 当前工作目录 os.getcwd()

用法：
  from workspace import detect_workspace
  detect_workspace()                      # 综合探测
  detect_workspace('D:\\\\xxx')            # 显式传入工作区
  detect_workspace(anchor=r'D:\\proj\\旧月报.docx')  # 用输入文件目录反推
"""
import os
import re

_ENC_SEP = re.compile(r'(?<!\\)-(?!:)')
_ENC_DRIVE = re.compile(r'^([A-Za-z])\\')


def _decode_session_seg():
    """从 DSH_SESSION_JSONL 还原工作区路径（Harness 专属，非空返回 str 否则 None）。"""
    sj = os.environ.get('DSH_SESSION_JSONL')
    if not sj:
        return None
    try:
        seg = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(sj))))
    except Exception:
        return None
    seg = seg.strip('-')
    s = re.sub(r'~([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), seg)
    s = _ENC_SEP.sub('\\\\', s)
    s = _ENC_DRIVE.sub(r'\1:\\', s)
    return s


def detect_workspace(explicit=None, anchor=None):
    """
    返回工作区路径；无法确定时返回 None。

    explicit: 显式工作区路径（--ws）
    anchor:   一个位于工作区内的文件/目录（如输入旧月报原始路径）；取其目录作为工作区
    """
    candidates = []

    def _ok(p):
        return p and os.path.isdir(p)

    # 优先级 1：显式
    if _ok(explicit):
        return explicit
    if explicit:
        candidates.append(explicit)
    # 优先级 2：锚点（输入文件目录 / 目录本身）
    if anchor:
        if os.path.isdir(anchor):
            if _ok(anchor):
                return anchor
            candidates.append(anchor)
        elif os.path.isfile(anchor):
            parent = os.path.dirname(os.path.abspath(anchor))
            if _ok(parent):
                return parent
            candidates.append(parent)
    # 优先级 3：环境变量
    env = os.environ.get('DSH_WORKSPACE')
    if _ok(env):
        return env
    if env:
        candidates.append(env)
    # 优先级 4：Harness 专属解码
    dec = _decode_session_seg()
    if _ok(dec):
        return dec
    if dec:
        candidates.append(dec)
    # 优先级 5：cwd（可能是 skill 基目录或工作区）
    cwd = os.getcwd()
    if _ok(cwd):
        return cwd
    return candidates[0] if candidates else None


if __name__ == '__main__':
    import sys
    ws = detect_workspace()
    print('workspace:', ws)
    print('is_dir:', bool(ws) and os.path.isdir(ws))
