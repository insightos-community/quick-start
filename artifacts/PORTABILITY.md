# 静态制品与 Linux 发行版适配

## 本次交付

内部制品：`0.5.0-dev.20260910.3`，大小 362387241 bytes。

SHA256：`ea6874612f8ac957adea6d2de18a4a6563b8a0acac67a7c042f88f1f18ba7fa8`。

此版本替换所有应用原生程序，不再复制旧动态程序到 Bundle。源码工作区、已有服务、
原仓库 `.output` 与 xmake 配置均未改动；构建在 `artifacts/.build/` 完成。

| 程序 | 构建方式 | ELF 检查 |
| --- | --- | --- |
| AbilityFramework | 原项目 `fwk-static` + 第三方依赖源码静态构建，glibc 工具链 | 无 PT_INTERP / DT_NEEDED |
| semantic-server | CGO + musl-gcc + `musl,netgo,osusergo` + 外部静态链接 | 无 PT_INTERP / DT_NEEDED |
| semantic / semantic-pilot / semantic-robot-instance | 同上 | 无 PT_INTERP / DT_NEEDED |
| semantic-web-gateway | `CGO_ENABLED=0` | 无 PT_INTERP / DT_NEEDED |
| uv | 保留发布用动态版本 | 直接引用最高 GLIBC_2.17 |

Go 的实际构建参数：

```bash
CGO_ENABLED=1 CC=musl-gcc go build -trimpath \
  -tags musl,netgo,osusergo \
  -ldflags '-linkmode external -extldflags "-static"' \
  -o /path/to/semantic-server ./cmd/semantic-server
```

`go-fitz v1.24.15` 提供 musl 版 MuPDF 静态库，因此无需删除 PDF 功能，也无需依赖
低版本 glibc 容器来解决 Server 的链接问题。没有选择 `CGO_ENABLED=0` 路径：
该版本的 go-fitz 在此模式下使用 purego/dlopen，并不意味着没有原生动态库依赖。
`probes/pdf_static.go` 实际测试生成 PDF、提取文字和渲染页面，不只是执行 `--help`。

## 兼容范围与验证

- Ubuntu 24.04 x86_64 宿主机：新包完整隔离安装、Web/API 登录、MuJoCo 场景 smoke、
  三个 Skill 精确版本发布、curl 管道重装、密码保留、测试服务关闭均通过。
- Fedora 42 干净容器：dnf 自动安装依赖及上述完整流程通过。
- Debian 12（glibc 2.36）干净容器：apt 自动安装依赖及上述完整流程通过。
- Debian 11 / glibc 2.31 容器：静态 Server 启动帮助、PDF 文本/渲染通过；
  AbilityFramework 实际启动、资源 API、内嵌 Web UI 通过。
- Alpine 3.20：静态 AbilityFramework 版本命令及静态 MuPDF 文本/渲染通过；
  **不代表整套 Python/MuJoCo 运行栈支持 Alpine**。
- Debian 11 完整安装测试被官方 bullseye-security 元数据过期阻止；HTTP/HTTPS 均复现。
  未关闭有效期检查、未关闭签名验证，也未修改宿主机镜像源。
- yum、pacman、zypper 的命令生成、发行版识别和错误处理有单元测试；
  尚未在这些发行版上完成真实安装验收。

当前清单的 glibc 2.28 是 Python/Wheel 栈的目标基线，来自现有 manylinux Wheel
和 uv 的兼容要求，不是“所有 glibc >= 2.28 系统已实测”的承诺。Python 解释器、
libstdc++/OpenMP、图形驱动及 Wheel 全部导入/启动通过才算可用；安装流程会执行这些检查。
目前仍仅提供 x86_64 包，未发布 ARM64 制品。Robot/真实硬件任务与 GPU 渲染需另行验收。

## 系统依赖策略

安装器识别 `/etc/os-release` 的 ID/ID_LIKE，并检查对应命令存在。仅显式传入
`--install-system-deps` 才会调用 root/sudo 安装。目标机仍须先准备 bash、Python 3.10+；
curl 管道入口需要 curl。

| 管理器 | 对应依赖 |
| --- | --- |
| apt-get | ca-certificates, zstd, libstdc++6, libgcc-s1, libgomp1, libegl1, libgl1, libgl1-mesa-dri |
| dnf / yum | ca-certificates, zstd, libstdc++, libgcc, libgomp, mesa-libEGL, mesa-libGL, mesa-dri-drivers |
| pacman | ca-certificates, zstd, gcc-libs, libglvnd, mesa |
| zypper | ca-certificates, zstd, libstdc++6, libgcc_s1, libgomp1, libEGL1, libGL1, Mesa-dri |

不存在自动替换系统 glibc、添加第三方仓库、关闭签名检查或全系统升级行为。
Arch 使用现有同步数据库的 `pacman -S --needed`，管理员须先保证系统已正常更新；
不会执行会造成部分升级的 `-Sy`，也不会擅自执行 `-Syu`。
参考：[Arch 系统维护](https://wiki.archlinux.org/title/System_maintenance)、
[Fedora Mesa 包](https://packages.fedoraproject.org/pkgs/mesa/)、
[manylinux 兼容规范](https://github.com/pypa/manylinux)。

## 可复现检查

```bash
python -B artifacts/build_native.py
python -B artifacts/probes/ability_http.py artifacts/.build/native-static/AbilityFramework
python -B -m unittest discover -s tests -q
python -B artifacts/test_container.py --distro fedora \
  --package artifacts/releases/0.5.0-dev.20260910.3/linux-x86_64/semantic-0.5.0-dev.20260910.3-linux-x86_64.tar.gz
```

容器测试支持 `debian11`、`debian12`、`fedora`，默认使用一次性容器，不映射宿主机端口、
设备、Docker socket，也不使用 privileged/host-network。日志和结果保存在
`.build/container-*/`。Debian 测试容器使用同一官方源的 HTTPS 地址，安装器本身不改源。

本次成功报告：`.build/smoke-fawmicr0/smoke-report.json`、
`.build/container-fedora-njby9jeu/semantic/smoke-report.json`、
`.build/container-debian12-ro9_9p2c/semantic/smoke-report.json`。

原生构建日志与 ELF 报告在 `.build/native-static/`；归档内包含 `native-linkage.json`
及逐文件 SHA256。静态编译不等于无需持续更新第三方安全补丁，应随版本重新构建分发。
