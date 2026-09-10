# Semantic 安装器 (TUI)

面向 Ubuntu 源码工作区的终端交互式安装程序：
左侧阶段/步骤树、中间实时日志、可设置环境变量、分阶段逐步执行。

**零依赖**, 仅需 Python 3 标准库 (`curses`)。

## 启动

```bash
python3 semantic_installer.py            # TUI 模式
python3 semantic_installer.py --list     # 只列出全部阶段与步骤
python3 semantic_installer.py --run-all  # 无头模式顺序执行全部
python3 semantic_installer.py --stage 1 --stage 2   # 无头模式执行指定阶段
python3 semantic_installer.py --reset-status        # 清空步骤状态
```

## 界面与按键

```
┌ 左: 阶段/步骤树 ──────┬ 中: 实时日志 ─────────────────────────┐
│ 1 系统依赖 0/6 ·      │ 14:32:01 $ sudo apt update            │
│   1.1 · 基础工具      │ ...                                   │
└───────────────────────┴───────────────────────────────────────┘
```

| 按键 | 作用 |
|---|---|
| `↑/↓` `j/k` | 移动选择 |
| `Enter` | 运行: 选中**阶段**=整段顺序执行; 选中**步骤**=单步(跳过 skip 检查强制执行) |
| `a` | 从阶段 1 连续执行所有 (尊重 skip 检查, 手动步骤跳过) |
| `A` | 从当前选中项连续执行到末尾 |
| `v` | 仅运行当前阶段/步骤的校验命令 |
| `e` | **环境变量设置** (见下), 保存并生成 `semantic-env.sh` |
| `L` | 查看选中服务步骤的日志尾部 |
| `x` | 停止本工具启动的所有后台服务 |
| `m` | 标记手动步骤 (7.1) 完成/取消 |
| `c` / `C` | 中止当前运行 / 清空日志 |
| `r` | 重置全部步骤状态 |
| `Tab` | 焦点在 步骤树/日志 间切换; 日志焦点下 `PgUp/PgDn/Home/End` 滚动 |
| `?` | 帮助 (含原文档的坑点摘要) |
| `q` | 退出 (询问是否停止后台服务) |

## 可配置的环境变量 (e 键)

| 分组 | 变量 |
|---|---|
| 路径与远程 | `SEMANTIC` (工作根目录), 远端主机配置 |
| 版本 | `GO_VERSION`, `BUNDLE_VER` (r1pro-mujoco Bundle 版本) |
| 镜像与密钥 | `UV_DEFAULT_INDEX` (PyPI 镜像), `SEMANTIC_ADMIN_PASSWORD` |
| 国内镜像 | `APT_MIRROR`, `GO_DL_MIRROR`, `GO_PROXY`, `NODE_MIRROR`, `NODE_VERSION`, `NPM_REGISTRY`, `GITHUB_PROXY` (见下, **全部置空即直连**) |
| 渲染后端 | `SEMANTIC_MUJOCO_GL` (`egl` 默认 / `osmesa`) |
| 服务地址 | `SERVER_HTTP`, `SERVER_WS`, `WEB_URL`, `ABILITY_PORT_FIRST/LAST` |
| 仓库分支 | 13 个组件仓库的清单版本 |

保存于 `installer-settings.json`; 同时生成 `semantic-env.sh`, 可在任意终端 `source semantic-env.sh`。

## 国内源支持 (自动下载安装依赖)

