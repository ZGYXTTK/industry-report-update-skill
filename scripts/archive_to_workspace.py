# -*- coding: utf-8 -*-
"""
archive_to_workspace.py —— 把本期 run 的全部产出镜像到「Skill 使用者当前对话工作区」。

这是 Skill 的 P1 强制收尾步骤（Step 9.5）：保证任何一次调用，产出都出现在
使用者的当前对话工作区（而非 skill 基目录/AppData 缓存）。

用法：
  python scripts/archive_to_workspace.py --run-id <run-id> [--ws <工作区>] [--product <名称>]
  # --ws 可省略：脚本按 workspace.detect_workspace() 自动解析工作区
  # 产物落到  <工作区>/<product>_产出/   下（根、源文件/、门禁报告/ 三处）
"""
import argparse
import os
import shutil
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
RUNS = os.path.join(BASE, 'runs')
# skill 基目录下的下载资料（adapters.py 默认落盘点）
DOWNLOAD_DATA = os.path.join(BASE, '下载资料')

sys.path.insert(0, HERE)
import workspace  # noqa: E402

# 门禁/审计报告文件名（logs 里以 .md 结尾的运行类报告）
REPORT_MD = ['格式对比报告.md', '一致性校验报告.md', '交叉一致性报告.md',
             '空值对比报告.md', '溯源反查报告.md', '配置校验报告.md',
             '运行日志.md', '通道降级日志.md', '通道健康度-*.md']
SOURCE_EXT = ('.csv', '.jsonl', '.xlsx', '.json')
SOURCE_PREFIX = ('采集_', '溯源', '通道实测', '来源记录', 'QVeris', '工具清单')


def _norm(p):
    """归一化路径：abspath + normcase + 统一正斜杠，供前缀比较。"""
    return os.path.normcase(os.path.abspath(p)).replace('\\', '/')


def _inside_base(p):
    """p 是否位于 skill 基目录内（或与其相等）。按「段边界」比较，避免"共享前缀的兄弟目录"误判。"""
    n = _norm(p)
    b = _norm(BASE)
    return n == b or n.startswith(b + '/')


def _md_is_report(name):
    for pat in REPORT_MD:
        if pat.endswith('-*.md'):
            head = pat[:-len('-*.md')]  # '通道健康度'
            if name.startswith(head + '-') and name.endswith('.md'):
                return True
        elif name == pat:
            return True
    return False


def archive(run_id, ws, product):
    run = os.path.join(RUNS, run_id)
    if not os.path.isdir(run):
        raise SystemExit('❌ 找不到 run 目录：%s' % run)
    out_root = os.path.join(ws, '%s_产出' % product)
    os.makedirs(out_root, exist_ok=True)
    src_dir = os.path.join(out_root, '源文件')
    gate_dir = os.path.join(out_root, '门禁报告')
    in_dir = os.path.join(out_root, '输入')
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(gate_dir, exist_ok=True)
    os.makedirs(in_dir, exist_ok=True)

    copied = 0

    def cp(src, dst_dir):
        nonlocal copied
        if not os.path.isfile(src):
            return
        shutil.copy2(src, os.path.join(dst_dir, os.path.basename(src)))
        copied += 1

    # ① 主产出（output/）
    odir = os.path.join(run, 'output')
    if os.path.isdir(odir):
        for f in os.listdir(odir):
            if f.endswith('.docx') or f.endswith('.md'):
                cp(os.path.join(odir, f), out_root)

    # ② 输入（input/：旧月报、用户确认等）
    idir = os.path.join(run, 'input')
    if os.path.isdir(idir):
        for f in os.listdir(idir):
            if f.endswith('.docx') or f.endswith('.md') or f.endswith('.txt'):
                cp(os.path.join(idir, f), in_dir)

    # ③ 源文件（download/ + sources/ + skill base 下载资料/）
    for sub in [('download', src_dir), ('sources', src_dir)]:
        sdir = os.path.join(run, sub[0])
        if os.path.isdir(sdir):
            for f in os.listdir(sdir):
                if f.startswith(SOURCE_PREFIX) or f.endswith(SOURCE_EXT) or f.endswith('.md'):
                    cp(os.path.join(sdir, f), sub[1])
    if os.path.isdir(DOWNLOAD_DATA):
        for f in os.listdir(DOWNLOAD_DATA):
            if f.endswith('.csv'):
                cp(os.path.join(DOWNLOAD_DATA, f), src_dir)

    # ④ 门禁报告（logs/）
    ldir = os.path.join(run, 'logs')
    if os.path.isdir(ldir):
        for f in os.listdir(ldir):
            if f.endswith('.md') and _md_is_report(f):
                cp(os.path.join(ldir, f), gate_dir)
    # 通道健康度报告可能在 run 根
    for f in os.listdir(run):
        if f.endswith('.md') and f.startswith('通道健康度'):
            cp(os.path.join(run, f), gate_dir)

    print('✅ 已归档到工作区：%s' % out_root)
    print('   复制文件数：%d' % copied)
    for d in [out_root, in_dir, src_dir, gate_dir]:
        print('   - %s' % d)
    return out_root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--ws', default=None, help='当前对话工作区路径（缺省自动探测）')
    ap.add_argument('--anchor', default=None,
                    help='位于工作区内的文件/目录（如输入旧月报原始路径），以其所在目录作为工作区；'
                         'open-source 环境下最可靠，任何运行环境通用')
    ap.add_argument('--product', default='机器人行业重点赛道行业与资本市场动态月报',
                    help='产出目录前缀')
    a = ap.parse_args()

    anchor = a.anchor
    # 若未显式给锚点，尝试从 manifest 读取输入旧月报原始路径作为锚点
    if not anchor:
        import json
        mf = os.path.join(RUNS, a.run_id, 'manifest.json')
        if os.path.isfile(mf):
            try:
                m = json.load(open(mf, encoding='utf-8'))
                for k in ('input.old_doc', 'input.old_report', 'input.old_docx'):
                    if m.get(k):
                        anchor = m[k]
                        break
                if not anchor:
                    anchor = (m.get('input') or {}).get('old_doc')
            except Exception:
                pass

    ws = workspace.detect_workspace(a.ws, anchor=anchor)
    if not ws or not os.path.isdir(ws):
        raise SystemExit('❌ 无法确定当前对话工作区：请传入 --ws <工作区路径> 或 --anchor <工作区内文件/目录>'
                         '（如输入旧月报原始路径）；亦可用 `Get-Location`/`pwd` 获取工作区。')
    # 避免把产物写回 skill 基目录（统一分隔符归一化比较，Windows 下也生效）
    if _inside_base(ws):
        raise SystemExit('❌ 解析到的工作区与 skill 基目录冲突，请显式传入 --ws/--anchor 指向真实工作区。')
    archive(a.run_id, ws, a.product)


if __name__ == '__main__':
    main()
