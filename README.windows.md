# Windows 原生适配清单

审计日期：2026-09-13。基线为 `macos-v0.1.0-rc.3` 及其锁定的组件提交。
下方依赖审计以该基线为准；实施进度单独记录。当前没有 Windows installer，
也没有 Windows 整套产品实机运行通过的结论。
编译诊断、源码版本及 PyPI 文件检查见 [审计记录](artifacts/windows/audit-2026-09-13.json)。

首版建议目标：Windows 11 x64、普通用户安装、本机 Server/Web/Pilot/AbilityFramework/MuJoCo，
沿用一套随包 CPython 3.13 和 NumPy 2.3.5。Robot、Simulation 和 Skill 可以保留隔离的 venv，
但共享同一 Python 基础运行时。Windows ARM64、Windows Service、可选 LIBERO/Robosuite 和正式 MSI 可后续扩展。
运行和安装不依赖 WSL、Docker、Git Bash、预装 Python 或编译器。

## 实施进度

官网与安装脚本的优先改动已通过 [quick-start PR #17](https://github.com/insightos-community/quick-start/pull/17)
合并并部署；macOS 安装包已发布为 `macos-v0.1.0-rc.4`。

第一项 Windows 代码适配见 [semantic-deployment PR #5](https://github.com/insightos-community/semantic-deployment/pull/5)：
supervisor 与 debug stack 的实例锁接入 `internal/ports/filelock`，
提供 Linux/macOS `flock` 和 Windows `LockFileEx` 实现。
新增三平台原生 CI，验证非阻塞互斥、独立进程竞争、解锁/关闭及进程崩溃后的恢复。
验证结果见 [CI](https://github.com/insightos-community/semantic-deployment/actions/runs/34756652306)。

仅此平台接口能够在 Windows 构建和测试，不代表完整 supervisor 或 installer 已支持 Windows。
进程树、正常停止 IPC、进程身份和 Pinocchio 可重定位产物仍待推进。
在 semantic-deployment 中使用 Go 1.25.8 复现（Windows PowerShell 同样适用）：

```text
go test ./internal/ports/... -count=1 -timeout=2m
```

## 实施路线与 ports 边界

Pinocchio 属于“已有 Windows 支持，需要补齐本项目的构建与发布”，不需要从零移植算法。
组织已有 [insightos-community/pinocchio](https://github.com/insightos-community/pinocchio)，直接扩展该 fork。
检查到的 3.9.0 源码包含 Windows Release、clang-cl 和 Python standalone CI 路径，
`pixi.toml` 声明 `win-64`、Windows Python 安装目录和碰撞依赖。
参见 [现有 CI](https://github.com/insightos-community/pinocchio/blob/2e5854965571237a17934e1baca13d856d053b3c/.github/workflows/macos-linux-windows-pixi.yml)
和 [构建环境](https://github.com/insightos-community/pinocchio/blob/2e5854965571237a17934e1baca13d856d053b3c/pixi.toml)。

自建分两步：先复现上游 Windows 编译/测试，固定 Python 3.13、NumPy 2.3.5 和完整 URDF/碰撞功能；
再输出能在随包 Python 中离线安装的 wheel/DLL，并在未激活 Pixi/Conda 的干净环境测试。
Pixi 可以作为构建工具，但不能因为它能运行测试，就认定离开其环境的 installer 也能运行。
依赖先采用上游已支持的构建方案；只对确有补丁、版本或发布需求的库补独立构建，不预设全部重写。

Framework 与 supervisor 应建立 ports/平台适配层，集中处理操作系统差异。
业务代码保留实例状态机、启动顺序、hold/stop 证据和错误处理。

| ports 职责 | Unix adapter | Windows adapter | 共同契约 |
| --- | --- | --- | --- |
| 进程树启动和回收 | POSIX 进程组、wait、信号 | 进程句柄、Job Objects、等待/退出码 | 只控制自己创建或已验证归属的进程，保证子进程归属，回收后无残留 |
| 请求正常停止 | 应用协议或约定信号 | 应用 IPC；控制台事件仅在适用时使用 | 请求停止、收到业务停止证据、强制回收必须是三个独立动作 |
| 实例锁 | flock | LockFileEx 或命名 mutex | 互斥、非阻塞竞争、进程崩溃后可恢复 |
| 进程身份 | PID、启动时间、可执行路径 | 句柄、创建时间、映像路径 | 避免 PID 复用后误认或误杀进程 |
| host command | POSIX shell adapter | 明确选择的 PowerShell/cmd adapter | 参数与引号语义清楚、超时取消覆盖子进程 |

可执行后缀、venv 布局、平台标识和默认渲染后端使用集中函数/配置，不必全部包装成接口。
Go 代码按 `linux`、`darwin`、`windows` build tags 选择 adapter；不再用 `!darwin` 代表 Linux。
各调用方的 ports 接口保持小而明确；可复用的底层 adapter 可放入独立版本化的公共 Go 包，
不要让两个仓库互相导入对方的 `internal`，也不要让 Framework 依赖 supervisor 的业务状态机。
AbilityFramework 的 C++ 适配单独实现，并遵守同一进程生命周期契约。

先将当前 Linux/macOS 实现迁入 adapter 并通过原有回归，再增加 Windows adapter。
契约测试必须包含停止未确认时保留 interrupted/对账能力；`Close` 不应暗含无条件强杀。
Windows 下 Job 句柄的拥有者、生命周期、异常退出策略和进程加入时机需要明确设计。

| 工作组 | 相对工作量判断 | 主要不确定性 |
| --- | --- | --- |
| Pinocchio 自建发布 | 中等，构建路线已有依据 | 精确版本组合、NumPy/Boost.Python ABI、DLL 闭包和脱离构建环境运行 |
| Framework / supervisor ports | 核心工作 | 停止协议、状态机与 OS 进程树/锁语义衔接 |
| AbilityFramework | 中等，不能只视为换编译器 | POSIX 权限/网络接口、MSVC 编译与子进程行为 |
| Ability 入口、纯 Python SDK、Web、静态资源 | 通常较小 | 路径、参数、编码和平台元数据 |
| Installer | 中等 | Windows 文件锁、版本切换、无管理员安装和完整卸载 |
| MuJoCo/GLFW 集成 | 代码改动预计较小，验证需单列 | 实际图形会话、驱动、连续帧和上下文生命周期 |

这些是源码审计后的相对判断，不是已经完成的 Windows 构建结果或工期承诺。

## 已确认的结论

| 检查 | 结果 | 对适配的影响 |
| --- | --- | --- |
| Framework Windows 交叉编译 | 失败：`Setpgid`、`syscall.Kill` 不存在 | 需要拆分进程平台实现，不能只设置 `GOOS=windows` |
| semantic-deployment Windows 交叉编译 | 失败：另有 `Flock`、`LOCK_EX` 等 | supervisor、实例锁和进程身份检查必须适配 |
| 完整第三方依赖按 Windows/3.13 解析，仅允许 wheel | 失败：`pin==3.9.0` 无可用 wheel | Pinocchio 打包是首要依赖阻塞 |
| 暂时移除 Pinocchio 及直接 cmeel 约束的解析探针 | 38 个包成功解析 | 只证明这部分依赖有候选解，不能据此删掉机器人依赖或宣布安装成功 |
| Ability 启动入口 | 7 个包均使用 `#!/usr/bin/env bash` | 架构标签仍为 x86_64 也不能在 Windows 直接执行 |
| Runtime 的后端默认值 | 已有 Windows → `glfw` | 上层 Framework 和 installer 仍可能覆盖成 `egl`，需要贯通修改 |
| Pydantic 一致性 | 三个 Skill 锁定 2.13.4；Runtime 对 Windows 仍选择 2.11.5 | 需要 Windows 的一致约束，避免重现 macOS 离线安装故障 |

交叉编译在 Linux 主机执行，使用发布基线的实际源码：

```bash
# 分别在 Semantic-Framework 和 semantic-deployment 仓库执行
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build ./cmd/...

# 在 quick-start 中执行：当前预期在 pin==3.9.0 处失败
uv pip compile artifacts/macos/installer-requirements.in \
  --python-version 3.13 --python-platform x86_64-pc-windows-msvc \
  --only-binary :all: --generate-hashes -o /tmp/windows-probe.lock
```

上述 macOS requirements 仅用于检查现有版本组合；最终必须生成独立的 Windows 输入文件和锁文件。

## P0：依赖和核心进程可运行

### Python 与数学依赖

以下结果来自指定版本的 PyPI 文件清单，按标准 CPython 3.13 / `win_amd64` 标签检查。
“有 wheel”不等于已验证 DLL 加载或业务行为。

| 依赖 | 当前版本 | Windows x64 候选产物 | 待办 |
| --- | --- | --- | --- |
| MuJoCo | 3.4.0 | 有 `cp313-cp313-win_amd64` wheel | 使用上游 wheel，测试物理步进和渲染 |
| NumPy | 2.3.5 | 有 `cp313-cp313-win_amd64` wheel | 验证与自建 Pinocchio/EigenPy 的 NumPy ABI |
| Ruckig | 0.19.4 | 有 `cp313-cp313-win_amd64` wheel | 优先复用，测试轨迹生成；自建作为复现选项 |
| GLFW | 2.10.2 | 有 `py2.py3-none-win_amd64` wheel | 检查随包 DLL 与 OpenGL 上下文 |
| Pydantic / pydantic-core | 2.13.4 / 2.46.4 | 通用 wheel / Windows cp313 wheel | 统一 Runtime、Robot 和三个 Skill 的约束 |
| Pinocchio / libpinocchio | 3.9.0 | 无匹配的 PyPI Windows wheel | 建立 Windows 原生构建及可重定位 wheel |
| EigenPy / Coal / libcoal | 3.12.0 / 3.0.2 / 3.0.2 | 无匹配的 PyPI Windows wheel | 与 Pinocchio 一起构建、验证 |
| cmeel 原生依赖 | Boost 1.89.0、urdfdom 4.0.1、tinyxml2 10.0.0、console-bridge 1.0.2.3、Assimp 6.0.5、OctoMap 1.10.0、Qhull 8.0.2.1、zlib 1.3.2 | 当前这些 wheel 无 Windows 候选 | 确定源码版本、功能开关和 Windows DLL/头文件发布方式 |
| uvloop | 0.22.1 | 无 Windows wheel | 按依赖平台 marker 排除，使用 Windows asyncio；无需移植 uvloop |

- [ ] 锁定 Windows CPython 3.13 标准 ABI 和 `uv.exe` 发行文件、来源及 SHA-256。验证完整标准库、`venv`、SSL、SQLite 和证书读取。uv 官方支持 Windows x64。[uv 平台说明](https://docs.astral.sh/uv/reference/policies/platforms/)
- [ ] 选择可重定位、能创建 venv 的完整 Python 分发。不要直接假设 Python embeddable ZIP 等价于当前运行时；其默认不含 pip，常规 pip 依赖管理也不属于官方支持用途。[Python Windows 分发说明](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)
- [ ] 以同一 MSVC 工具链、CPython/NumPy ABI 构建 Pinocchio 依赖链，固定 Boost.Python、Eigen、EigenPy、Coal、URDF 和 mesh 导入依赖。现有 Pinocchio 源码已有 Windows 分支；缺的是满足本项目版本组合的交付产物，并非库完全不支持 Windows。[Pinocchio 3.9.0](https://pypi.org/project/pin/3.9.0/)
- [ ] 保留 URDF 和碰撞功能。Robot SDK 实际调用 `buildModelsFromUrdf`、`GeometryData`、碰撞检测，不能通过关闭这些能力来换取“编译通过”。[调用位置](https://github.com/insightos-community/robot-sdk/blob/59a1a8364c3d0330f1802c020e37544e0dbfa7c5/packages/r1pro/src/semantic_robot_sdk_r1pro/providers/local_kinematics.py#L53)
- [ ] 确定 wheel 结构及 METADATA 依赖：不能让自建 wheel 继续要求不存在的 Windows cmeel wheel；也不能只复制 DLL 而漏掉依赖声明。
- [ ] 收集 `.pyd`/`.dll` 的直接和递归依赖，处理 DLL 搜索目录、同名库冲突、VC Runtime 部署，记录实际加载位置。测试时清除构建工具和 Conda/Pixi 路径，确保运行不依赖构建机。[DLL 搜索规则](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)、[Python DLL 目录接口](https://docs.python.org/3.13/library/os.html#os.add_dll_directory)
- [ ] 生成 Windows 完整离线 wheelhouse 和带哈希的锁文件；运行 `pip check`、URDF/mesh 读取、FK/IK、碰撞和 Ruckig 数值测试。

### Semantic-Framework 与 semantic-deployment

- [ ] 将 POSIX 实现拆到受 build tag 约束的文件，新增 Windows 实现。现有部分 `*_other.go` 使用 `!darwin`，会把 Windows 错当成 Linux。
- [ ] 替换 `Setpgid`、负 PID 发信号、`Getpgid`、`Signal(0)`、`/proc/<pid>` 检查；实现启动、存活、身份校验、停止、超时和日志采集。
- [ ] 用 Windows Job Objects 等机制管理本实例拥有的进程树，检查子进程加入时机与句柄继承。保留现有“先 hold/stop、确认后回收”的顺序；停止未确认时保留 interrupted 状态，不能因关闭 Job 句柄而无条件杀掉仍需保留的进程。异常退出策略需单独设计并测试。[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [x] 将 semantic-deployment 的实例 `Flock` 接入 Linux/macOS/Windows 平台文件锁；覆盖并发启动、异常退出与锁恢复，见上方 PR #5。其他进程平台接口仍待适配。
- [ ] 检查 Runtime 管理器、Robot supervisor、Pilot Skill worker、CLI 的所有启动路径，统一 `.exe`、`Scripts/python.exe`、参数数组及 UTF-8 处理。
- [ ] 适配 host command 工具：当前 `/bin/sh`、`setsid` 和 POSIX 引号不能直接用于 Windows；定义 PowerShell/cmd 执行语义和取消行为。
- [ ] 将所有后端选择统一为 Windows `glfw`，Web 继续请求 `auto`；明确拒绝不兼容的显式后端，保留可诊断错误。
- [ ] 验证 SQLite、静态 Web gateway 和文件打包/解包的 Windows 构建及行为；替换依赖外部 GNU tar/zstd 命令的路径。

源码入口：[simulation/launcher.go](https://github.com/insightos-community/Semantic-Framework/blob/6d524fe4dbdfceb2029f7468619723274465c976/internal/simulation/launcher.go)、
[runtime_pack.go](https://github.com/insightos-community/Semantic-Framework/blob/6d524fe4dbdfceb2029f7468619723274465c976/internal/simulation/runtime_pack.go#L265)、
[pilot/installer.go](https://github.com/insightos-community/Semantic-Framework/blob/6d524fe4dbdfceb2029f7468619723274465c976/internal/pilot/installer.go#L65)、
[instance/runner.go](https://github.com/insightos-community/semantic-deployment/blob/ef9bbebf9a6d1f2c25350d575d242d52f29e8e42/internal/instance/runner.go)。

### AbilityFramework、Ability 与 SDK

- [ ] 为 xmake 增加 Windows/MSVC 配置并锁定依赖；移除构建时对 `date`、`python3` 命令和未转义源码路径的假设，验证带空格路径。
- [ ] 适配 `getuid/getgroups/gid_t`、Unix 执行权限位，以及 `arpa/inet.h`、`ifaddrs.h`、`ioctl` 等接口。使用 Windows 进程/网络 API；覆盖默认网卡、MAC、mDNS 和多网卡发现。
- [ ] 增加 Windows HostInfo 和统一的架构命名，替换 `uname`、`/etc/os-release`。包、bundle、host 的 OS/arch 校验必须一致。
- [ ] 为 7 个 Ability 增加原生启动描述或轻量 `.exe` 入口，直接调用随包 Python；传递 UUID、JSON 配置和 `ABILITY_ROOT`，测试参数引号。不要只修改包名或架构标签。
- [ ] 调整 Ability-SDK-Python 的父进程退出处理和自退出逻辑；Linux `prctl` 在 Windows 不生效，Windows `SIGTERM` 行为也不能当成 POSIX 优雅退出。
- [ ] 更新 `ability-scaffold`，确保新生成的 Ability 能使用相同 Windows 启动协议。
- [ ] 更新 `ability-runtime` bundle 模板、Python 可执行路径及 Windows 平台元数据；验证安装后读取的路径不含构建机绝对路径。
- [ ] 运行 Robot SDK、Skill worker、JSON-RPC、心跳、重复启动、停止失败保留和子进程清理测试。

源码入口：[subprocessmgr.cpp](https://github.com/insightos-community/AbilityFramework/blob/b5e8e443d1a8f3911c19a43a3842dcbbe92b8cb1/src/subprocessmgr/subprocessmgr.cpp)、
[discovery_utils.cpp](https://github.com/insightos-community/AbilityFramework/blob/b5e8e443d1a8f3911c19a43a3842dcbbe92b8cb1/src/util/discovery_utils.cpp)、
[Ability Bash 入口](https://github.com/insightos-community/r1pro-ability/blob/76e670f0cb8874b12fadbeb9acc9a88da7fb9b9c/abilities/r1pro-navigation/bin/ability)。

## P1：可交付的安装包与仿真闭环

### MuJoCo 与显示

- [ ] 在 Windows 测试现有 `mujoco==3.4.0` wheel、DLL、MJCF/URDF 和当前拆码垛资产。官方 MuJoCo 已支持 Windows。[官方说明](https://mujoco.readthedocs.io/en/3.4.0/programming/index.html)、[指定版本 wheel](https://pypi.org/project/mujoco/3.4.0/#files)
- [ ] 修改 Runtime 的 Pydantic 平台约束并重新生成锁文件，确保三个 Skill 所需 2.13.4 与 Windows Runtime 一致。
- [ ] 验证 `glfw` 创建隐藏窗口/离屏帧缓冲、RGB/depth、连续 Web 视频流，以及线程和上下文销毁；`headless=true` 不自动证明系统不需要可用的图形环境。
- [ ] 在 Windows 11 的实际登录桌面及显卡驱动环境验证 NVIDIA/AMD/Intel 中首批承诺支持的配置；分别记录 `GL_VENDOR`、`GL_RENDERER`、OpenGL 版本、分辨率、帧率及 CPU/GPU 使用情况。
- [ ] 单独检查 RDP、锁屏、断开显示器后的行为，明确支持边界。首版使用用户会话启动，Windows Service 图形会话另行验证。
- [ ] GPU 路线优先采用显卡厂商的 Windows OpenGL 驱动。Mesa 软件回退作为可选后续方案；不用将 Linux musl 的 libdrm/elfutils/整套 Mesa 构建链直接移植为 Windows 必选依赖。

### quick-start 与网站

- [ ] 增加 `artifacts/windows` 构建器、独立 sources/requirements 锁定、Windows manifest 和产物平台标识。
- [ ] 首版输出离线 ZIP、`install.ps1` 和原生管理入口（候选 `semanticctl.exe`）；安装到用户目录，无需管理员或 Developer Mode。
- [ ] 将现有 [installer](artifacts/runtime/installer.py)、[uninstall](artifacts/runtime/uninstall.py) 的 `fcntl`、`/proc`、`killpg`、shell launcher、`bin/python` 和平台检测拆成 Windows 实现。
- [ ] 替换 `current` 符号链接等需要特殊权限的假设；考虑显式活动版本指针、拷贝或经验证的 junction 方案。处理 reparse point、大小写、保留文件名、盘符、中文/空格、长路径和跨盘。
- [ ] 创建 venv 时引用包内 Python；安装步骤使用完整离线 wheelhouse，避免依赖系统 Python、PATH 或用户预装 pip。
- [ ] 实现 start/stop/status/doctor/logs/configure/uninstall，默认本机监听；用户需要局域网访问时才配置对应规则，保留 Windows 自身软件源和代理配置。
- [ ] Windows 正在运行的 EXE/DLL 可能锁定文件：采用停机后切换版本、校验和回滚，卸载保留数据，明确升级/数据迁移边界。
- [ ] 下载入口验证 tag、平台、大小和 SHA-256；安全解压处理 Windows 路径规则。离线包导入也执行相同验证。
- [ ] 完成 GitHub Release 发布后，再把网站选择器、中英文 README 和 PowerShell 安装指令加入 Windows 选项；不要提前公布不存在的下载地址。

## 涉及仓库与发布边界

| 仓库/组 | 首批工作 | 交付 |
| --- | --- | --- |
| Semantic-Framework、semantic-deployment | Windows 进程、锁、路径、后端与测试 | Server/CLI/Pilot/supervisor `.exe` |
| AbilityFramework | MSVC/xmake、系统与网络接口、生命周期 | EXE、必要 DLL、测试与加载报告 |
| Ability-SDK-Python、ability-scaffold | 生命周期和启动模板 | 通用 wheel/模板及 Windows 测试 |
| r1pro-ability、ability-runtime | 7 个原生入口、bundle 路径/平台 | Windows Ability 包、bundle |
| robot-sdk、robot-skill | ABI、URDF/碰撞、worker/Skill 安装测试 | 可复用 Python 包；必要时修订发布 |
| mujoco-runtime | 依赖约束、启动和 GLFW 渲染验证 | Runtime wheel、验证报告 |
| semantic-web、semantic-docs、mujoco-asset | 保持 `auto`、校验静态资产路径、更新说明 | 已验证的通用静态资源，可复用现有 Release |
| pinocchio | Windows 原生依赖链和 wheel 打包 | cp313 Windows wheel、依赖包/清单 |
| 现有 assimp、tinyxml2、qhull、zlib forks | 依赖链需要时补 Windows 构建 | DLL/开发前缀或 wheel |
| Eigen、Boost、EigenPy、Coal、URDFDOM/headers、console_bridge、OctoMap | 固定源码和构建顺序；组织目前没有这些同名独立仓库 | 可先由 Pinocchio CI 构建；需要独立维护补丁或独立 Release 时再纳入 fork |
| ruckig、mujoco forks | 优先复用上游已有 Windows wheel；有补丁/自主发布需要再增加流程 | 固定版本的 Windows 产物 |
| quick-start | 离线安装器、聚合 Release、网站 | 完整 Windows 安装包 |

构建顺序建议：基础 C/C++ 依赖 → EigenPy/Coal/URDF → Pinocchio wheel → Robot 依赖验证；
Framework/deployment 和 AbilityFramework 的平台接口可以同时推进；上述条件满足后再组装 installer。
不是每个依赖都必须新 fork，也不是每个通用 wheel/资产都必须重复发布。

## CI、验收与交付阶段

- [ ] 使用固定的 GitHub Windows 标准 runner 镜像和工具链做构建、单元测试、数学/物理测试及离线安装检查，避免依赖 `windows-latest` 漂移。[runner 规格](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [ ] 图形测试另设具有实际 Windows 桌面和显卡驱动的 runner；普通 hosted runner 成功不能代替 GPU/桌面验证。已有 9700X + RTX 5060/5060 Ti Windows 主机可作为候选验证机，具体结果以实测为准。
- [ ] CI 清理/隔离预装 Python、Conda、编译器及 DLL 搜索路径，再安装实际发行 ZIP；在不允许下载依赖的条件下验证安装。
- [ ] 从场景目录创建拆码垛项目，等待 scene running、`r1_pro_tote_gripper-1` 的 Runtime ready、7 个 Ability healthy、Pilot online、3 个 Skill installed/enabled。
- [ ] 将物理步进、Runtime ready、RGB/depth 渲染和业务任务分别报告，不以 HTTP 健康检查替代完整启动。
- [ ] 验证正常 release、重复 start/stop、失败诊断、并发安装、端口冲突、超时、进程异常退出；停止后不留自有子进程，不误杀其他 Python/应用。
- [ ] 验证带中文和空格的路径、普通用户权限、离线重装、配置/数据保留、卸载与必要回滚。
- [ ] 发布过程先创建 draft、上传并核对资产、再公开；支持网络失败后的幂等恢复。保存 sources、依赖锁、SHA256SUMS、DLL 加载报告和完整验证报告。
- [ ] 对 Linux glibc、musl、macOS 保留回归，确保平台拆分没有改变已有安装/停止行为。

| 阶段 | 完成标准 |
| --- | --- |
| A：基础库与可执行程序 | Pinocchio 数学/URDF/碰撞测试通过；Framework、supervisor、AbilityFramework 在 Windows 构建并运行 |
| B：本机项目闭环 | 三层启动就绪、7 个 Ability/3 个 Skill 正常、场景安全停止后无残留 |
| C：安装包预览 | 实际离线 ZIP 在干净 Windows 11 安装/重装/卸载通过，发布验证报告 |
| D：图形验证与正式分发 | 承诺的显卡/桌面组合通过；按需要补 MSI/EXE 包装、代码签名、开始菜单/卸载登记 |

建议首先推进 A，优先消除 Pinocchio wheel 和 Go 进程层的已确认阻塞。
当前没有充分数据给出可靠工期；原生依赖的 Windows ABI/打包试构建后再评估。