| 环节 | 默认国内源 | 步骤 |
|---|---|---|
| apt 软件源 | `https://mirrors.aliyun.com/ubuntu` (可换清华 `https://mirrors.tuna.tsinghua.edu.cn/ubuntu`) | 1.0 自动替换 `archive/security.ubuntu.com`, 每个源文件留 `.bak-orig` 备份 |
| Go 官方包 | `https://mirrors.aliyun.com/golang` (或 `https://golang.google.cn/dl`) | 1.2 从镜像下载 tarball |
| Go 模块 | `GOPROXY=https://goproxy.cn,direct` | 1.6 `go env -w` 持久化 + `make build` 注入 |
| Node.js | `https://cdn.npmmirror.com/binaries/node` 二进制 | 1.3 下载解压 `/usr/local` (默认 22.14.0, 置空 `NODE_VERSION` 自动解析 latest-v22.x; 置空 `NODE_MIRROR` 改走 NodeSource) |
| npm registry | `https://registry.npmmirror.com` | 1.6 写入 `~/.npmrc`; 6.2 `npm ci --registry` 双保险 |
| uv 安装 | astral.sh → `GITHUB_PROXY` 代理 → pip 国内源 | 1.4 三策略自动回退, 任一成功即继续 |
| Python 解释器 (uv) | `UV_PYTHON_INSTALL_MIRROR` (由 `GITHUB_PROXY` 拼接) | 1.4 / 4.1 / 5.3 注入, 加速 `uv python install` 与 `uv sync` |
| PyPI (uv sync) | `UV_DEFAULT_INDEX` 阿里云 (备用清华) | 4.1 / 5.3 |

`GITHUB_PROXY` 示例: `https://mirror.ghproxy.com` (GitHub 代理前缀, 用于 uv 二进制与 python-build-standalone 解释器加速; 代理域名失效时换一个或置空直连)。


## 阶段总览

1. **系统依赖**: apt 国内源 / 基础工具 / Go>=1.23 (镜像) / Node 22 (镜像二进制) / uv+Python3.13 (多策略回退) / EGL 渲染库 / 镜像配置 (GOPROXY+npm) / 版本自检
2. **拉代码与资产**: 克隆 13 个组件仓库 (Deployment 本地目录必须是 `semantic-robot-deployment`) / 切联调分支 / `git lfs pull` / 目录核对
3. **构建 Server**: `.env` (管理员密码) / `make build` / `make init` / 产物核对
4. **登记 MuJoCo Runtime**: `uv sync` / `semantic runtime install` (已存在时自动加 `--replace` 重试)
5. **Robot 执行栈**: 从源码构建并复制 AbilityFramework / ability-py / ability-scaffold / Wheel 缓存检查 / `refresh_v050_mujoco.py build --activate --stop-users` (重跑先停本工作区 Server 与占用旧 Bundle 的实例) / 自动改 `.output` 配置 (robot_runtime + leader allowlist)
6. **启动**: Server (`make run` 后台) / Web (`npm ci` + `.env` + `npm run dev` 后台) / 登录并发布三个 Robot Skill（默认用户名 `admin`，密码 `test-admin-pass`；如已修改，使用 `.env` 中的 `SEMANTIC_ADMIN_PASSWORD`）；已有本工作区同名服务会先停再拉
7. **实操示例**: 7.1「拆码垛场景测试」，按 Enter 查看通过对话进行场景任务规划的示例提示词，完成后 `m` 标记
8. **日常再开**: 先停本工作区已在跑的 Server/Web, 再后台拉起

步骤 7.1 提示词可使用如下：

> 将来源托盘当前最上面一层周转箱，搬到目标托盘对应位置，放稳并恢复行走姿态。给出计划。

## 行为说明

- **表单与故障日志**: 阶段 1/2 和 3.1 右侧显示配置或拉取清单,不滚动展示命令标准输出。
  `Tab` 切到右侧后可翻页查看仓库状态；每次步骤执行自动保存 `.tui-logs/step-<步骤号>-*.log`,
  包含脱敏后的命令/输出/错误,失败时显示原因与日志路径。
  构建工具输出的 ANSI 颜色、光标和超链接控制码会在界面及步骤日志中清理，无需安装额外字体。
  阶段 5 的源码构建须完成产物复制和校验才会标记成功；Wheel 检查压缩包完整性及元数据，
  AbilityFramework 检查 `--version` 能否执行。复制或校验失败会停止后续步骤，不接受 LFS 指针充当产物。
