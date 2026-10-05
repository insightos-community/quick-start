# Semantic 安装器 (TUI)

将《新版Semantic安装步骤.pdf》(Ubuntu 从 0 到 1) 转化为的终端交互式安装程序:
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
| 路径与远程 | `SEMANTIC` (工作根目录), `GITLAB` |
| 版本 | `GO_VERSION`, `BUNDLE_VER` (r1pro-mujoco Bundle 版本) |
| 镜像与密钥 | `UV_DEFAULT_INDEX` (PyPI 镜像), `SEMANTIC_ADMIN_PASSWORD` |
| 国内镜像 | `APT_MIRROR`, `GO_DL_MIRROR`, `GO_PROXY`, `NODE_MIRROR`, `NODE_VERSION`, `NPM_REGISTRY`, `GITHUB_PROXY` (见下, **全部置空即直连**) |
| 渲染后端 | `SEMANTIC_MUJOCO_GL` (`egl` 默认 / `osmesa`) |
| 服务地址 | `SERVER_HTTP`, `SERVER_WS`, `WEB_URL`, `ABILITY_PORT_FIRST/LAST`, `READINESS_TIMEOUT` |
| 仓库分支 | 11 个仓库的联调分支名 (另有 3 个 ability-framework 仓库固定按版本清单切, 不开放设置) |
| 扩展场景 (阶段 8) | `EXTENSION` (`none` 默认 / `libero` / `isaac`), `LIBERO_*` / `ISAAC_*` 设置组, `HF_ENDPOINT`, `GPU_MODE`, `CPU_ACTIONS_PER_CHUNK`, `CPU_THREADS` |

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


## 阶段总览 (对应 PDF 章节)

1. **系统依赖**: apt 国内源 / 基础工具 / Go>=1.23 (镜像) / Node 22 (镜像二进制) / uv+Python3.13 (多策略回退) / EGL 渲染库 / 镜像配置 (GOPROXY+npm) / 版本自检
2. **拉代码与资产**: 克隆 14 仓库 (含 `franka-ability`; Deployment 本地目录必须是 `semantic-robot-deployment`) / 切联调分支 / `git lfs pull` / 目录核对。选装扩展时才克隆的功能线仓库 (`semantic-simulation/isaac-runtime`) 在 `EXTENSION=isaac` 时并入
3. **构建 Server**: `.env` (管理员密码) / `make build` / `make init` / 产物核对
4. **登记 MuJoCo Runtime**: `uv sync` / `semantic runtime install` (已存在时自动加 `--replace` 重试)
5. **Robot 执行栈**: `make setup/check` / Wheel 缓存检查 / `refresh_v050_mujoco.py build --activate --stop-users` (重跑先停本工作区 Server 与占用旧 Bundle 的实例) / 自动改 `.output` 配置 (robot_runtime + leader allowlist)
6. **启动**: Server (`make run` 后台) / Web (`npm ci` + `.env` + `npm run dev` 后台) / 登录并发布三个 Robot Skill；已有本工作区同名服务会先停再拉
7. **Studio 手动联调**: 按 Enter 显示 8 条手动清单, 完成后 `m` 标记
8. **安装扩展场景** (选装, 默认不跑, 在最后一步"日常再开"之前): 设 `EXTENSION=libero` (LIBERO) 或 `EXTENSION=isaac` (BEHAVIOR/Isaac) 启用。前置检查 → 登录 Server → 拉上游源码 → 构建并安装 Runtime → 构其余五个产物 → 装场景 (限量预览) → 装机器人四件套 → 联调清单
9. **日常再开** (常驻在阶段树最底部): 先停本工作区已在跑的 Server/Web, 再后台拉起

### 阶段 8: 安装扩展场景 (LIBERO / BEHAVIOR)

默认不执行 (`EXTENSION=none`)。LIBERO 是**选装**的扩展场景, 与基础 r1pro 环境**并存**, 不改动前 7 个阶段的任何结果; 排在阶段 9「日常再开」之前, 装完正好往下走。

**启用方式**: `e` → 「扩展场景 (阶段 8)」分组 → 把 `EXTENSION` 设为 `libero`。

关键设置项:

