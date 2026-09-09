# Semantic Quick Start

[English](README.md) | [简体中文](README.zh-CN.md)

> 本次源码公开快照不包含星海图模型，也不默认指向旧的预编译安装包。详见[发布范围](PUBLICATION.md)。R1 Pro 仿真需另行获取和适配模型。

🚀 构建并运行 Semantic：连接 Web Studio、调度服务、机器人 Skill、Ability 与仿真的开发工作区。本仓库协调 13 个组件仓库，本身不是 Server。

## 从这里开始

请从下面的公开源码工作区开始。[制品安装说明](artifacts/README.md)介绍如何安装另行提供的包；本次快照不发布完整二进制部署包。

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
python3 semantic_installer.py --list
```

原有部署基线面向 **Linux x86_64**，已在 **Ubuntu 24.04** 验证。移除外部模型后，本次源码快照不代表开箱即用的完整 R1 Pro 仿真部署。安装系统依赖可能需要 sudo。

## 🛠 源码构建

使用 Linux、Git / Git LFS 和支持 curses 的 Python。源码安装器的系统配置步骤面向 Ubuntu/apt；组件构建还需要 Go 1.23+、Node.js 22、uv 和 xmake。原生 MuJoCo 与 Robot Worker 分别使用独立的 Python 3.10 / 3.13 环境。

```bash
python3 semantic_installer.py --list
python3 semantic_installer.py
```

开始前确认工作目录与仓库地址，通过 [repo-versions.json](repo-versions.json) 指定版本；安装器按清单切换 revision。个人设置、凭据和构建输出不要提交到版本库。

| 顺序 | 工作内容 | 产物 |
|---|---|---|
| 1–2 | 配置工具、克隆仓库、拉取所需 LFS 资产 | 源码工作区与资产 |
| 3 | 编译 Server / Pilot，初始化配置 | `semantic-framework/.output/` |
| 4 | 准备并登记原生 MuJoCo | Runtime 登记与独立环境 |
| 5 | 编译 AbilityFramework、Python Wheel，组装并激活 Robot Bundle | Runtime 种子、Bundle 与目录 |
| 6 | 启动 Server / Web，发布 Robot Skill | Studio 与版本化 Skill 注册表 |
| 7 | 在 Studio 配置模型、项目、场景和 Robot | 可执行的任务环境 |

**Bundle 激活与 Skill 发布是两个独立步骤。** 仅编译 Bundle 不会安装 Robot 所请求的 Skill。

## 工程结构

| 目录 | 职责 |
|---|---|
| `semantic-framework/` | Server、Pilot、管理 CLI |
| `semantic-web/` · `semantic-docs/` | Studio 前端与文档站 |
| `semantic-robotsdk/robot-sdk/` | 机器人统一契约与适配层 |
| `semantic-ability/r1pro-ability/` | R1 Pro 语义能力 |
| `semantic-skill/robot-skill/` | Skill Worker SDK 与任务级 Skill |
| `semantic-simulation/mujoco-runtime/` · `semantic-scene/mujoco-asset/` | 物理仿真与独立治理的资产 |
| `semantic-robot-deployment/` | Bundle 打包与单 Robot 进程管理 |
| `semantic-ability/ability-runtime/` | 构建输入与离线依赖缓存 |
| `ability-framework/{abilityframework,ability-py-sdk,ability-scaffold}/` | Ability 宿主、Python SDK 与工程生成工具 |

各组件均有中英文 README。仓库名称不一定等于本地目录名；跨仓构建时请保留上述布局。

## 版本与日常使用

发布及后续镜像同步均基于已验证的维护版本，不跟随上游或默认分支的领先版本。请使用 `repo-versions.json` 固定的 Tag 与提交，详见[发布策略](maintenance/release-policy.md)和 [v0.1.2 记录](maintenance/v0.1.2.md)。

```bash
# 已默认配置 insightos-community 组织及仓库映射。
python3 repo_versions.py --env github.env --show-config
python3 -m unittest discover -s tests
```

该配置用于 `repo_versions.py`，不是安装器参数。对外分发前应准备地址可公开访问、revision 相匹配的清单。详见[仓库配置参考](README.reference.md)与[开源发布检查清单](maintenance/open-source-readiness.md)。

TUI 中 `e` 配置、Enter 执行步骤、`L` 查看服务日志、`x` 停止托管服务。预编译安装使用 `semanticctl start|stop|status|doctor`，详见[安装管理](artifacts/README.md)。

## 常见问题

- Wheel 无效：重跑 5.1–5.2 的源码构建与复制；LFS 指针不是二进制产物。
- Robot 离线或缺 Skill：检查 Runtime 登记、激活 Bundle 和已发布 Skill 的精确版本。
- 步骤失败会停止队列；重跑前查看 `.tui-logs/`。
- 密码和模型 Key 仅保存在本地，不向不可信网络开放开发服务。

[详细 TUI 指南](semantic-installer-README.md) · [排障笔记](NOTES.md)

## 许可证

Copyright 2026 InsightOS。自有代码采用 [Apache-2.0](LICENSE)；第三方代码、模型与二进制资产请查看 [NOTICE](NOTICE) 和[许可范围](LICENSE_SCOPE.md)。
