# 本次发布包验证

- 当前静态制品：`0.5.0-dev.20260910.11`，最新卸载/终端占用修复验收见文末；静态链接基线详见 [PORTABILITY.md](PORTABILITY.md)。
- 当前单元测试：149 项通过；.11 完整安装及 CLI 卸载在 Debian 12 隔离容器通过。Ubuntu 24.04、Fedora 42 为此前版本实测。
- 此前 .6 官网 curl 管道下载、进度、LAN 配置与交互取消验证通过；网站四档屏幕布局、复制按钮和脚本哈希通过。
- 历史 OSS 发布：`.3` 版本及安装入口上传到 insightos-artifacts / semantic 前缀；
  初次按 private 发布，签名入口真实下载、SHA256、初始化和 MuJoCo smoke 通过。
  用户随后明确授权公开读取：六个发布对象已改为 public-read，Bucket 及其他对象未改动；
  匿名入口/清单/校验文件 GET 返回 200，安装包 Range GET 返回 206 且总大小正确，curl 管道帮助命令通过。
  凭据/签名票据仅在仓库外（0600），52 个候选源码文件的实际凭据扫描通过。详见 [OSS.md](OSS.md)。
- 新版 install.sh 内嵌离线卸载器，不需要重建或下载旧制品。新增 20 项卸载测试，覆盖保留数据、
  purge、dry-run、路径/挂载点保护、活动进程拦截、PID 复用、停止超时、安装锁和管道调用。
- 完整卸载集成验证：用 `.3` 制品新建隔离实例 → 默认卸载 → 同版本重装（保留数据库与密码）
  → 管道 purge，通过。仅删除测试实例；结果与日志位于
  `.build/uninstall-smoke-zog3zn25/report.json`、`.build/uninstall-smoke-zog3zn25/smoke.log`。

以下保留上一版动态制品的历史验证记录，不代表当前下载通道：

- 历史内部版本：`0.5.0-dev.20260910.2`
- 历史文件：`releases/0.5.0-dev.20260910.2/linux-x86_64/semantic-0.5.0-dev.20260910.2-linux-x86_64.tar.gz`
- 大小：360705196 bytes（约 344 MiB）
- SHA256：`557cfb48a0d0d5068dc770d19fc52d9e10ea023a247864a581735d2b6a8dafd8`
- 环境：Ubuntu 24.04 x86_64；独立安装目录、独立端口；不是干净虚拟机测试。

## 已通过

- Python 回归测试 70 项，包括校验损坏、越界归档、符号链接、管道参数、密码文件
  权限、PID 重用保护，以及端口 TIME_WAIT 不误判为监听冲突。
- Go Web gateway 测试：静态文件、SPA 路由、HTTP/WS 路由代理、隐藏文件保护。
- `bash -n artifacts/install.sh`、`git diff --check`。
- 实际通过本地归档完整安装，重建 Robot Python 环境并导入能力依赖。
- `semantic runtime install` 以正式 Pack 完成 Native MuJoCo 真实场景 smoke。
- 新 Server 初始化独立数据库和随机密码；通过 Web 同源代理登录。
- 发布并查询 grasp-object 0.4.23、semantic-navigation 0.4.7、place-object 0.4.42。
- 本地 HTTP 镜像实际执行 `curl | bash`，重新下载、SHA256 验证、解包并重复安装。
- 同版本重复安装保留密码；测试结束停止仅由测试安装器创建的 Server/Web。

详细测试报告位于本机忽略目录 `.build/smoke-jggxasvv/smoke-report.json`，日志和新建
的测试数据库也留在该独立目录。现有源码工作区的 8080/3000 服务未停止或替换。

## 未宣称完成

没有在另一台干净 OS 上验证 apt 自动补依赖；没有公网 HTTPS 托管、代码托管平台 Release
上传、跨版本数据迁移、systemd 开机启动、LLM 调用、Robot 抓取任务或完整物理产品验收。
资产许可仍需审查，发布包仅限内部部署。没有移动任何既有 Git Tag。

初版使用 Runtime 仓旧 authoring 样例，实测暴露 `pose` 字段兼容问题；已改为
Framework 当前 schema 的源码场景模板。旧测试包已隔离在 `.build/`，不在最终发布目录。
# 2026-09-10：局域网与安装体验 (.6)

