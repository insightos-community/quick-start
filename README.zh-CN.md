# Semantic Quick Start

[English](README.md) | [简体中文](README.zh-CN.md)


另提供 **macOS Apple Silicon / macOS 15.5+ 原生安装包预览版**，见[安装方法与验证范围](#macos-原生安装包apple-silicon-预览版)。真机图形渲染仍待验收。
> R1 Pro 旧业务模型现已通过清单锁定的资产仓库提供 Git LFS 下载。第三方来源声明见[发布范围](PUBLICATION.md)。组件与整包通过 GitHub Releases 发布，下载时保留第三方来源和许可声明。

🚀 构建并运行 Semantic：连接 Web Studio、调度服务、机器人 Skill、Ability 与仿真的开发工作区。本仓库协调 13 个组件仓库，本身不是 Server。

## 从这里开始

使用预编译产物安装 Semantic，支持 **Linux x86_64**，已在 **Ubuntu 24.04** 验证。需要 Bash、curl 和 Python 3.10+，可选择以下下载来源：

| 下载来源 | 独立安装脚本 | 默认版本 |
|---|---|---|
| 阿里云 OSS | [install.sh](install.sh)，中文提示 | OSS `stable` 通道 |
| GitHub Releases | [install-en.sh](install-en.sh)，英文提示 | 已验证的 `v0.1.0` Release |

### 从阿里云 OSS 安装

```bash
curl -fsSL https://semantic.insightos.cn/install.sh -o install.sh
bash install.sh --install-system-deps
```

安装器读取公开 OSS 通道清单，从阿里云 OSS 下载整包并校验 SHA-256，无需 OSS 账号或凭据。可用 `--version <OSS版本号>` 选择已发布的 OSS 版本，或用 `--base-url <HTTPS地址>` 指定其他制品站点。

### 从 GitHub Releases 安装

```bash
curl -fsSL https://raw.githubusercontent.com/insightos-community/quick-start/main/install-en.sh -o install-en.sh
bash install-en.sh --version v0.1.0 --install-system-deps
```

安装器下载 [GitHub Release](https://github.com/insightos-community/quick-start/releases/tag/v0.1.0)，校验文件哈希、发布身份和 `v0.1.0` 固定源码提交。模型缺失或仍为 LFS 指针时，按清单锁定的 GitHub 资产提交通过 Git LFS 补齐，并校验大小和 SHA-256；无需克隆组件仓库或安装 Git LFS 客户端。`--version` 对应 GitHub Tag，省略时也默认使用 `v0.1.0`。

两个通道的版本号和发布时间各自独立，OSS `stable` 不一定与 GitHub `v0.1.0` 是同一构建。

### 可选 musl 安装（包内或宿主运行时）

默认安装方式仍使用 glibc。在 **Linux x86_64** 系统上，显式添加 `--musl` 选择额外安装包。新版默认使用包内 musl，也可在 glibc 系统上运行：

```bash
curl -fsSL https://raw.githubusercontent.com/insightos-community/quick-start/main/install.sh -o install.sh
bash install.sh --musl --musl-runtime bundled --install-system-deps
```

选择 `--musl-runtime bundled` 使用随包提供的 musl 1.2.5；选择 `--musl-runtime system` 使用宿主的 `/lib/ld-musl-x86_64.so.1`（musl 1.2+）。省略此选项时，新版本默认 `bundled`，重装保留已有选择。切换运行时须使用新的 `--dir`，不会写入系统 `/lib` 或修改全局库路径。

中英文脚本均支持此参数，并默认从 GitHub Release 下载 musl 制品。Robot 与 MuJoCo 的独立虚拟环境共用一套随包提供的 CPython 3.13.15，均使用 NumPy 2.3.5；同时包含验证过的 musl 机器人依赖与 Mesa。安装期间无需下载 Python 或编译源码。Alpine 软件包依赖通过用户机器现有的 APK 源安装，不改写源配置。

默认 `--render-backend auto` 会测试 Mesa GPU 渲染，不可用时回退到 llvmpipe；`--render-backend software` 强制软件渲染，`--render-backend mesa-gpu` 要求 GPU 测试成功。AMD radeonsi 已完成本地实机测试；包含的 Intel、Nouveau 驱动尚未经过对应硬件验证。NVIDIA 专有驱动仍使用默认 glibc 安装路径。详见 [musl 制品与验证说明](artifacts/musl/README.md)。

尝试不同变体请使用独立的 `--dir`。`--musl --version musl-v0.1.0-2` 指定可选版本；普通 `v0.1.0` 和 OSS stable 安装渠道保持原样。

### 从仓库运行与实例管理

当前 `main` 的仓库根目录也包含这两个脚本。克隆仓库后，选择其中一个执行：

```bash
bash ./install.sh --install-system-deps     # 阿里云 OSS
bash ./install-en.sh --install-system-deps  # GitHub Releases
```

两个脚本均可单独复制到其他目录运行，不会再下载额外的安装器代码。可先查看脚本，再用 `bash install.sh --help` 或 `bash install-en.sh --help` 查看参数。无需 Go、Node 或 xmake 构建工具；首次安装会下载独立 Python 环境。`--install-system-deps` 可能需要 sudo，使用用户机器已配置的系统软件源，不改写源配置；英文安装器也保留用户的 uv 配置和包索引。

用 `--dir /绝对路径/实例目录` 安装独立实例。预编译安装的管理员账号为 `admin`，密码随机生成，可用 `~/.local/share/semantic/bin/semanticctl welcome` 查看（自定义 `--dir` 时调整路径）。服务管理使用 `semanticctl start|stop|status|doctor`，详见[安装管理](artifacts/README.md)。

如需从源码构建，使用已验证的公开基线：

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
git checkout v0.1.0
python3 semantic_installer.py --list
```

根目录安装脚本位于当前 `main`，已有 `v0.1.0` 源码 Tag 保持不变。源码构建下载模型后仍需完成 Bundle 激活与 Skill 发布。

## 🛠 源码构建

步骤 2.3 的场景资产仍通过 Git LFS 拉取；第三方 Wheel 优先复用已校验的本地缓存，
再通过 `pip download` 从 `UV_DEFAULT_INDEX` 指定的包源下载。文件名、大小和 SHA-256
均以当前检出版本的 LFS 指针为准，不升级依赖。包源缺失或文件不一致时回退 LFS；
经过特殊处理的 TinyXML2/urdfdom Wheel 仍使用 LFS。下载结果用于后续离线 Bundle，
不会安装到系统 Python。设置 `RUNTIME_WHEEL_SOURCE=auto`（默认）、`lfs`（跳过包源）
或 `offline`（仅检查运行时缓存，场景资产仍走 LFS）。已修改的缓存文件会保留并报错。

2.3 同时下载已确认发布的 R1 Pro 模型文件（XML/URDF、配置与 Mesh），2.4 检查模型入口
及引用文件。chassis 与 tote/gripper 目录应保持完整；不要继续使用之前不含模型的资产 tag。
第三方模型保留其原有权利与来源声明。

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
| 7 | 实操示例：拆码垛场景测试，通过对话进行场景任务规划 | 可审阅的任务计划 |

启动 Server 后，默认用户名为 `admin`，密码为 `test-admin-pass`；如已修改，使用 `.env` 中的 `SEMANTIC_ADMIN_PASSWORD`。

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

**推荐构建版本：`v0.1.0`。** 请先 `git checkout v0.1.0`，再运行安装器进行构建。该 Tag 中的 [repo-versions.json](https://github.com/insightos-community/quick-start/blob/v0.1.0/repo-versions.json) 是可用、已验证的组件版本组合，固定了全部 13 个仓库的 Tag 与提交 SHA。已有克隆请先执行 `git fetch origin --tags`。

发布及后续镜像同步均基于已验证的维护版本，不跟随上游或默认分支的领先版本。请使用 `repo-versions.json` 固定的 Tag 与提交，详见[发布策略](maintenance/release-policy.md)和 [v0.1.3 记录](maintenance/v0.1.3.md)。

```bash
# 已默认配置 insightos-community 组织及仓库映射。
python3 repo_versions.py --env github.env --show-config
python3 -m unittest discover -s tests
```

该配置用于 `repo_versions.py`，不是安装器参数。对外分发前应准备地址可公开访问、revision 相匹配的清单。详见[仓库配置参考](README.reference.md)与[开源发布检查清单](maintenance/open-source-readiness.md)。

TUI 中 `e` 配置、Enter 执行步骤、`L` 查看服务日志、`x` 停止托管服务。预编译安装使用 `semanticctl start|stop|status|doctor`，详见[安装管理](artifacts/README.md)。

## 常见问题

- Wheel 无效：重跑 5.1–5.2 的源码构建与复制；LFS 指针不是二进制产物。
- sudo 使用 Linux 用户登录密码，不是 Web 管理员密码。安装前先验证，失败原因显示在表单中；
  TUI 输入有问题时，按 `e` 设置 `SUDO_AUTH=terminal` 后重跑。
- Robot 离线或缺 Skill：检查 Runtime 登记、激活 Bundle 和已发布 Skill 的精确版本。
- 步骤失败会停止队列；重跑前查看 `.tui-logs/`。
- 密码和模型 Key 仅保存在本地，不向不可信网络开放开发服务。

[详细 TUI 指南](semantic-installer-README.md) · [排障笔记](NOTES.md)

## 许可证

Copyright 2026 InsightOS。自有代码采用 [Apache-2.0](LICENSE)；第三方代码、模型与二进制资产请查看 [NOTICE](NOTICE) 和[许可范围](LICENSE_SCOPE.md)。


### macOS 原生安装包（Apple Silicon 预览版）

支持 **Apple Silicon / macOS 15.5+**，随包提供 Python 3.13.15、NumPy 2.3.5、
原生服务、离线 Python 依赖和 MuJoCo 场景资产，无需 Homebrew、系统 Python 或编译器。
从 [macOS 预览版 Release](https://github.com/insightos-community/quick-start/releases/tag/macos-v0.1.0-rc.2)
下载 `semantic-*-macos-arm64.tar.gz`，解压后执行：

```bash
bash install.command --yes
```

默认安装到 `~/Library/Application Support/Semantic`，访问 `http://127.0.0.1:3000`。
使用安装目录下的 `bin/semanticctl` 启动、停止、查看状态或卸载；
`semanticctl welcome` 在终端显示安装时生成的 admin 密码。
可传入 `--dir "$HOME/semantic"` 指定目录。Release 中的 `install-macos.sh`
支持下载并校验安装包。

这是未签名预览版，已执行的验证见 Release 的 `validation.json`。
真机 CGL 图形和完整 AI 拆码垛任务仍待验收；暂不承诺 Intel Mac、LIBERO/Robosuite
或厂商硬件驱动。详见 [macOS 构建说明](artifacts/macos/README.md)。

## 三个平台的构建复现

参见 [glibc、musl 与 macOS 构建说明](README.build.md)：包含已锁定的源码版本、实际脚本入口、工具要求、本地与 CI 指令、产物位置和平台验证范围。
