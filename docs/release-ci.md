# Release CI 与 installer

所有 13 个组件使用 GitHub 官方 `ubuntu-24.04` runner。PR/main 运行组件检查并上传临时 Actions 产物；推送 `v*` Tag 发布 Release。历史 Tag 通过 **Actions → CI and Release → Run workflow**，在 main 上填写 Tag 补发。构建从 Tag 检出业务源码，从当前工作流提交读取构建脚本，分别记录 SHA，不移动 Tag、不覆盖已发布 Release。

| 仓库 | Release 内容 |
| --- | --- |
| Semantic-Framework | 静态 Server、Pilot、CLI |
| semantic-web | Web 生产静态资源 |
| AbilityFramework | 静态 AbilityFramework |
| Ability-SDK-Python | Python Wheel、sdist |
| semantic-docs | Hugo 文档站点 |
| robot-sdk | core、r1pro、franka Wheel、sdist |
| robot-skill | SDK Wheel、sdist、三个 Skill ZIP |
| r1pro-ability | 共享 Wheel、sdist、七个 Ability ZIP |
| ability-scaffold | Wheel、sdist |
| semantic-deployment | 静态部署工具、Type Package 模板 |
| mujoco-asset | 已批准公开的维护模型、场景、资产目录与来源声明 |
| ability-runtime | 锁定的第三方 Python Wheel 缓存与许可文件 |
| mujoco-runtime | Runtime Wheel、visuals Wheel、离线 native MuJoCo Runtime Pack |

每个 Release 包含 `SHA256SUMS` 与 `release.json`。后者记录 Tag、源码 SHA、构建脚本 SHA、平台、CI 链接及验证范围。R1Pro CI 从已发布的 Robot SDK、Ability SDK 和 scaffold 获取依赖；Runtime Pack 锁定 Framework 场景定义与资产目录版本。更新依赖时需同时更新对应 CI 中的依赖 pins 和 quick-start 的 `repo-versions.json`，通过兼容性检查后再发布新 Tag。

## 安装

在 **当前 main** 的 quick-start 中运行（旧 `v0.1.0` 源码 Tag 不含新入口，Tag 保持不变）：

```bash
python3 semantic_installer.py --release --install-system-deps
# 指定独立目录，自动确认安装：
python3 semantic_installer.py --release --dir "$HOME/.local/share/semantic-demo" --yes
```

默认下载 quick-start 的 `v0.1.0` Release。入口核对该 Tag 的固定源码 SHA，校验每个下载文件，再交给原有制品安装器完成解包、环境初始化、Runtime 注册、技能发布和服务启动。目标机不需要 Go/Node/xmake 或各子仓库源码；需要 Python 3.10+，系统图形运行库与 zstd，以及首次安装 Python 运行环境时的网络。管理员账号 `admin` 使用安装时生成的随机密码，`semanticctl welcome` 查看；源码开发模式的 `test-admin-pass` 不适用于此入口。

也可以只下载 Release 中的 `install.sh`、整包 `.tar.gz` 及 `SHA256SUMS`，先运行 `sha256sum --check --ignore-missing SHA256SUMS`，再运行 `bash install.sh --package <整包路径> --sha256 <整包SHA256> --install-system-deps`。安装入口不覆盖已有不同版本的实例，升级应使用新目录并单独迁移数据。

## 组装

quick-start 的 **Installer from Releases** 工作流从版本清单读取全部组件 Release，不重新编译任何组件；只编译本仓库的轻量 Web 网关。整包附带 `release-lock.json`，记录实际使用的所有资产哈希。构建机需要 Go 1.25.8、uv 0.12.12、Python/PyYAML、binutils；安装机不需要这些构建工具。

```bash
python3 artifacts/fetch_releases.py --cache /tmp/semantic-releases
python3 artifacts/build_from_releases.py \
  --version 0.1.0 --cache /tmp/semantic-releases \
  --output artifacts/releases/0.1.0/linux-x86_64
```

输出目录必须不存在，缓存命中也重新校验哈希。版本清单中的源码 SHA 必须与 Release 元数据一致；不同组件的依赖 pins 也必须一致。归档解包拒绝路径穿越、链接和重复文件，静态应用程序与 uv 的 glibc 基线在组装时检查。模型和第三方 Wheel 保留来源、许可声明，不重新授权。

PR/main 组装后执行真实安装冒烟检查，覆盖 Web SPA、认证 API、三个精确技能版本、原生 MuJoCo 注册/场景 smoke、重复安装和管理配置更新。通过后才允许 Tag/manual 发布。它不执行真机任务、GPU 验收或 LLM 拆码垛任务。Release 中的内部 Python 包版本继续沿用原业务基线，不强行改成维护 Tag 后缀。

## 可选 musl Release

默认 installer 及 `repo-versions.json` 继续使用现有 glibc 运行栈。额外的 `.github/workflows/musl-release.yml` 使用独立的 `musl-v*` Tag，发布供 `--musl` 选择的预发布包，不更新普通 latest Release 或 OSS stable。

锁定的输入见 `artifacts/musl/releases.json`（组织内依赖 Release）、`upstream.json`（官方 musl Python/uv、基础安装包与源码）和 `python-wheels.json`（PyPI musl Wheel）。组装会验证 SHA-256、源码提交和平台，审计整个包及 Wheel 中的 ELF 依赖，然后在断网 Alpine 容器中测试中英文安装入口、Server/Web、Native MuJoCo 场景和机器人库联合运行。详见 [musl 构建说明](../artifacts/musl/README.md)。