- 发布版本：`0.5.0-dev.20260910.6`；包 SHA-256：`27731775192b55212fd76b1a5ccdd514fe0862588b7c0ccfe22f8b6e99e5eb3e`。
- `python -B -m unittest discover -s tests`：131 项通过。
- Python 3.10 制品相关测试：71 项通过，包含真实 PTY 中密码只写终端、不写重定向输出。
- Debian 12 隔离容器完整安装、健康检查、Web SPA、登录 API、3 个技能版本、MuJoCo 场景 smoke、幂等重装通过。
- .6 新实例与 .4 旧实例均验证 `--configure-existing` 切换为 LAN 再切回 loopback；通过真实网卡 IP 请求 Web 网关后的 API。
- 旧实例测试确认业务版本、`files.json`、管理员密码保持不变；没有升级或迁移数据库。
- 桌面文件通过 `desktop-file-validate`，测试覆盖中文桌面路径、实例路径含空格、被修改/符号链接的入口不覆盖、卸载仅清理未修改入口。
- 无桌面环境自动跳过；未在用户的真实桌面上执行浏览器点击测试，桌面环境可能要求“允许启动”。
- PNG 与用户原图 SHA-256 一致；三档 ASCII 轮廓尺寸和终端单元格换行通过测试。
- 容器测试日志：`.build/container-debian12-i47jhhzl/container.log`（.6），`.build/container-debian12-nrr3gd__/container.log`（.4 + .6 管理工具）。
- 内部 .5 候选被容器测试拦截（导入辅助模块产生未入清单的 pycache），未发布；.6 禁用字节码写入并补回归测试。

## 2026-09-10：表单层级与刷新 (.8)

- 发布包 SHA-256：`3b42b709e9f64271515648ab12a1fa5f8212f121319cd72a2d882cf62d298a2b`。
- 136 项单元测试通过；Python 3.10 下 19 项体验测试通过。
- 真实 80×24 PTY 验证成功后仅显示欢迎页、终端内联密码、分类颜色及旧任务清除。
- 覆盖中文标签/续行对齐、19/31/39/63/79 列换行、紧凑小图标、失败保留任务、NO_COLOR / dumb / 重定向降级。
- 不发送 CSI 3J，不清除 shell 历史滚动区；仅交互终端刷新当前视口。
- .8 Debian 12 容器验证完整安装、SPA/登录、MuJoCo smoke、技能版本、幂等重装及 LAN/loopback 管理切换通过。
- 容器日志：`.build/container-debian12-mlxfgikw/container.log`。
- 发布归档内三个管理模块均与已测试工作区源码一致；非交互日志不包含密码。
- OSS 默认通道与 semantic.insightos.cn 已更新到 .8，线上脚本哈希、页面资源、四档浏览器布局及官网真实管道配置表单/取消验证通过。

## 2026-09-10：sudo 授权先于进度刷新 (.9)

- 发布包：362899026 bytes，SHA-256 `50be9a117ee0899759bfd1ffde3606a0a00f4f5c2781230486c94f47b41a3999`。
- 完整单元测试 142 项通过；Python 3.10 制品相关测试 82 项通过。
- 真实 80×24 控制终端 + 管道 stdin，使用不提权、不执行真实包管理器的 fake sudo 验证：
  授权提示先于进度刷新，密码不回显、不写日志，认证失败不进入依赖安装，后续命令携带 `sudo -n`。
- 单元测试覆盖 root / 已缓存授权跳过、缺少 sudo、无控制终端、权限检查超时、授权早于面板创建、
  子命令启动前刷入 START 日志及失败返回码记录。没有清除开发机的真实 sudo 缓存。
- Debian 12 隔离容器完成真实系统依赖安装（root 分支）、完整部署、MuJoCo 场景 smoke、
  SPA/API 登录、三个技能版本、幂等重装及 LAN / loopback 管理切换。
- 容器日志：`.build/container-debian12-wisdsysz/container.log`；依赖日志确认 apt-get 启动前已记录权限及命令。
- 归档内三个管理模块与已测试源码一致；`bash -n artifacts/install.sh`、`git diff --check` 通过。
- work22 的真实 PAM / sudo 策略及用户密码输入仍需用户重试验证；没有操作其原有 panel.py 进程。
- OSS 默认通道及官网版本已更新至 .9；官网脚本与本地 SHA-256 一致，四档浏览器布局与资源检查通过。
  官网真实 `curl | bash` 在 PTY 中完成 .9 下载、校验、配置表单及取消验证，未启动本机系统依赖安装。
  网站更新前备份位于服务器 `semantic-site/backup.sudo.7tbEi0kx`。