- **拉取/构建工作区**: TUI 执行 2.1 前默认填入当前 quick-start 仓库路径,可直接确认或输入其他绝对路径。
  目录不存在时再询问是否创建; 取消会停止队列。确认后保存 `SEMANTIC` 到设置和环境脚本,
  后续步骤统一使用该目录。同次运行重试时沿用已确认目录; 无头模式使用已配置路径。
- **状态持久化**: 步骤状态存于 `installer-status.json`, 重开程序续跑。
- **skip 检查**: 已满足的步骤 (如 Go 已 >= 1.23) 自动跳过; 单步 Enter 强制执行。
- **前置检查**: 运行阶段 6/7/8 时若前置阶段未完成会弹确认。
- **sudo**: 默认 TUI 掩码输入，安装前先验证；可设置 `SUDO_AUTH=terminal` 切换到真实终端。
- **后台服务**: Server/Web 以独立进程组启动, 日志在 `$SEMANTIC/.tui-logs/`, 健康检查通过后步骤标记完成; `L` 随时看日志, `x` 停止。
- **失败即停**: 某步失败后清空队列, 修复后重跑该步或整段。
- **LFS 与源码产物**: 克隆/切换版本跳过自动 smudge,2.3 排除所有目录中的 `AbilityFramework`、
  `ability_py-*.whl`、`ability_scaffold-*.whl`,其余场景资产和第三方 Wheel 正常下载。
  2.3 只校验第三方资产与 bundle 配置,这三类产物由 5.1/5.2 源码构建后校验；不自动清理已下载文件。
- **Wheel 下载**: `RUNTIME_WHEEL_SOURCE=auto` 默认先检查缓存，再从 `UV_DEFAULT_INDEX`
  通过 `pip download` 下载当前版本锁定的包，校验完整文件名、大小与 SHA-256。
  特殊的 TinyXML2/urdfdom Wheel、包源缺失或不同构建回退到精确 LFS 对象。
  三次包源失败后本次剩余项直接走 LFS，避免反复等待；表单显示当前文件和进度，详细输出写日志。
  `lfs` 模式跳过包源，`offline` 模式只校验运行时缓存（不影响场景资产的 LFS 拉取）。
  本地已修改/损坏的非指针文件不会被覆盖，请先检查并移走后重试。
- 校验命令 (`test -f ...` 等) 在主命令成功后自动执行, 结果计入步骤状态 (`!` 警告 / `✗` 失败)。

## 仓库认证

根据所选远端配置 Git 的 SSH 或凭据助手。公开仓库不应要求开发者获取组织内部令牌。
界面中的 `g` 为原托管环境的认证入口，并非通用的 GitHub 登录入口。
凭据、本地设置与 OAuth 应用信息不要提交；共享日志前仍需复核敏感内容。

## sudo 鉴权

sudo 步骤默认走 **TUI 内鉴权**: 弹出掩码密码框, 密码通过 `sudo -S` 从 stdin 传给子进程;
使用 Linux 账户登录密码，而非 Web 密码。新输入先进行一次验证，失败或超时不启动安装、
不缓存密码，并在表单显示原因；不会自动发送三次相同密码。验证通过后仅保存在本进程内存
(不写盘)，后续步骤复用，`P` 键随时清除。中文 sudo 错误也会显示在失败表单。

- 设置 `SUDO_AUTH`: `tui` (默认, 推荐) / `terminal` (临时退出 curses 到真实终端输密码)
- 无头模式 (`--run-all` 等) 自动回退 terminal 模式
- 后台脚本仍以独立进程组运行, 不占用控制终端, 日志照常进入中间面板

## 生成的文件

- `installer-settings.json` 环境变量设置
- `installer-status.json` 步骤状态
- `semantic-env.sh` 供终端 source 的环境脚本
- `$SEMANTIC/.tui-logs/{server,web}.log` 后台服务日志
