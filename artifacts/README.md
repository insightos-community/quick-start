# Semantic 产物发布与一键部署

这是与源码 TUI 安装器独立的**预编译产物部署**入口。安装端不克隆 Git、不运行
Go/xmake/npm 构建；从构建机提取产物，在目标机初始化独立实例。

已接入阿里云 OSS：实际发布地址、仓库外凭据配置、按版本上传和限时安装入口见 [OSS.md](OSS.md)。
当前发布对象为公开读、授权写，中国用户可直接通过 OSS 的 curl 入口安装，无需密钥或下载票据。

介绍与安装入口：<https://semantic.insightos.cn/>。静态站点源码、Nginx 配置和维护/回滚说明见 [site/README.md](site/README.md)。

## 局域网、安装进度与桌面入口

新安装并开放 Web 局域网访问：

```bash
curl -fsSL https://semantic.insightos.cn/install.sh | bash -s -- --install-system-deps
```

新安装 Web 默认监听 `0.0.0.0:3000`，同时接受 `127.0.0.1` 与本机网卡 IPv4 的连接，无需重复绑定。
`--lan` 仍作为兼容选项；可用 `--web-host <本机网卡IP> --web-port 3001` 指定网卡及端口，
或 `--web-host 127.0.0.1` 限制为仅本机。API/WS 继续本机监听，通过 Web 网关统一代理。
不会自动修改防火墙/云安全组：只向可信局域网开放 Web 端口（默认 3000），不要公开 API/WS/Runtime。
所有网卡也可能包含公网网卡；公网请使用 HTTPS 反向代理与访问控制。HTTP 不加密。

**已经安装的实例（包含 .4 版本）不需要重新部署数据库和运行包**，可以更新管理工具并开启局域网：

```bash
curl -fsSL https://semantic.insightos.cn/install.sh | bash -s -- \
  --configure-existing --dir "$HOME/.local/share/semantic" --lan --desktop-shortcut
```

此模式仍下载并校验新版本完整归档，但只安装 `bin/semantic-manager`、更新 `semanticctl`、监听配置和快捷入口。
保留业务版本、原始发布包、数据库、密码与运行环境；保存旧 install.json 到 configs 下。
需要变更监听时只重启 Web，已运行 Server 不被重启。不要将业务升级与管理工具更新混为一谈。
已有实例不传网络参数会保留原监听配置；切换到本机 + 局域网请显式加 `--lan`。
此模式也支持 `--web-port 3001` 修改 Web 端口，冲突会在停止原 Web 前被拒绝。
自动化可加 `--yes`；`--no-start` 不启动服务（变更监听时仍停止原 Web）。

安装器显示真实下载字节进度、SHA-256/解包阶段、任务清单和各阶段耗时。
交互终端采用单页任务表，原位刷新；成功后清理当前视口，只显示欢迎表单，不清除 shell 历史滚动区。
失败时保留任务状态与日志位置，重定向输出不刷新或清屏。
任务条百分比是已完成任务比例，不代表预计剩余时长。窄屏按字符宽度换行；非 TTY 不输出 ANSI 控制序列。
欢迎页分为访问、管理、环境、提示四区：青色标题/命令、绿色成功、黄色凭据/注意事项、灰色辅助标签。
终端欢迎页仅显示文字，不再渲染 ASCII 图标；标准 80×24 终端显示紧凑欢迎表单。
`NO_COLOR=1` 禁用配色，`TERM=dumb` 禁用颜色和重绘。
密码只向 `/dev/tty` 输出，不写 stdout/stderr 管道或安装日志；没有控制终端时提示密码文件位置。
注意屏幕录制仍可能记录终端显示，分享截图前请遮挡密码。

