# packs/ · 行业包机制（P2-9）

SKILL 主流程（SKILL.md + scripts/）是**通用引擎**；赛道定义、标的池、权威源映射、
时点对齐、行业专属纪律全部封装为**可插拔行业包**：

| 目录 | 内容 |
| --- | --- |
| `packs/robotics/` | 机器人行业包（当前激活）：5 个 YAML + RULES.md |
| `config/` | **当前激活包**（脚本只读这里，由 `pack.py activate` 维护） |

## 操作

```bash
python scripts/pack.py list                      # 查看已有行业包
python scripts/pack.py activate robotics         # 切换（自动备份旧 config/ 到 config/_backup/）
python scripts/pack.py wizard 旧月报.docx --name medtech   # 新行业：反推生成包骨架（带 TODO，人工补全后 activate）
```

## 规则

1. 脚本永远只读 `config/`，不直接读 `packs/`；
2. activate 后必须跑 `scripts/snapshot.py snapshot --ym <YYYY-MM>` 落盘新口径快照；
3. 行业专属纪律写在包内 RULES.md（P2 级），通用纪律留在 SKILL.md（P0/P1 级）；
4. wizard 生成的是**候选召回骨架**，标的池需逐家人工判断是否属于赛道后才能启用。