## 2026-09-10：文字欢迎页、默认局域网及 Web 端口配置 (.10)

- 发布包：362898683 bytes；SHA-256 `9d859153eb614b517c7005fbc9edf113df63ac187cc1227afdfbd706ca7cf482`。
- 145 项单元测试通过；Python 3.10 制品相关测试 85 项通过；bash 语法和 diff 空白检查通过。
- 终端欢迎页不再加载/绘制 ASCII 图案；80×24 文字布局和桌面原始 PNG 图标回归通过。
- 新安装默认 Web 监听 0.0.0.0，实际验证不传 --lan 也可通过 loopback 和容器网卡 IP 请求 API。
  API/WS 仍仅本机；显式 --web-host 覆盖默认，旧实例不传网络参数保留原配置。
- configure 支持 --web-port；无效/重复/占用端口在停止现有 Web 前被拒绝。
- Debian 12 实测完整安装、MuJoCo smoke、登录/技能、重装；随后切换 LAN / loopback 及 Web 新端口。
- 单独验证 .9 业务实例使用 .10 管理工具切换网络和端口，原业务版本、files.json、密码、Server 进程身份均保留。
- 两组日志：`.build/container-debian12-bhh6mzfl/container.log`（.10 新安装）、
  `.build/container-debian12-a356174a/container.log`（.9 + .10 管理工具）。
- 发布归档内三个管理模块与已测试源码一致。站点更新前备份：`semantic-site/backup.textlan.Zemrv67Q`。
- OSS 通道和官网更新至 .10，线上脚本哈希与工作区一致。四档浏览器布局与资源安全检查通过。
  官网真实 curl 管道下载/校验后，配置表单默认显示 `0.0.0.0:3000`；测试在确认处取消，没有修改开发机系统。

## 2026-09-10：已删除终端工作目录误阻止卸载 (.11)

- 用户进程信息确认：阻塞 PID 是 Bash，cwd 为实例 logs 目录且已删除，不是 Robot/Runtime。
- 修复检查 inode 链接数：已删除 cwd 不阻塞卸载；不忽略进程仍在使用的实例可执行文件/命令参数。
  真实目录（包括名称以 ` (deleted)` 结尾者）继续受保护，并提示 PID、进程名、原因及 cd 操作。
- 149 项单元测试通过，Python 3.10 制品测试 89 项通过；真实 Bash 在已删除 cwd 中保持存活，
  测试实例仍可卸载，且没有向该 Bash 发信号。真实目录和仍运行的实例程序正确阻止删除。
- 增加 semanticctl uninstall / --dry-run / --yes / --purge；status 显式显示 Server/Web 与其他占用。
  终端失败输出简明原因，完整 traceback 保留在外部 0600 卸载日志。
- 完整容器安装、MuJoCo、技能、Web 登录、幂等重装、网络/端口配置通过；日志
  `.build/container-debian12-to9tg1j_/container.log`。
- 随后以 UID 1000 对该测试实例执行已安装 semanticctl 的 status、uninstall --dry-run、uninstall --yes，
  确认程序删除而数据库和密码不变。仅清理此次生成的测试实例程序；配置/数据/日志仍在测试目录，程序可通过同版本重装恢复。
- 发布包 362898821 bytes，SHA-256 `3f37f29a1820a2231dc2c800f8568b8b4a407c9d01be9a81debc2a58270f6bf5`。
  包内三个管理模块及入口内嵌卸载器均与工作区源码一致；bash 语法与 diff 空白检查通过。
- OSS 通道、官网脚本和版本已更新至 .11，四档浏览器布局/资源检查通过；线上脚本与本地逐字节一致。
  使用官网下载的脚本对隔离夹具执行管道卸载，真实 Bash 保持在已删除 cwd 中：卸载成功、Bash 仍存活、
  测试数据保留。没有操作 work22 的进程或实例。网站更新前备份为 `semantic-site/backup.uninstall.WcPuxtbi`。
