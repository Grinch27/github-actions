# AGENTS.md Part I 统一维护

本目录是六个受管仓库的 GitHub Actions 通用规范 **Part I 的唯一维护源**。项目专属的 Part II 始终留在各自仓库中，由项目独立维护。

- 统一正文：`docs/agents/part-i.md`
- 当前版本：**1.0.0**（以 `COMMON_RULES_VERSION` 为准）
- 检查与同步脚本：`scripts/agents_part_i.py`
- 定期检查工作流：`.github/workflows/check-agents-part-i.yml`（只读，不自动写入）

目前纳入管理的仓库：

- [Grinch27/twrp_builder](https://github.com/Grinch27/twrp_builder/blob/main/AGENTS.md)
- [Grinch27/openwrt-compiler](https://github.com/Grinch27/openwrt-compiler/blob/main/AGENTS.md)
- [Grinch27/docker-builder](https://github.com/Grinch27/docker-builder/blob/main/AGENTS.md)
- [Grinch27/uboot-mtk-compiler](https://github.com/Grinch27/uboot-mtk-compiler/blob/main/AGENTS.md)
- [Grinch27/aosp-builder](https://github.com/Grinch27/aosp-builder/blob/main/AGENTS.md)
- [Grinch27/VRviewer](https://github.com/Grinch27/VRviewer/blob/main/AGENTS.md)

## 单一版本与内容校验

上述仓库的 Part I 使用完全相同的文本，包括标题、版本注释、参考链接、规则正文及 `<!-- BEGIN: NEW WORKFLOW RULES -->` / `<!-- END: NEW WORKFLOW RULES -->` 分隔标记。

版本号放在正文内，例如：`<!-- COMMON_RULES_VERSION: 1.0.0 -->`。每次修改统一规范时应根据变更性质递增版本号，同时将更改同步到全部目标仓库。**版本号相同仍不足以证明同步**：检查脚本还对 Part I 的实际 UTF-8 内容进行逐字节一致性比较，并打印 SHA256。

每个目标仓库的 Part II、原有维护规则及标记之外的所有内容都不参与统一替换；不得因 Part I 更新而清理、整理或覆盖项目专属内容。

## 操作方法

从本仓库工作区执行：

```bash
# 只读检查：默认模式，也适用于 CI。
python3 scripts/agents_part_i.py --check

# 仅检查单个仓库。
python3 scripts/agents_part_i.py --check --repo docker-builder

# 经批准后，由持有六个目标仓库 Contents: write 权限的操作者手动执行：
GH_TOKEN=... python3 scripts/agents_part_i.py --write

# 写入后再次只读核验。
python3 scripts/agents_part_i.py --check
```

不要将访问令牌写入命令历史、文档、仓库或日志。上例的 `GH_TOKEN=...` 为占位示意；实际使用已授权的安全凭据提供方式。校验功能不要求写权限。

`--write` 会读取目标 `main` 的现有 `AGENTS.md` 和文件 SHA，在 GitHub Contents API 更新前验证存在完整 Part I，且仅替换该区间；目标文件在读取后被并发修改时由 SHA 校验阻止覆盖。它不会创建缺失文档、变更 Part II、修改工作流、触发手动构建或发布。

**不配置自动跨仓库写入**。统一维护源变更后，检查工作流会报告 DRIFT；需要经批准同步。当前托管仓库公开，检查工作流读取这些公开 `AGENTS.md` 时不需要目标仓库写入凭据。

## 变更流程

1. 在 `docs/agents/part-i.md` 修改通用规则，必要时提高 `COMMON_RULES_VERSION`。
2. 确认该部分没有任何仓库专属的路径、权限或发布约束；项目特例必须写入该项目的 Part II。
3. 审阅变更，保证 GitHub Actions 示例语法有效、已有安全边界不被误覆盖。
4. 执行只读检查；未同步时返回 DRIFT 属于预期状态。
5. 按本次授权使用同步脚本，或以人工审阅的相同内容批量更新五个目标 `AGENTS.md`。
6. 再次运行 `--check`；六个仓库均 OK 后方可称为已统一。
7. 检查各仓库提交范围仅限 `AGENTS.md`，尤其保证 `docker-builder` 和 `twrp_builder` 的历史安全约束原文不变。

新增仓库需要先审计是否已有 `AGENTS.md`、项目约束和写入权限，再调整仓库白名单，不能直接对任意仓库执行覆盖。

## 当前执行边界

此机制负责**统一文档规范版本**，不自动将现有 Non-container 或 Container 工作流迁移，也不触发 Docker 构建、固件编译或发布。检测到工作流与规范不一致时，应分别记录和授权处理。
