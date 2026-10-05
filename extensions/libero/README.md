# LIBERO 扩展场景 — 清单与取得渠道

本目录是 LIBERO 扩展场景的**清单源文件**，随仓库版本化。安装本体（下载与校验、安装
编排）在 `artifacts/runtime/extension.py`，设计依据见 `../../docs/extensions.md`。

`extension.json` 由安装器直接解析。改字段前先读 `docs/extensions.md` 第一节：清单约束
不是风格偏好，`verify` 会按它逐字节校验。

## 通道布局

OSS 是主通道，GitHub Releases 是镜像；一份清单两处通用。

```text
OSS:    <oss>/extensions/libero/stable.json                # 可变指针 {"version":"0.1.0"}
        <oss>/extensions/libero/0.1.0/extension.json       # 不可变清单
        <oss>/extensions/libero/0.1.0/<artifact>           # 不可变产物
GitHub: tag ext-libero-v0.1.0 的 Release                   # 不可变镜像（资产平铺）
```

清单里每个产物的 `url` 是**相对路径**（裸文件名），安装时按所选通道拼成绝对地址：

- `--extension-source oss`（默认）：`<base>/extensions/libero/0.1.0/<名称>`
- `--extension-source github`：`https://github.com/<org>/quick-start/releases/download/ext-libero-v0.1.0/<名称>`

> **GitHub 通道对 LIBERO 不完整。** `franka-libero-robot.zip`（约 2.9 GB）、
> `franka-ability.zip`（约 2.9 GB）、`franka-smolvla-model.zip`（约 3.3 GB）都超过
> GitHub 单个 Release 资产的 **2 GiB 硬上限**，清单把它们标成 `hosts: ["oss"]`。
> 走 GitHub 通道时安装器**自动回退到 OSS** 下载这三件；其余三件仍从 GitHub 取。
> 也就是说 GitHub 通道能装，但离线不可用——离线请用 `--extension-package-dir`。

## 发布流程（sha256 与 size 从哪来）

仓库里这份 `extension.json` 是**模板**：`sha256` 全是 `0`，`size` 是 2026-09 实测值。
真实产物在构建机上，按下面两步回填与发布，**不要手填**。

```bash
# 1. 在构建机产出六个产物后，回填并生成 staging（清单 + 产物 + stable.json）
python3 artifacts/build_extension.py --id libero --version 0.1.0 \
  --package-dir <六个产物所在目录> --output <仓库外的 staging 目录>
#    —— 逐产物算 sha256/size 写回 extensions/libero/0.1.0/extension.json，
#       用 extension.parse 自检，并为超 2 GiB 的产物自动加 hosts=["oss"]。

# 2. 发布：OSS 不可变前缀 + stable.json 指针，再建 GitHub Release（可镜像产物）
python3 artifacts/publish_extension.py --id libero --version 0.1.0 \
  --staging <staging 目录> --channel oss,github
```

`build_extension.py` 只在全部六个产物齐备时才写出清单，缺件直接失败。扩展版本与 GitHub tag
固化在 `repo-versions.json` 的 `extensions.libero`；产物摘要固化在通道上的不可变
`extensions/libero/0.1.0/extension.json`，复现时以它为准。上传走 `artifacts/oss_client.py` 的
既有通道，`extensions/libero/stable.json` 是可变对象，已在 OSS mutable 白名单里
（`artifacts/oss_client.py` 的 `MUTABLE_PATTERNS`）。

发布后核对一次，确认通道上的对象与清单一致：

```bash
semanticctl extension verify libero --source oss
```

## 六个产物与安装顺序

顺序固定：**Runtime → 场景 → 运行支持 → Ability → 模型 → Skill**。Bundle（运行支持）
是底座，后三者往它上面插，倒序装不上去。

| 角色 | 产物 | 体积 | 通道 |
|---|---|---|---|
| `runtime` | `semantic-libero-robosuite-1.4-0.4.0-dev.0.runtime.tar.zst` | 约 2.2 GB | OSS + GitHub |
| `scene_catalog` | `libero-scenes.zip` | 约 239 MB | OSS + GitHub |
| `robot_base` | `franka-libero-robot.zip` | 约 2.9 GB | 仅 OSS（>2 GiB） |
| `robot_ability` | `franka-ability.zip` | 约 2.9 GB | 仅 OSS（>2 GiB） |
| `model` | `franka-smolvla-model.zip` | 约 3.3 GB | 仅 OSS（>2 GiB） |
| `robot_skill` | `vla-manipulation.zip` | 约 12 KB | OSS + GitHub |

Runtime 的 `installation_id` 是 `local-libero-robosuite-1.4`，endpoint 固定 `8092`——
基础环境的 native-mujoco 用 `8090`，两者并存时不能复用。

## 许可

LIBERO 是上游第三方 benchmark（`github.com/Lifelong-Robot-Learning/LIBERO`），资产已获
授权在本通道内再分发。清单的 `license` 与 Runtime 包的 `license` 都是 `LIBERO`；装带
`license` 字段的扩展时安装器会自动补 `--accept-license LIBERO`（也可显式传
`--accept-license LIBERO`）。不要因为"能下载"就默认可再分发。

## 人工前置

清单 `prerequisites` 与 `post_install` 表达的是**装不进来、只能由人做**的部分：

- 模型权重走 HuggingFace 镜像（`HF_ENDPOINT=https://hf-mirror.com`，国内官网不可达）；
  代理与镜像二者取一即可。
- 场景落库只注册到场景目录，不会自动进项目，要手动「添加兼容场景」。
- 不绑定 Ability 与模型，Robot 起不来：Ability 停在 `Standby`（`abilityPort: 0`）直到
  超时，Pilot 一直 `offline`。
- Skill 带 `robot_required`，需要设备中心先有 Robot；全新环境要先「添加 Pilot」拿一次性
  加入码。

## 已验证的现场结论

2026-09 在核显机器（Intel 核显 / 30 GB 内存，无独显）上的完整实测记在 `../../NOTES.md`
的「LIBERO 扩展场景」一节，包括 CPU 推理调优与 heartbeat timeout 的性质。装之前值得先读。
