# BEHAVIOR 扩展场景 — 清单与取得渠道

本目录是 BEHAVIOR(Isaac Sim) 扩展场景的**清单源文件**，随仓库版本化。安装本体（下载与
校验、安装编排）在 `artifacts/runtime/extension.py`，设计依据见 `../../docs/extensions.md`。

`extension.json` 由安装器直接解析。改字段前先读 `docs/extensions.md` 第一节：清单约束
不是风格偏好，`verify` 会按它逐字节校验。标识用 `isaac`，与 TUI 阶段 8 的
`EXTENSION=isaac` 取值一致。

## 通道布局

OSS 是主通道，GitHub Releases 是镜像；一份清单两处通用。

```text
OSS:    <oss>/extensions/isaac/stable.json                # 可变指针 {"version":"0.1.0"}
        <oss>/extensions/isaac/0.1.0/extension.json       # 不可变清单
        <oss>/extensions/isaac/0.1.0/<artifact>           # 不可变产物
GitHub: tag ext-isaac-v0.1.0 的 Release                   # 不可变镜像（资产平铺）
```

清单里每个产物的 `url` 是**相对路径**（裸文件名），安装时按所选通道拼成绝对地址：

- `--extension-source oss`（默认）：`<base>/extensions/isaac/0.1.0/<名称>`
- `--extension-source github`：`https://github.com/<org>/quick-start/releases/download/ext-isaac-v0.1.0/<名称>`

六个产物合计约 99 MB（最大约 52 MB），都小于 GitHub 单个 Release 资产的 **2 GiB 上限**，因此 GitHub 通道
可以完整镜像，`--extension-source github` 无需回退。超限产物才会被清单标成 `hosts: ["oss"]`
并在 GitHub 通道自动回退到 OSS（LIBERO 的三个大产物就是这种情形）。

## 与 LIBERO 的三点不同

1. **引擎镜像不随任何包交付。** `behavior:v3.9.2` 约 31.1 GB，是 Docker 本地镜像库，Runtime
   用 `docker run` 消费。清单只能**探测**它的存在（`prerequisites` 的 `probe`），装不进来。
2. **数据集与策略服务是人的事。** 授权数据集（数十 GB）用 `--asset-root` 指向；π0.5 是独立
   GPU 策略服务（端口 20080），不进镜像、不进 Ability 环境，且**必须先于机器人四件套启动**。
3. **GPU 是硬前提。** 清单 `host_requirements.gpu=required`；预览需 ≥6144 MiB 空闲显存，
   6 GB 卡上能启动场景但预览必然失败，安装时要用 `--generate-previews=false`。

这三项都写在 `prerequisites` / `post_install` 里：`probe` 会在安装前跑一次检测，**失败只告警、
不阻断**（允许"先装环境、后补镜像"的正常顺序）；`user_action` 是只能由人完成的动作。

## 发布流程（sha256 与 size 从哪来）

仓库里这份 `extension.json` 是**模板**：`sha256` 全是 `0`，`size` 是 2026-09 实测值。
真实产物在构建机上，按下面两步回填与发布，**不要手填**。

```bash
# 1. 在构建机产出六个产物后，回填并生成 staging（清单 + 产物 + stable.json）
python3 artifacts/build_extension.py --id isaac --version 0.1.0 \
  --package-dir <六个产物所在目录> --output <仓库外的 staging 目录>
#    —— 逐产物算 sha256/size 写回 extensions/isaac/0.1.0/extension.json，用 extension.parse 自检。

# 2. 发布：OSS 不可变前缀 + stable.json 指针，再建 GitHub Release
python3 artifacts/publish_extension.py --id isaac --version 0.1.0 \
  --staging <staging 目录> --channel oss,github
```

扩展版本与 GitHub tag 固化在 `repo-versions.json` 的 `extensions.isaac`；产物摘要固化在通道
上的不可变 `extensions/isaac/0.1.0/extension.json`。`extensions/isaac/stable.json` 是可变
对象，已在 OSS mutable 白名单里（`artifacts/oss_client.py` 的 `MUTABLE_PATTERNS`）。

发布后核对一次：

```bash
semanticctl extension verify isaac --source oss
```

## 六个产物与安装顺序

顺序固定：**Runtime → 场景 → 运行支持 → Ability → 模型 → Skill**。Bundle（运行支持）
是底座，后三者往它上面插，倒序装不上去。

| 角色 | 产物 | 体积 | 通道 |
|---|---|---|---|
| `runtime` | `behavior-runtime-0.1.18.zip` | 约 23 MB | OSS + GitHub |
| `scene_catalog` | `behavior-scenes-3.9.2.zip` | 约 1.3 KB | OSS + GitHub |
| `robot_base` | `r1pro-behavior-robot-0.1.1.zip` | 约 52 MB | OSS + GitHub |
| `robot_ability` | `r1pro-behavior-ability-0.1.3.zip` | 约 24 MB | OSS + GitHub |
| `model` | `r1pro-radio-model-0.1.1.zip` | 约 1.2 KB | OSS + GitHub |
| `robot_skill` | `vla-manipulation-0.1.10.zip` | 约 12 KB | OSS + GitHub |

Runtime 的 `installation_id` 是 `local-behavior-omnigibson`，endpoint 本文用 `18090`——
与 LIBERO 的 `local-libero-robosuite-1.4` / `8092`、基础环境的 `native-mujoco` / `8090`
都不同，可以并存。

> **模型包必须先重打成 0.1.1。** 源文件里的 endpoint 是 `ws://127.0.0.1:18080`，要改成
> `ws://127.0.0.1:20080` 再升版本重打（同名同版本内容不同会被安装器拒绝）。清单里登记
> 的是重打后的 `0.1.1`。

## 许可

BEHAVIOR / OmniGibson 与授权数据集是上游第三方资产，已获授权在本通道内分发。清单的
`license` 与 Runtime 包的 `license` 都是 `behavior-assets`，安装器据此自动补
`--accept-license behavior-assets`（也可显式传）。数据集只按上游许可（**仅限非商业学术
研究**）由使用方单独取得，不随本通道分发。不要因为"能下载"就默认可再分发。

## 人工前置

- **数据集**：用 `--asset-root` 指向宿主绝对路径，且必须是含 `2026-challenge-task-instances/`
  的上一级目录；磁盘可用 ≥50 GiB。
- **π0.5 策略服务**：OpenPI 环境 + 官方 radio 权重（`turning_on_radio`），`--action-horizon 16`
  要与模型配置的 `actions_per_chunk: 16` 一致，端口与模型配置的 `endpoint` 必须一致。
- **LLM 密钥**：Agent 对话必需，写在 Server 工作目录的 `.env`。
- **端口段**：Runtime `18090`、策略服务 `20080`、Ability `18100-18199`。Ability 段与 LIBERO
  共享，同机并存要分别分配，否则报 `http server bind ... failed`。

## 已验证的现场结论

命令级实测见 `../../temp/behavior-packaging-and-install-commands.md`（《BEHAVIOR 打包与安装
速查》）。要点：π0.5 必须先起，否则 Ability 停在 `Standby`、Pilot 一直 `offline`；
`data_root`/`bundles_dir` 必须是绝对路径，否则受管 Robot 起不来；
场景装完不会自动进项目，要手动「添加兼容场景」。