自动检测桌面；`--desktop-shortcut` 显式创建，`--no-desktop-shortcut` 跳过。
快捷方式使用原始 PNG，直接通过 `xdg-open` 打开本机 Web；不携带账号密码，也不会自动启动服务。
支持 XDG 本地化桌面目录与应用菜单，多实例使用不同文件名。GNOME 等环境可能需要右键“允许启动”。
无桌面/无 xdg-open 时提示跳过，不影响安装；卸载只删除本实例创建且未被用户修改的快捷方式。
格式遵循 [Desktop Entry 规范](https://specifications.freedesktop.org/desktop-entry/latest-single/)。

完成页提供环境变量与启停指引，不擅自修改 shell 启动文件：

```bash
export SEMANTIC_HOME="$HOME/.local/share/semantic"
export PATH="$SEMANTIC_HOME/bin:$PATH"
semanticctl start
semanticctl status
semanticctl stop
semanticctl welcome  # 再次查看地址、环境变量指引及终端密码
```

若需持久生效，将 export 两行加入 `~/.bashrc` 或 `~/.zshrc`。当前不配置开机自启动。

## 默认安装（本机与局域网）

```bash
curl -fsSL https://semantic.insightos.cn/install.sh | bash -s -- --install-system-deps
```

当前制品目标：Linux x86_64、glibc >= 2.28，完整 Server + Web + Native MuJoCo +
R1 Pro Bundle。应用程序采用静态 ELF，glibc 门槛来自 uv/Python/Wheel 运行栈；
满足门槛不等于所有发行版都已通过产品验收。实测范围见 [PORTABILITY.md](PORTABILITY.md)。
ARM64、Alpine/musl 完整运行栈及 Windows/macOS 尚不支持。

入口形式参考 [Hermes 安装脚本](https://hermes-agent.nousresearch.com/install.sh)：
支持管道启动、参数化路径和非交互安装；安装过程中从 `/dev/tty` 读取确认，
不会把下载脚本的 stdin 当作用户输入。此实现没有直接执行参考脚本。

## 目录结构

```text
artifacts/
├── install.sh                    # 可托管的 curl | bash 入口
├── site/                         # 介绍页、静态站点容器与边缘反向代理配置
├── build_release.py              # 构建机：提取、补齐、验证并打包
├── build_native.py               # 独立构建静态 AbilityFramework 与 Go 程序
├── test_container.py             # 一次性 Debian/Fedora 容器部署测试
├── smoke_release.py              # 独立目录/端口的真实安装与管道重装测试
├── smoke_uninstall.py            # 新实例：卸载保留数据、重装、管道彻底删除验证
├── runtime/installer.py           # 安装/初始化/semanticctl 实现
├── runtime/uninstall.py           # 卸载逻辑源码，同步内嵌于 install.sh，离线可用
├── gateway/main.go                # Web 静态文件 + HTTP/WS 反向代理
├── channels/stable.json           # 当前内部快照的下载路径、SHA256、大小
└── releases/<version>/linux-x86_64/
    ├── manifest.json             # 下载元数据；路径相对整个 artifacts/ 站点根
    ├── release.json              # 组件版本、源码提交、平台和分发边界
    ├── semantic-<version>-linux-x86_64.tar.gz
    └── semantic-<version>-linux-x86_64.tar.gz.sha256
```

归档内部按组件存放，不打包完整工作区：

```text
bin/                semantic-server / semantic / semantic-pilot / Web gateway / uv
web/                Vite production 静态文件（不用 npm run dev）
robot-bundles/      AbilityFramework、Pilot、七类 Ability ZIP、Wheel、部署模板
robot-skills/       grasp-object / semantic-navigation / place-object 发布 ZIP
runtime-packs/      Native MuJoCo 正式 Runtime Pack（Wheelhouse、锁、场景、许可）
assets/mujoco/      受版本控制的模型、网格、场景、资产目录
defaults/          来自源码模板的干净 Server 配置（不读取运行中配置）
release.json        组件版本及来源提交
native-linkage.json  应用 ELF 静态链接检查与 uv 的直接 glibc 符号基线
files.json          每个产物的 SHA256
installer.py        初始化逻辑
```

不提取 `.env`、用户数据库、Project/Task/会话、Pilot 凭据、运行日志、`.git`、
`node_modules`、现有 `.venv` 或指向构建机的 Python 符号链接。
Robot 使用 Python 3.13；当前 Native MuJoCo Pack 使用 Python 3.10.19。
二者在目标目录分别建环境，不能直接搬运 Conda 或已安装的 venv。

## 在构建机生成发布包

先用现有 TUI 完成源码构建（至少 3.2、5.1～5.4），准备好 uv、Go、Node/npm、
tar/zstd、readelf、xmake、C/C++ 静态库与 musl-gcc（Ubuntu 构建机对应 musl-tools）。
Web 有已安装依赖时直接构建 production；否则先在 Web 仓执行 `npm ci`。

```bash
python -B artifacts/build_native.py
uv run --no-project --with PyYAML python artifacts/build_release.py \
  --version 0.5.0-dev.20260910.3
```

`build_native.py` 在 `.build/` 的独立源码副本构建 AbilityFramework，开启 `fwk-static`，
强制第三方库从源码静态构建，不修改原仓库的 xmake 配置或现有 `.output`。
Go 程序保留 CGO，使用 `CC=musl-gcc`、`musl,netgo,osusergo` 标签及外部静态链接；
包含 Server、CLI、Pilot、Robot Instance。构建日志默认保存在 `.build/native-static/`。
可用 `--component ability` 或 `--component server` 分别构建。

发布器默认读取 `.build/native-static/`，也可传 `--native-dir DIR` 提供已验证静态产物。
五个程序必须齐全，且 `readelf` 检查不得有 `PT_INTERP` 或 `DT_NEEDED`；不允许静默
回退到旧动态版本。Bundle 中的 AbilityFramework/Pilot/Robot Instance 同步替换。

构建器检查真实 LFS 文件、Wheel ZIP、三个 Skill 的精确版本与 Bundle 模板一致性。
Runtime Pack 使用 `uv.lock` 导出固定依赖，再转为不含源码路径的 Wheel-only 锁；
场景目录使用当前 Framework schema 的源码模板，避免 Runtime 仓旧 authoring
样例与当前 Server 不兼容。现有 Python 环境不会进入发布包。

相同版本目录拒绝覆盖。重建应使用新版本。`--runtime-pack FILE` 可显式复用已经
验证的 Runtime Pack；**仅在 Runtime 源码、锁和场景模板未变时使用**。
首次构建会在 `.build/native-mujoco.runtime.tar.zst` 留下可复用 Pack。
`--skip-web-build` 只适用于已生成并确认正确的 `semantic-web/dist`。

当前 `channels/stable.json` 是内部开发快照通道，不意味着已发布正式稳定版本。

## 本地一键安装

```bash
bash artifacts/install.sh \
  --package artifacts/releases/0.5.0-dev.20260910.3/linux-x86_64/semantic-0.5.0-dev.20260910.3-linux-x86_64.tar.gz \
  --dir "$HOME/.local/share/semantic" \
  --yes
```

归档旁边的 `.sha256` 必须保留，也可显式传 `--sha256 HASH`。
默认询问路径/创建确认；CI 或无人值守使用 `--yes`。默认目录为
`$HOME/.local/share/semantic`，不覆盖其他用途的非空目录。

入口需要 bash、Python 3.10+，在线管道还需要 curl；请先由系统包管理器准备。
缺少系统依赖时会报清单。允许安装器调用系统包管理器/sudo 时，加 `--install-system-deps`。
启用该选项后，安装器先检查 sudo 授权，再进入动态进度面板。需要密码时通过
`/dev/tty` 显示授权表单，由 sudo 直接读取当前 Linux 用户密码（不回显、不写日志），
支持 `curl | bash`。root 或已有有效授权会自动跳过提示。授权限时 180 秒。
后续命令使用 `sudo -n`，不再隐藏等待密码；授权过期会明确失败，可先运行 `sudo -v` 后重试。
`--yes` 仅跳过安装确认，不代替 sudo 授权；无人值守需预先配置可用权限或由管理员预装依赖。
日志在等待授权及每条依赖命令执行前即写入，进度面板显示当前命令和耗时。
支持 apt-get、dnf（或 yum）、pacman、zypper，根据发行版 ID/ID_LIKE 选择。
安装的是证书、zstd、C++/OpenMP 运行库和 EGL/Mesa；静态应用不再要求系统 yaml-cpp、
libuv、OpenSSL。默认渲染后端为 EGL，不把 OSMesa 作为强制依赖。
不传该选项就不会执行系统安装；不会改写镜像源、关闭签名验证或自动执行全系统升级。
Arch 请先由管理员保持系统更新；脚本使用 `pacman -S --needed`，不执行 `-Sy` 或 `-Syu`。
未知发行版允许管理员手动满足依赖，但拒绝猜测包管理器后自动修改系统。

可以用 `--http-port`、`--ws-port`、`--web-port`、`--runtime-port` 避开现有服务。
默认依次为 8080、8081、3000、8090。安装器不自动停止其他进程来腾出端口。
`--no-start` 只初始化而不启动 Server/Web；Runtime 安装仍执行隔离场景 smoke。

## HTTPS 一键入口

把 `install.sh`、`channels/`、`releases/` 按上述相对结构放到自己的可信 HTTPS
静态站点（例如内部对象存储或下载站），然后：

```bash
curl -fsSL https://YOUR-HOST/semantic/install.sh | \
  bash -s -- --base-url https://YOUR-HOST/semantic --yes
```

固定版本加 `--version 0.5.0-dev.20260910.3`；也可提前设置
`SEMANTIC_DOWNLOAD_BASE`，省略 `--base-url`。`YOUR-HOST` 是通用托管示例；默认地址已配置为
阿里云 OSS，公开访问及可选私有票据流程见 [OSS.md](OSS.md)。本地 HTTP 测试需显式 `--allow-http`，默认拒绝 HTTP
及 HTTPS 降级重定向。服务器需要按普通文件返回制品，当前入口不处理 代码托管平台登录页。

引导阶段先校验归档 SHA256，拒绝越界路径、符号链接、特殊文件和超大归档，
解包后再执行安装逻辑。安装逻辑还验证逐文件清单。
SHA256 防止损坏，不替代签名：HTTPS 站点和引导脚本必须可信。高信任环境可先下载、
审阅入口，再用独立可信渠道获取的 `--sha256` 固定制品。

## 安装与初始化结果

```text
<install-dir>/
├── releases/<version>/   不与源码工作区混用的产物与重建 Python 环境
├── current -> releases/<version>
├── bin/semanticctl       本实例管理入口
├── configs/             初始化的 Server、Agent、Skill 配置及 secrets.json
├── data/                新数据库（不复制原实例数据）
├── runtimes.d/          CLI 验证通过后登记的 Native MuJoCo
├── runtime-packs/       解包后的正式 Runtime Pack
├── runtime-envs/        目标机独立 MuJoCo venv
├── content/             场景目录
├── python/              uv 按需下载的 Python
├── run/                 PID 身份与安装锁
└── logs/                每次安装和 Server/Web 日志
```

流程：SHA256 → 平台/依赖检查 → 提取到安装目录 → Robot venv 重建/导入检查 →
`semantic init` → 随机管理员密码 → 正式 Runtime Pack 安装与 smoke →
Server/Web 健康检查 → 登录并发布三个 Robot Skill。

新安装 Web 默认监听全部 IPv4 网卡：访问 `http://127.0.0.1:3000` 或 `http://局域网IP:3000`。公网访问建议 SSH 隧道或
管理员配置的 HTTPS 反向代理；不默认向公网暴露。模型仍为 mock，真实模型服务和
Token 需要在 Web 系统设置中配置。不会创建业务 Project、下发 Robot Task 或自动
运行抓取动作。Runtime 安装的 smoke 是临时仿真场景，结束后由 CLI 清理。

用户名 `admin`；随机密码在 `<install-dir>/configs/secrets.json`（0600），不在
安装日志中打印，不复用开发默认密码。同版本重跑保留密码、配置和数据库。

```bash
"$HOME/.local/share/semantic/bin/semanticctl" status
"$HOME/.local/share/semantic/bin/semanticctl" start
"$HOME/.local/share/semantic/bin/semanticctl" doctor
"$HOME/.local/share/semantic/bin/semanticctl" logs
# 先在 Studio 停止场景/Robot，再停 Server/Web：
"$HOME/.local/share/semantic/bin/semanticctl" stop
```

目前提供本用户后台进程管理，不自动注册 systemd/开机启动。PID 校验包含 Linux
进程启动时间，不会因 PID 重用误杀其他进程。跨版本升级/数据库迁移暂不自动执行：
使用新安装目录，经验证后再制定数据迁移方案。同版本未完成安装可重新执行；日志
保留失败原因，不进行破坏性数据库重置。

## 卸载

使用新版 `install.sh`，不需要下载或指定发布包；旧版 `.2/.3` 托管实例也可使用。
`.11` 起也可使用 `semanticctl uninstall`（支持 `--dry-run`、`--yes`、`--purge`）。
旧管理工具没有此子命令时，直接用最新版 `install.sh --uninstall`（也接受 `uninstall` 子命令），
无需先更新业务包或启动服务。

```bash
# 只检查目录、进程并显示计划，不停止或删除；仍生成审计日志
bash artifacts/install.sh --uninstall --dir "$HOME/.local/share/semantic" --dry-run

# 默认保留用户配置、数据库和日志；交互确认后停止 Server/Web 并卸载程序
bash artifacts/install.sh --uninstall --dir "$HOME/.local/share/semantic"

# 永久删除整个实例，包括所有用户数据；非交互场景需同时显式传 --yes
bash artifacts/install.sh --uninstall --dir "$HOME/.local/share/semantic" --purge --yes

# 在线入口也可卸载，下载的只有入口脚本，不再下载几百 MB 制品
curl -fsSL https://semantic.insightos.cn/install.sh | \
  bash -s -- --uninstall --dir "$HOME/.local/share/semantic" --yes
```

默认删除 `releases/`、`python/`、`runtime-envs/`、`runtime-packs/`、`bin/` 和 `current`
链接。保留 `configs/`、`data/`、`logs/`、`content/`、`runtimes.d/`、Robot 实例数据及其他
非程序目录，安装状态标记为未就绪。**保留数据模式不是备份**；重要数据请另行备份。
使用原版本制品、原路径和原端口重新安装可以重建运行环境并保留密码；跨版本迁移规则不变。

卸载前请先在 Studio 安全停止场景和 Robot。卸载器检查本机可读的进程参数、程序路径和
工作目录；若发现该实例仍有 Robot/Runtime 等进程，会拒绝继续，不自动终止它们。
状态表明确显示 Server/Web 已停止或运行，以及其他占用进程，不再以 `{}` 代替状态。
若是 Bash 等终端仍停留在实例的真实目录，提示对应 PID、进程名、工作目录及 `cd ~`，
不要用 kill 代替切换目录。对于已删除工作目录（inode 链接数为 0），不再误判为实例占用，
也不会关闭该终端；仅名称以 ` (deleted)` 结尾的真实目录仍会受到保护。
仅对 PID、启动时间、实例内程序路径均匹配的 Server/Web 发送 SIGTERM；20 秒未退出
即中止，不强制杀进程。此检查不代替远程设备/远程 Runtime 的人工安全停机。

目录必须含 `.semantic-install-root` 和有效 `install.json`，由安装时的同一用户操作。
拒绝主目录、当前工作目录及其父目录、符号链接根目录、异常管理路径及目录内挂载点。
不要在实例目录内部执行卸载。删除内部符号链接不追随到外部；不卸载系统共享软件包，
不清理实例外部资源。`--purge` 删除不可由本脚本恢复。

每次卸载（包括失败与 dry-run）会在系统临时目录生成 `semantic-uninstall-*.log`，
权限 0600，并显示路径；日志位于实例外，purge 不会删掉它。需要长期留存时请另行保存。
终端显示简明失败原因，完整 traceback 只写入日志。
卸载实现内嵌于入口，单元测试校验它与 `runtime/uninstall.py` 一致，避免维护时不同步。

## 网络和分发边界

- 安装包包含应用二进制及 Python Wheel，不包含操作系统和独立 Python 解释器。
  目标机缺少 Python 3.13 / 3.10.19 时，uv 仍需要网络下载；系统包安装同样需要网络。
  因此这不是完全离线的 OS 安装介质。
- 资产清单存在 `distribution_status: internal-only` 和 `license: pending`。
  生成物明确标记为内部部署快照；公开发布前必须审查源码、第三方 Wheel、模型及
  网格的再分发许可，不能因为有 curl 安装入口就默认公开上传。
- `releases/`、`channels/` 和测试暂存目录被 Git 忽略，避免几百 MB 的制品进入源码
  提交。发布包应存放在制品仓库；当前脚本只在本机生成，不自动上传。

## 测试

```bash
python -B -m unittest discover -s tests -q
go test artifacts/gateway/main.go artifacts/gateway/main_test.go
bash -n artifacts/install.sh
# 实际安装测试：独立目录与 28180～28183 端口，最后停止测试实例
python -B artifacts/smoke_release.py \
  --package artifacts/releases/0.5.0-dev.20260910.3/linux-x86_64/semantic-0.5.0-dev.20260910.3-linux-x86_64.tar.gz \
  --port-base 28180
```

集成验证应使用全新目录和独立端口；除安装成功外，检查登录、Web 同源代理、
Runtime/场景登记、三个 Skill 精确版本及重跑保留密码。Robot 真正就绪、物理抓取
和任务执行仍需单独的产品验收，不能由“安装完成”替代。

## English installer

The standalone English entry is `artifacts/install-en.sh`. After publishing the
site files, use:

```bash
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --install-system-deps
```

For local use: `bash artifacts/install-en.sh --help`. All existing download,
installation, configuration and safe offline uninstall options are supported.
Installer-owned prompts, progress, errors, welcome output and the installed
`semanticctl` are in English; external programs retain their original output.
The artifact source remains the same OSS endpoint; language does not select a
different mirror or imply broader platform support.

Regenerate after changing the canonical installer or its runtime modules:
`python artifacts/build_english_installer.py`. Verify with `--check`.
Translations live in `artifacts/installer.en.json`; do not edit generated
`install-en.sh` directly. See [site deployment](site/README.md) for publishing.
