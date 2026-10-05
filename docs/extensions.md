# 扩展场景的安装设计 (LIBERO / Isaac)

本文回答一个问题：**预编译安装入口 (`install.sh`) 目前只能装基础环境，扩展场景（LIBERO，以及后续 Isaac）该怎么装。**

配套阅读：[发布 CI](release-ci.md)、[产物发布与一键部署](../artifacts/README.md)。源码编译路径（TUI 阶段 8）见 `semantic-installer-README.md`。

---

## 一、为什么不能直接塞进基础制品

预编译路径由 `artifacts/build_from_releases.py` 从各组件 Release 组装，先看清三条硬约束：

1. **`files.json` 是精确集合，不是白名单。** `artifacts/runtime/installer.py` 的 `verify_payload()`
   要求「列出的每个文件都存在且摘要一致」**且**「包内不存在未列出的文件」。往 payload 里
   多放一个文件就会报 `发布包存在未列入校验的文件`，安装直接失败。
2. **体积差约 30 倍。** 基础制品约 **345 MiB**（实测 `0.5.0-dev.20260910.3` = 362,387,241 B）；
   LIBERO 六个扩展产物合计约 **11.5 GB**（Runtime 2.2G + 场景 239M + 运行支持 2.9G
   + Ability 2.9G + 模型 3.3G + Skill 12K）。为不装扩展的人付这份下载量不可接受。
3. **扩展产物的构建依赖公司内网与上游第三方。** LIBERO 上游在 GitHub（不在公司 GitLab），
   Runtime 需要 Python 3.8 profile，模型包需要能访问 HuggingFace 或镜像。这些都进不了
   静态 Release 组装流水线。

**结论**：扩展场景必须是**独立的、可校验的旁挂产物**，由安装器在基础环境装好之后按需拉取安装。
基础制品保持精简与不可变。

### 复用现状（这些已经有了，不要另造）

| 能力 | 位置 | 说明 |
|---|---|---|
| 组件安装 | `semantic install <包> --project <ID>` | 经运行中的 Server HTTP API；包类型 `scene_catalog` / `robot_base` / `robot_ability` / `model` / `robot_skill` |
| Runtime 安装 | `semantic install runtime --pack <文件> --installation-id <ID> -c <配置>` | **本地执行**，不经过 Server |
| 多组件集合 | `internal/install/package_set.go` | 一个 zip + `semantic-package.yaml`，按 `requires` 拓扑排序安装 |
| 管理入口 | `install.sh` 内嵌 `installer.py` / `install_support.py` / `uninstall.py` 到 `<实例>/bin/semantic-manager/` | `semanticctl` 复用 |
| 校验纪律 | `digest()` + `verify_payload()` + 归档安全解包 | 下载即校验 SHA256 与大小，拒绝路径穿越/链接/重复 |

> **`package` 集合表达不了 Runtime**：`InstallPackage()` 明确拒绝 `runtime` 与嵌套 `package`
> （"Runtime 请独立安装，组件集合只支持一层"）。所以集合包之上还需要一层清单来描述
> 「本地 Runtime 安装」与「Server 组件安装」两种落点。这就是本文的扩展清单。

---

## 二、设计：扩展清单 + 管理子命令 + 独立通道

三层，互相独立，可分别落地。

### 第 1 层：扩展清单 `extension.json`

小而独立（KB 级），与基础制品同通道发布，按 id 分目录：

```text
<base-url>/extensions/index.json                      # 已知扩展的目录（可选，便于 list）
<base-url>/extensions/libero/stable.json              # 当前稳定版本指针（可变对象）
<base-url>/extensions/libero/0.1.0/extension.json     # 该版本的清单（不可变，带 sha256）
```

清单结构（示例为 LIBERO；`sha256` 与 `size` 在此为占位，实际值以《LIBERO 打包与安装速查》的
本机实测大小为准：Runtime 2.2 GB / 场景 239 MB / 运行支持 2.9 GB / Ability 2.9 GB / 模型 3.3 GB / Skill 12 KB）：