| 变量 | 默认 | 说明 |
|---|---|---|
| `EXTENSION` | `none` | `none` 不装; `libero` 启用 LIBERO; `isaac` 启用 BEHAVIOR (Isaac Sim) |
| `LIBERO_LINE_BRANCH` | `feature/libero-behavior-vla` | libero 功能线分支。`EXTENSION=libero` 时, 七个 libero 线仓库 (framework / web / deployment / franka-ability / mujoco-runtime / robot-sdk / robot-skill) 在阶段 2.2 一律切到该分支, **优先级高于 `repo-versions.json`**——发布 Tag 上没有 LIBERO 的脚本与能力, 按 Tag 切会缺件。各仓已把功能线合并进 develop 且已推送时可改 `develop` |
| `ISAAC_LINE_BRANCH` | 空 | BEHAVIOR (isaac) 功能线分支。留空 = 按**内置逐仓表**切 (framework / robot-skill / deployment / robot-sdk / isaac-runtime 在 `feature/behavior-test`, web 与 r1pro-ability 在 `feature/behavior-isaac`, ability-runtime 留 `develop`); 填了则**统一覆盖** ISAAC_REPOS 里的每个仓库。各仓合并回主分支后填 `develop`/`main` 即可收敛。与 LIBERO 一样 **优先级高于 `repo-versions.json`** |
| `LIBERO_PACKAGE_DIR` | 空 | 六个产物的目录; 留空 = `<framework>/.output/packages/libero-current` (约 10.4 GB) |
| `LIBERO_RUNTIME_ID` | `local-libero-robosuite-1.4` | Runtime 安装 ID, 需与项目 runtime-preference 一致 |
| `LIBERO_RUNTIME_VERSION` | `0.4.0-dev.0` | 决定产物 1 的文件名 |
| `LIBERO_SCENES` | `libero-spatial-0,libero-spatial-7` | 逗号分隔, 仅对这些场景生成预览 |
| `LIBERO_UPSTREAM_DIR` | 空 | 上游 LIBERO 源码; 留空按 `sources.lock.yaml` 拉取并校验 commit |
| `LIBERO_PROJECT_ID` | 空 | 安装目标项目; 留空自动取 development 项目 |
| `LIBERO_ROBOT_ID` | 空 | 受管 Robot; 留空自动取一台 `franka_panda` |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 国内官网不可达, 用镜像 (仅构建模型包时用) |
| `GPU_MODE` | `auto` | `auto` 按本机能力自动判定 (有 CUDA 走 GPU, 否则 CPU 自动调优); `gpu` 强制按独显装; `cpu` 强制按 CPU 装 (便于复现无显卡现场) |
| `CPU_ACTIONS_PER_CHUNK` | `10` | 走 CPU 推理时把一个预测块的前 N 步连续执行, 摊薄单次推理成本。留空 = 不开启 (保持 checkpoint 原生的 1)。独显主机不使用该值 |
| `CPU_THREADS` | 空 | **覆盖阀门, 一般不用填**。留空 = 由 Ability 按本机拓扑自动探测 + 启动标定 (推荐); 填了则固定线程数并跳过标定 (写入 `SEMANTIC_VLA_THREADS`), 仅在自动结果不合适时使用。独显主机不使用该值 |

**为什么 `LIBERO_SCENES` 一定要限制**: 场景包内含 **130 个任务 / 6500 个初态**。登记本身只要 3 秒, 但每个初态预览都要启动 Runtime、恢复初态、跑 5 个仿真步再渲染——不限量会对全部 6500 个初态逐一出图, 是整条链路最慢的一步。

**重跑是安全的, 只补缺的部分**: 五个构建步骤 (8.4/8.6/8.7/8.8/8.9) 在产物已存在于 `LIBERO_PACKAGE_DIR` 时自动 skip; 8.5 在 Runtime 已登记过同 ID 时跳过安装, 只做 `doctor` 校验而不覆盖。8.3 拉取上游源码、8.10/8.11 安装这三步不会自动跳过, 正常重跑即可 (安装器自身按版本与摘要判重)。

**装完不等于能用**: 阶段 8.11 只完成"装", 最后的绑定必须到 Web 里做——①「添加兼容场景」把场景加进项目 (安装只注册到场景目录, 不会自动进项目); ②「机器人与模型配置」为 `franka_panda` 绑 Ability 与模型。**不绑的话 Ability 会停在 `Standby` (`abilityPort: 0`) 直到超时, Robot 一直 `interrupted`**。步骤 8.12 会把这份清单打在日志里。

**无独显机器 (`GPU_MODE=auto` 判定为 `cpu`, 或强制 `cpu`)**: 模型包与绑定**始终声明 `device=cuda`**, 以保持同一份包在独显与无显卡机器上都能用; 运行期由 Ability 按本机能力收敛, 并如实上报 (`device: cuda` / `effective_device: cpu`), 不是静默行为。

CPU 上的耗时由三条杠杆决定, 都不改模型:

- **等待策略**: 框架在拉起受管实例时无条件关闭 OpenMP 自旋等待 (`KMP_BLOCKTIME=0` / `OMP_WAIT_POLICY=PASSIVE`)。这是效果最大的一条 (同机重载下交错复测约 3 倍), 对独显机器无害, 运维已显式设置的值不被覆盖。
- **推理线程数**: 由 Ability 按本机拓扑 (P 核 / E 核 / 低速核) 探测、扣掉留给同机仿真与渲染的余量, 再用启动标定微调, 结果随绑定摘要上报 `cpu_threading`。越过快速核数会出现 2–4 倍塌陷, 所以必须收敛; 在快档内则只差约 15%。**默认 `auto`**——安装时定死会在换机器或同机负载变化时翻车, 所以设置项 `CPU_THREADS` 只是覆盖阀门 (阶段 3.1 与 8.1 会把探测到的核数与将采用的线程数打进日志, 现场也能用 `SEMANTIC_VLA_THREADS` 临时固定)。
- **动作块摊薄** (`CPU_ACTIONS_PER_CHUNK`, 默认 10): 把同一预测块的前 N 步连续执行, 每控制步从约 2.5 s 降到亚秒级。这会改变控制语义 (开环执行 N 步), 因此只在判定为 CPU 推理时开启, 独显主机保持 checkpoint 原生行为。

