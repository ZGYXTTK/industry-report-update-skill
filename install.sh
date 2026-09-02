#!/usr/bin/env bash
# install.sh · industry-report-update-skill (Apache-2.0)
# 一键安装到 12 个 Tier-1 工具 + 通用 ~/.agents/skills/ 兜底
# 用法：bash install.sh
# 可选：SKILL_DIR=/custom/path bash install.sh

set -euo pipefail

SKILL_NAME="industry-report-update-skill"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SKILL_DIR:-$SCRIPT_DIR}"

# 通用兜底（任何读取 AGENTS.md 的工具）
mkdir -p "$HOME/.agents/skills"
ln -sfn "$SOURCE_DIR" "$HOME/.agents/skills/$SKILL_NAME"
echo "[OK] Linked → ~/.agents/skills/$SKILL_NAME"

# Tier-1 工具（SKILL.md 原生支持）
declare -A TIERS=(
    [Claude Code]="$HOME/.claude/skills"
    [OpenCode]="$HOME/.config/opencode/skills"
    [Goose]="$HOME/.config/goose/skills"
    [Roo Code]="$HOME/.config/Roo Code/skills"
    [Cline]="$HOME/.config/cline/skills"
    [Kilo]="$HOME/.config/kilo/skills"
    [Kiro]="$HOME/.config/kiro/skills"
    [Factory]="$HOME/.config/factory/skills"
    [Antigravity]="$HOME/.config/antigravity/skills"
    [Gemini CLI]="$HOME/.gemini/skills"
)

for tool in "${!TIERS[@]}"; do
    target_dir="${TIERS[$tool]}"
    mkdir -p "$target_dir"
    ln -sfn "$SOURCE_DIR" "$target_dir/$SKILL_NAME"
    echo "[OK] $tool → $target_dir/$SKILL_NAME"
done

# Codex CLI（额外要求 SKILL.md 顶层结构）
mkdir -p "$HOME/.config/Codex/skills"
ln -sfn "$SOURCE_DIR" "$HOME/.config/Codex/skills/$SKILL_NAME"
echo "[OK] Codex CLI → ~/.config/Codex/skills/$SKILL_NAME"

# Cursor（Windows 路径在 install.ps1 处理；Unix 用 ~/.config）
mkdir -p "$HOME/.config/Cursor/User/skills"
ln -sfn "$SOURCE_DIR" "$HOME/.config/Cursor/User/skills/$SKILL_NAME"
echo "[OK] Cursor → ~/.config/Cursor/User/skills/$SKILL_NAME"

echo ""
echo "========================================="
echo "  installation complete (Apache-2.0)"
echo "  source: $SOURCE_DIR"
echo "  tool: $SKILL_NAME v1.0.0"
echo ""
echo "  uninstall:"
echo "    rm ~/.agents/skills/$SKILL_NAME"
echo "========================================="