```json
{
  "schema_version": 1,
  "id": "libero",
  "title": "LIBERO 仿真场景 (robosuite 1.4 + Franka + SmolVLA)",
  "version": "0.1.0",
  "compatible_base": ">=0.5.0",
  "profile": "libero-robosuite-1.4",
  "runtime": {
    "installation_id": "local-libero-robosuite-1.4",
    "endpoint": "http://127.0.0.1:8092",
    "pack": { "url": ".../semantic-libero-robosuite-1.4-0.4.0-dev.0.runtime.tar.zst",
              "sha256": "…", "size": 1932735283 }
  },
  "components": [
    { "role": "scene_catalog", "id": "libero-scenes",   "url": "…/libero-scenes.zip",        "sha256": "…", "size": 250609664,
      "previews": { "default_scenes": ["libero-spatial-0", "libero-spatial-7"],
                    "note": "包内 130 任务 / 6500 初态；不限定 --scene 会对全部初态逐一出图" } },
    { "role": "robot_base",    "id": "franka-libero-robot", "url": "…/franka-libero-robot.zip", "sha256": "…", "size": 3113851289 },
    { "role": "robot_ability", "id": "franka-ability",      "url": "…/franka-ability.zip",      "sha256": "…", "size": 2899102924,
      "project_default": true },
    { "role": "model",         "id": "franka-smolvla-model","url": "…/franka-smolvla-model.zip","sha256": "…", "size": 3435973836,
      "project_default": true },
    { "role": "robot_skill",   "id": "vla-manipulation",    "url": "…/vla-manipulation.zip",    "sha256": "…", "size": 11264,
      "robot_required": true }
  ],
  "post_install": [
    { "kind": "user_action", "text": "场景配置 → 添加兼容场景：安装只把场景注册到 scene-catalogs，不会自动进项目" },
    { "kind": "user_action", "text": "项目内容 → 机器人与模型配置：为 franka_panda 绑定 Ability 与模型，否则 Ability 停在 Standby" }
  ]
}
```

要点：

- **`role` 决定落点**：`runtime` 走本地 CLI；其余走 Server 组件安装。两者顺序固定为
  Runtime → 场景 → 运行支持 → Ability → 模型 → Skill（Bundle 是底座，后三者往它上面插）。
- **每个产物都带 `sha256` 与 `size`**，与基础制品同一套校验纪律，不做"清单里只写 URL"的弱化。
- **`previews.default_scenes`** 把「别对 6500 个初态全量出图」的建议写进清单，而不是靠用户记得。
- **`post_install`** 表达无法自动化的部分（绑定、加场景进项目），由安装器在结尾打印。

### 第 2 层：管理子命令 `semanticctl extension`

新增管理模块 `artifacts/runtime/extension.py`，与现有三个模块同等对待：

- `install.sh` 的内嵌块（`manager_shell()`，`artifacts/build_english_installer.py:69`）增加第四个文件，
  `build_installers.py --check` 继续强制生成脚本与源码同步。
- 子命令：`list` / `show <id>` / `verify <id>` / `install <id>` / `remove <id>`。
  `verify` 只做下载与摘要校验、不落地，供排障与验收。
- 安装流程严格按清单：

```text
1. 解析通道（--base-url / --source oss|github / --package 离线）取 extension.json
2. 逐产物校验 sha256 + size
3. runtime:  <实例>/current/bin/semantic install runtime --pack <文件> \
             --installation-id <runtime.installation_id> --endpoint <runtime.endpoint> \
             -c <实例>/configs/semantic-server.yaml        # 本地执行，不需要 Server
4. 组件:    取 admin token（<实例>/configs/secrets.json，与 publish() 同一来源），
             经 POST /api/v1/projects/<ID>/imports 上传，再 /imports/<id>/install
             传 InstallOptions（GeneratePreviews / SceneIDs / ProjectDefault / RobotID）
5. 无凭据或 Server 未启动时报错并给出下一步，不静默跳过
6. 打印 post_install 清单
```

- **目标 Project**：`--project <ID>` 显式指定；缺省取该用户 Default Project（框架里
  `EnsureDefaultProject` 建出来就是 `mode=development`，正好满足组件安装要求）。
  **组件安装必须落在 `mode=development` 的项目**（`internal/bootstrap/component_install.go:233`），
  安装器需要在日志里说清这一点。
- **`--robot`**：Skill 带 `robot_required` 且已发现受管 Robot 时自动传入，否则只导入并提示去
  Web 设备中心「添加 Pilot」。
- **`remove`**：先停场景与 Robot，再 `semantic runtime uninstall --id <ID>` 与组件卸载；
  基础环境的 native-mujoco Runtime 不受影响（`installation_id` 与 endpoint 各自独立）。

### 第 3 层：发布通道

- **产物存放**：沿用现有通道，新增不可变前缀 `extensions/<id>/<version>/<artifact>`，
  以及可变的通道指针 `extensions/<id>/stable.json`。OSS 侧需要**放开 mutable 白名单**——
  目前 `artifacts/oss_client.py` 的 `MUTABLE_PATTERNS` 已允许更新 `extensions/*/stable.json`
  （与 `install.sh`、`channels/stable.json`、`channels/musl-stable.json` 并列；仍要求
  `semantic-managed=1` 标记与 ETag 备份，规则不放宽）。