首次冷加载模型需数分钟, 若卡在就绪超时, 把 `READINESS_TIMEOUT` 填 `8m`。渲染走 Mesa EGL 正常。表现明显慢于独显, 适合验证与调试; **默认路径仍按独显设计**。

> 阶段 8 是**源码编译**路径, 面向要改组件版本的开发者。预编译入口 (`install.sh`) 的扩展场景
> 是**旁挂**设计 (独立清单 + `semanticctl extension` + 独立通道), 见 [docs/extensions.md](docs/extensions.md)。
> 目前只落地了只读层 (`extension list/show/verify`): 它下载清单与产物、逐件核对 sha256 与 size,
> 不落地安装。`install`/`remove` 尚未实现, 调用会明确报错并指向设计文档。

## 行为说明

- **状态持久化**: 步骤状态存于 `installer-status.json`, 重开程序续跑。
- **skip 检查**: 已满足的步骤 (如 Go 已 >= 1.23) 自动跳过; 单步 Enter 强制执行。
- **前置检查**: 运行阶段 6/7/8/9 时若前置阶段未完成会弹确认。
- **sudo**: 需要密码时自动临时切换到真实终端 (TUI 让位), 输入密码后返回, 输出仍回灌日志面板。
- **后台服务**: Server/Web 以独立进程组启动, 日志在 `$SEMANTIC/.tui-logs/`, 健康检查通过后步骤标记完成; `L` 随时看日志, `x` 停止。
- **失败即停**: 某步失败后清空队列, 修复后重跑该步或整段。
- 校验命令 (`test -f ...` 等) 在主命令成功后自动执行, 结果计入步骤状态 (`!` 警告 / `✗` 失败)。

## GitLab 凭证助手 (g 键)

clone/pull 需要认证时, 按 `g` 打开凭证助手, 两种方式获取并自动保存凭证:

| 方式 | 流程 | 前置条件 |
|---|---|---|
| **OAuth 登录** (推荐) | 首次: TUI 显示要填的表单值(Name/Redirect URI/Scopes) → 浏览器打开应用页创建 → 回 TUI 粘贴 ID/Secret 自动保存 → **立即**跳转授权同意页 → 点一下“授权” → 令牌自动获取 | 无 (首次在 TUI 内引导完成) |
| **PAT 粘贴** | 打开**预填**名称+scopes 的 PAT 创建页 → 选过期时间 → 点“创建” → 点页面“复制”按钮 → **TUI 自动从剪贴板读取 Token**(需 wl-paste/xclip/xsel 任一) → 自动保存验证 | 无 |

- PAT/应用页面路径会**自动探测**新旧两种路由(`/-/profile/*` 与 GitLab 17+ 的 `/-/user_settings/*`);浏览器仍 404 时日志会给出备用 URL 和无参数页面,也可在设置里固定 `PAT_PAGE_PATH` / `APPS_PAGE_PATH`

说明:
- GitLab 的 OAuth 授权码流程必须有“已注册的应用”(这是与 Google 不同的地方:Google 的应用由开发者预注册,你只见同意页)。首次注册由 TUI 引导完成;**应用不是个人专属,团队可共享同一组 ID/Secret** —— 管理员注册一次,其他人填同一组即可直接进“一键授权”。
- 注册后每次登录: `g` → `o` → 浏览器点一下“授权” → 回调自动取令牌,全程无复制粘贴。

- 令牌写入 `git credential store`(仅作用于该 GitLab 域, `~/.git-credentials`, 权限 0600), 之后所有 clone/pull/lfs 免密
- 保存后自动用 `git ls-remote` 验证; `g → c` 可随时清除
- clone 步骤遇认证失败(`could not read Username` / `Authentication failed` 等)会在日志中提示按 `g`

## sudo 鉴权 (命令行方式, 无需切终端)

sudo 步骤默认走 **TUI 内鉴权**: 弹出掩码密码框, 密码通过 `sudo -S` 从 stdin 传给子进程;
仅保存在本进程内存 (不写盘), **一次输入全程复用**, `P` 键随时清除。密码错误时自动清除并在重跑时重新询问。

- 设置 `SUDO_AUTH`: `tui` (默认, 推荐) / `terminal` (临时退出 curses 到真实终端输密码)
- 无头模式 (`--run-all` 等) 自动回退 terminal 模式
- 后台脚本仍以独立进程组运行, 不占用控制终端, 日志照常进入中间面板

## 生成的文件

- `installer-settings.json` 环境变量设置
- `installer-status.json` 步骤状态
- `semantic-env.sh` 供终端 source 的环境脚本
- `$SEMANTIC/.tui-logs/{server,web}.log` 后台服务日志
