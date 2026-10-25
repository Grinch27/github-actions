# AGENTS.md Part I 统一维护

`Grinch27/github-actions` 是十一个仓库 GitHub Actions 通用规范 **Part I** 的唯一维护源。各仓库的 `AGENTS.md` 均保留独立完整的 Part I；**Part II 由各项目独立维护**，不在统一规范范围内。

- 统一规范正文：[`docs/agents/part-i.md`](part-i.md)
- 当前版本：**1.3.0**（以正文中的 `COMMON_RULES_VERSION` 为准）
- 管理方式：**人工维护，无自动检查、自动同步或定期任务**

## 使用该规范的仓库

- [Grinch27/twrp_builder](https://github.com/Grinch27/twrp_builder/blob/main/AGENTS.md)
- [Grinch27/openwrt-compiler](https://github.com/Grinch27/openwrt-compiler/blob/main/AGENTS.md)
- [Grinch27/docker-builder](https://github.com/Grinch27/docker-builder/blob/main/AGENTS.md)
- [Grinch27/uboot-mtk-compiler](https://github.com/Grinch27/uboot-mtk-compiler/blob/main/AGENTS.md)
- [Grinch27/aosp-builder](https://github.com/Grinch27/aosp-builder/blob/main/AGENTS.md)
- [Grinch27/VRviewer](https://github.com/Grinch27/VRviewer/blob/main/AGENTS.md)
- [Grinch27/awara](https://github.com/Grinch27/awara/blob/main/AGENTS.md)
- [Grinch27/ECID](https://github.com/Grinch27/ECID/blob/main/AGENTS.md)
- [Grinch27/archive-kemono](https://github.com/Grinch27/archive-kemono/blob/main/AGENTS.md)
- [Grinch27/ffmpeg-compiler](https://github.com/Grinch27/ffmpeg-compiler/blob/main/AGENTS.md)
- [Grinch27/cloudflare-workers-doh-ecs](https://github.com/Grinch27/cloudflare-workers-doh-ecs/blob/main/AGENTS.md)

## 人工维护规则

1. 修改通用规范时，先编辑唯一维护源 `docs/agents/part-i.md`，并按实际变更调整 `COMMON_RULES_VERSION`。
2. 在获得对应仓库写入授权后，逐仓库人工更新 `AGENTS.md` 中从 **`# Part I — GitHub Actions 通用规范`** 到 **`<!-- END: NEW WORKFLOW RULES -->`** 的完整区域。
3. 不修改上述区域以外的内容，尤其不得改写各仓库 Part II、历史项目维护约束或项目安全边界。
4. 需要确认版本一致时，可以人工查看版本标识并比较 Part I 实际正文；版本号相同并不必然表示内容相同。
5. 核实每次提交仅包含当前批准的文档改动，不得以文档规范维护为由自动改写工作流、触发编译或发布产物。

**本项目不提供 Part I 检查脚本、同步脚本、GitHub Actions 定期检查或自动跨仓库更新。** 统一维护源是文档，不是持续运行的自动化系统。

## 新增仓库

新增需要使用通用规范的仓库时，先审查其现有 `AGENTS.md` 和专属约束，再经明确授权将当前 Part I 复制到其前部，保留独立 Part II。新增的仓库可在本文件登记，但不会自动加入任何自动化任务。