- **一份清单，两个通道**：清单里每个产物记的是**相对路径**（裸文件名），安装时按
  `--source oss|github`（缺省 `oss`）拼成 `<base>/extensions/<id>/<version>/<名>` 或
  `https://github.com/<org>/quick-start/releases/download/ext-<id>-v<版本>/<名>`。清单与
  `stable.json` 统一从 OSS 取。GitHub 单个 Release 资产有 **2 GiB 硬上限**，超限产物在清单里
  标 `hosts: ["oss"]`（简写 `github: false`），走 GitHub 通道时安装器**自动回退 OSS**；
  `extension.GITHUB_ASSET_LIMIT` 是这条规则的唯一事实来源。
- **发布工具**：`artifacts/build_extension.py` 逐产物回填 `sha256`/`size`、标记超限产物、写出
  staging 与 `stable.json` 并用 `extension.parse` 自检；`artifacts/publish_extension.py` 先上传
  不可变前缀、全部校验通过后再提升 `stable.json`，随后建 GitHub Release（含 `SHA256SUMS` 与
  `release.json`）。CI 见 `.github/workflows/extension-release.yml`。
- **清单版本随仓库走**：清单源文件放 `extensions/<id>/extension.json`，版本号与产物一起升；
  扩展版本与 GitHub tag 固化进 `repo-versions.json` 的 `extensions` 段；每个产物的真实摘要固化
  在通道上的不可变 `extensions/<id>/<version>/extension.json`，复现时以它为准。
- **许可**：LIBERO 与 BEHAVIOR 都是上游第三方资产，已获授权在本通道内分发，模板 `license`
  回填为 `LIBERO` / `behavior-assets`。安装器对带 `license` 字段的扩展要求
  `--accept-license <id>`（缺省自动补清单声明的值），与现有 `AcceptedLicenses` 选项对齐。

---

## 三、Isaac 的差异（为什么清单要能表达"人要做的事"）

> **已落地（2026-10）。** 本节描述的清单与探测能力已实现：`extensions/isaac/extension.json`
> 用 `prerequisites[].check` 表达三条 `probe`（镜像 / 磁盘 / 显存），`user_action` 表达数据集、
> π0.5 服务与 LLM 密钥；`runtime.content` 声明 `--asset-root` 硬要求；`runtime.pack.license`
> 触发 `--accept-license behavior-assets`；`host_requirements.gpu=required` 与
> `ports=[[18090,18090],[18100,18199],[20080,20080]]` 交安装器在装前检查。TUI 阶段 8 的
> isaac 源码编译线（8.14–8.27）与预编译通道的 `semanticctl extension install isaac` 共用这一份清单。
> 引擎镜像与数据集仍不可分发，清单只登记与探测。

BEHAVIOR/Isaac 与 LIBERO 不是同一种交付，以下三项**不是可下载产物**：

| 项 | 规模 | 为什么装不进来 |
|---|---|---|
| 引擎镜像 `behavior:v3.9.2` | 31.1 GB | Docker 本地镜像库，不随任何 ZIP 交付；Runtime 用 `docker run` 消费 |
| 数据集 | 数十 GB | 上游渠道单独取得，不属于公司制品 |
| π0.5 策略服务 | 独立 GPU 服务 | 不进镜像、不进 Pilot/Ability 环境 |

所以清单需要 `prerequisites` 段，既给人看、也能机器探测：

```json
"prerequisites": [
  { "kind": "probe", "text": "本机已导入引擎镜像且 sha256 与 runtime-settings.json 一致",
    "check": "docker image inspect sha256:<ID>" },
  { "kind": "probe", "text": "asset-root 所在盘可用空间 >= 50 GiB",
    "check": "df -h <asset-root>" },
  { "kind": "user_action", "text": "数据集需按上游说明单独取得" },
  { "kind": "user_action", "text": "π0.5 策略服务需自行准备（不进镜像与 Ability 环境）" }
]
```

另有两处必须显式声明、否则现场必踩：

- **端口段冲突**：Isaac runtime 默认占 `18100`，与 LIBERO 的 Ability 端口段（`18100-18199`）
  重叠。清单应声明所需端口段，安装器在分配前做占用检查并给出调整建议
  （现有 `check_port()` 与 `ability_port_first/last` 机制可复用）。
