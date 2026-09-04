# install.ps1 · industry-report-update-skill (Apache-2.0)
# 一键安装到 12 个 Tier-1 工具 + 通用 ~/.agents/skills/ 兜底
# 用法：pwsh -File install.ps1
# 可选：pwsh -File install.ps1 -SkillDir "D:\path\to\skill"

[CmdletBinding()]
param(
    [string]$SkillDir = ""
)

$ErrorActionPreference = 'Stop'
$SkillName = 'industry-report-update-skill'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = if ($SkillDir) { $SkillDir } else { $ScriptDir }

if (-not (Test-Path $SourceDir)) {
    Write-Error "Source dir not found: $SourceDir"
    exit 1
}

function New-SymlinkOrJunction {
    param(
        [string]$LinkPath,
        [string]$TargetPath,
        [string]$Label
    )
    $parent = Split-Path -Parent $LinkPath
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    if (Test-Path $LinkPath) {
        Remove-Item $LinkPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Windows 上对开发目录优先用 Junction（无需管理员）
    try {
        $cmd = Get-Command cmd.exe -ErrorAction Stop
        & cmd.exe /c mklink /J "$LinkPath" "$TargetPath" | Out-Null
        if (Test-Path $LinkPath) {
            Write-Host "[OK] $Label -> $LinkPath"
            return
        }
    } catch {}
    # fallback: 用 New-Item -SymbolicLink（如支持）
    try {
        New-Item -ItemType SymbolicLink -Path $LinkPath -Target $TargetPath -Force | Out-Null
        Write-Host "[OK] $Label -> $LinkPath"
    } catch {
        # 最终 fallback: 复制
        Copy-Item -Path $TargetPath -Destination $LinkPath -Recurse -Force
        Write-Host "[OK-DIR] $Label (copied) -> $LinkPath"
    }
}

# 通用兜底
New-SymlinkOrJunction `
    -LinkPath "$env:USERPROFILE\.agents\skills\$SkillName" `
    -TargetPath $SourceDir `
    -Label "universal (~/.agents/skills)"

# Tier-1 工具
$tools = @(
    @{ Name = "Claude Code";     Dir = "$env:USERPROFILE\.claude\skills" },
    @{ Name = "OpenCode";        Dir = "$env:USERPROFILE\.config\opencode\skills" },
    @{ Name = "Goose";           Dir = "$env:USERPROFILE\.config\goose\skills" },
    @{ Name = "Roo Code";        Dir = "$env:USERPROFILE\.config\Roo Code\skills" },
    @{ Name = "Cline";           Dir = "$env:USERPROFILE\.config\cline\skills" },
    @{ Name = "Kilo";            Dir = "$env:USERPROFILE\.config\kilo\skills" },
    @{ Name = "Kiro";            Dir = "$env:USERPROFILE\.config\kiro\skills" },
    @{ Name = "Factory";         Dir = "$env:USERPROFILE\.config\factory\skills" },
    @{ Name = "Antigravity";     Dir = "$env:USERPROFILE\.config\antigravity\skills" },
    @{ Name = "Gemini CLI";      Dir = "$env:USERPROFILE\.gemini\skills" },
    @{ Name = "Codex CLI";       Dir = "$env:USERPROFILE\.config\Codex\skills" },
    @{ Name = "Cursor";          Dir = "$env:APPDATA\Cursor\User\skills" }
)

foreach ($tool in $tools) {
    $link = Join-Path $tool.Dir $SkillName
    New-SymlinkOrJunction -LinkPath $link -TargetPath $SourceDir -Label $tool.Name
}

Write-Host ""
Write-Host "========================================="
Write-Host "  installation complete (Apache-2.0)"
Write-Host "  source: $SourceDir"
Write-Host "  tool: $SkillName v3.1"
Write-Host ""
Write-Host "  uninstall:"
Write-Host "    Remove-Item `$env:USERPROFILE\.agents\skills\$SkillName -Recurse -Force"
Write-Host "========================================="