- **GPU 前提**：Isaac 需要独显；LIBERO 在核显上能跑但慢（CPU 推理有自动线程调优）。
  清单用 `host_requirements.gpu` 区分「必需 / 可选」，让安装器能在装之前拦一下。

`prerequisites` 的执行语义是**可跳过但要报告**：探测失败给 warn 并继续，由用户决定是否继续装，
不要因为探测不到 Docker 就直接失败——那会把"先装基础环境、后补镜像"的正常顺序也堵死。

---

## 四、代码落点（已验证的接入点）

| 文件 | 改动 |
|---|---|
| `artifacts/runtime/extension.py` | 新增：清单解析、通道解析、下载校验、两类安装编排、`post_install` 打印 |
| `artifacts/runtime/installer.py` | `main()` 增加 `extension` 子命令组；`install()` 结束时按 `--extension` 触发；`install_manager()` 增加新模块的文件名 |
| `artifacts/build_english_installer.py` | `manager_sources()` / `manager_shell()` 的文件元组加 `extension.py`；同步更新 `artifacts/installer.en.json`（**新增中文字符串必须补英文条目，否则 `translate()` 直接抛 `Missing English translation`**） |
| `artifacts/build_installers.py` | 无需改逻辑，但改完必须 `python3 artifacts/build_installers.py` 重新生成并 `--check` 通过 |
| `artifacts/runtime/installer.py:712` | **建议**把 `bundles_dir` 从 `release/'robot-bundles'` 改为 `<root>/robot-bundles`。现状下 `RegisterInstalledBundle()` 会往不可变 Release 目录里写 `installed-bundles.json`，扩展 Bundle 又指向 Release 外的路径——架构上混，扩展开启后更明显 |
| `artifacts/oss_client.py:153` | mutable 白名单增加 `extensions/*/stable.json` |
| `extensions/<id>/extension.json` | 新增：清单源文件，随仓库版本化 |
| `extensions/<id>/README.md` | 新增：该扩展的取得渠道、许可、人工前置 |
| `tests/test_artifacts_extension.py` | 新增：清单解析、顺序、端口冲突、缺产物、坏 sha256、离线模式 |

沿用现有测试入口：`python -B -m unittest discover -s tests -q`，以及 `bash -n artifacts/install.sh`、
`python3 artifacts/build_installers.py --check`、`go test artifacts/gateway/main.go artifacts/gateway/main_test.go`。

### 一个容易漏的坑：新增管理模块要同步四个地方

`extension.py` 是**第四个**管理模块。加漏一处不会立刻报错，只会在某个入口上炸：

| 位置 | 漏了会怎样 |
|---|---|
| `artifacts/build_from_releases.py` 的 payload 组装 | 预编译发布包里没有 `extension.py` |
| `artifacts/build_release.py` 的 payload 组装 | 同上（另一条组装路径） |
| `artifacts/runtime/installer.py` 的 `install_manager()` | 现场 `semanticctl extension` 找不到模块 |
| `artifacts/build_english_installer.py` 的两个文件元组 | 英文版功能缺一半 |

`tests/test_artifact_experience.py` 的 `test_standalone_installer_does_not_add_unlisted_bytecode`
会抓第一个坑：它把 payload 里的模块拷出来单独跑 `installer.py`，缺模块直接
`ModuleNotFoundError`。

---

## 五、与 TUI 阶段 8 的关系

两条路服务不同人群，**共用同一份清单**，不要各写一套：

| | TUI 阶段 8（源码编译） | `install.sh` 扩展（预编译） |
|---|---|---|
| 人群 | 要改组件版本的开发者 | 只想跑起来的用户 |
| 产物来源 | 本机构建（上游源码 + 各仓源码） | 下载已验证产物 |
| 前提 | Go/Node/uv/xmake + 各仓源码 + 内网 | Python 3.10+ 与网络 |
| 清单 | `EXTENSIONS` 注册表 + `LIBERO_*` / `ISAAC_*` 设置 | `extension.json` |
| 状态 | 阶段 8 的 12 个步骤 (LIBERO) / 14 个步骤 (Isaac) | `semanticctl extension` |

TODO（可选，避免两份事实来源漂移）：让 TUI 阶段 8 的产物清单也从 `extensions/libero/extension.json`
读取，TUI 只负责"怎么构建"，清单负责"有哪些产物、装到哪"。当前 TUI 的产物名由
`LIBERO_ARTIFACTS` 拼装，与清单内容重复。

---

## 六、分阶段实施建议

按风险从低到高，每步都能独立验证：

1. ~~**只读层**：清单格式 + `extension list/show/verify`（只下载与校验，不落地）。~~
   **已完成。** `artifacts/runtime/extension.py` 落地，`install.sh` 的内嵌管理模块随之多一个
   `extension.py`（三处 payload 组装点 + `manager_shell()` 的元组都要同步加，否则
   独立运行 `payload/installer.py` 会 `ModuleNotFoundError`）。入口：
   `semanticctl extension list | show <id>` 与 `extension verify <id>`。
   清单模板在 `extensions/libero/extension.json`，**`sha256` 仍是 `0`，发布前必须回填**。
2. ~~**LIBERO 安装**：接上 Runtime 与组件两条安装路径 + `post_install` 清单。~~
   **已完成（2026-10）。** `extension.py` 的 `install` / `plan_commands` / `uninstall_plan`
   已实现两类落点与固定顺序，`install.sh` 的 `install_extension()` 在基础环境装好后按
   `--extension` 触发；离线走 `--extension-package-dir`（六个产物齐备即完全离线），
   `--extension-dry-run` 只打印命令计划。CI 用 staging 目录做离线冒烟（见
   `.github/workflows/extension-release.yml`）。**待办**：在目标机用真实产物按《LIBERO 打包与安装速查》
   逐条跑一遍安装并回填摘要，这是发布后的运维验收步骤，不是代码缺口。
3. ~~**发布流水线**：`extensions/<id>/` 的发布脚本 + OSS mutable 白名单 + 版本固化进
   `repo-versions.json`。~~
   **已完成（2026-10）。** OSS mutable 白名单加了 `extensions/*/stable.json`；
   `artifacts/build_extension.py` 回填并产出 staging，`artifacts/publish_extension.py` 发布
   OSS 不可变前缀、提升 `stable.json` 并建 GitHub Release；`repo-versions.json` 的
   `extensions` 段固化了版本、tag 与逐产物锚点。清单模板里的 `sha256` 仍是占位，由
   `build_extension.py` 在发布时从真实产物回填；OSS 通道上不可变的
   `extensions/<id>/<version>/extension.json` 已是回填后的真实摘要。
   **已发布（2026-10-05）**：isaac 0.1.0 与 libero 0.1.0 已推送到 OSS 主通道（桶
   `insightos-artifacts`，前缀 `semantic`，对象 `public-read`，匿名可读）。
   GitHub Release 镜像已发到 `insightos-community/quick-start`（tag `ext-isaac-v0.1.0` /
   `ext-libero-v0.1.0`），公开可下载并校验通过；libero 四个超过 2 GiB 单资产上限的产物
   （runtime 与三个 franka 包）仅走 OSS，走 GitHub 通道时自动回退。
4. ~~**Isaac 支持**：`prerequisites` 的探测语义 + 端口段分配 + GPU 前提校验。~~
   **已完成（2026-10）。** 清单模板 `extensions/isaac/extension.json` 已落；`extension.py` 支持
   `prerequisites[].check` 的 probe 执行（失败只 warn 并继续）、`host_requirements.gpu` 与
   声明的 `ports` 的装前检查（端口占用只告警）、`runtime.content`（`--asset-root`）与
   `runtime.pack.license`（`--accept-license`）；离线安装走 `--extension-package-dir` +
   `--manifest-file`。TUI 阶段 8 的 isaac 线（8.14–8.27）已实现，与预编译通道共用清单。
   引擎镜像与数据集仍未分发：清单只登记与探测，`sha256`/`license` 发布前回填。
   repo-versions 增补了 `semantic-simulation/isaac-runtime`（BEHAVIOR 依赖它，原先清单里没有）。

---

## 七、未决问题

1. **`bundles_dir` 是否迁出 Release 目录**：迁移更干净，但会影响已装实例的配置兼容性，
   需要一次配置迁移或兼容读取。建议与扩展支持一起做，并写进 `configure_existing` 的迁移路径。
2. **扩展清单要不要进基础制品**：放进去可离线 `list`，但会把扩展版本耦合到基础 Release。
   当前设计选择"运行时从通道取"，`--package` 离线场景可加 `--extension-manifest <文件>` 覆盖。
3. **离线安装**：> `--package` 已支持基础制品离线；扩展离线用 `--extension-package-dir <目录>`
   （六个产物 + 清单齐备即完全离线）或 `--extension-manifest <文件>` 覆盖清单来源。**已实现**。
4. **`previews` 的默认范围**：清单给了建议值，是否要按 `--scene` 之外的维度（按任务集）筛选，
   等实际使用反馈再定。
