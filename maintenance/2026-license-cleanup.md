# InsightOS 2026 源码维护发布（quick-start v0.1.1）

范围：`quick-start` 及 `repo-versions.json` 中的 13 个仓库。
各仓库使用 `chore/insightos-2026-license-cleanup` 分支和新的维护 Tag。
旧 Tag 不变；不将旧版本维护分支合入已有新业务改动的默认分支。

## 改动边界

- 为 1,323 个自有源码或构建配置文件补充 `Copyright 2026 InsightOS`、
  `SPDX-License-Identifier: Apache-2.0` 及 Apache 2.0 标准声明。
- 每个仓库增加 `LICENSE`、`NOTICE`、`LICENSE_SCOPE.md`，共 42 个法律说明文件。
- 仅清理 24 行纯装饰性分隔注释；保留有意义的注释、Python docstring、
  shebang、编码声明、Go 构建指令及原有换行格式。
- 将 r1pro-ability、robot-skill 的 Python 包许可证字段，以及 ability-py-sdk
  的 Debian 构建许可证参数，从 Proprietary 对齐为 Apache-2.0。
  未改变包版本、依赖锁文件、业务语句或 CI 发布条件。
- `artifacts/install.sh` 内嵌卸载模块同步对应源码的版权头，保持逐字一致。
- quick-start 清单使用新维护 Tag，并填写精确提交 SHA。

第三方代码、生成代码和模型资产不在重新授权范围内。Docsy/vendor、Ada、doctest、
GNU scope、Neargye semver、Mattias Jansson mdns、来源不明的 generator/
synchronized_value 及 Franka 模型包保留原内容和声明。具体边界见各仓库
`LICENSE_SCOPE.md`。模型/场景数据、二进制、Wheel、字体及图标不因本轮声明而
自动适用 Apache-2.0。

本地 ability-runtime 中已有的编译产物及 `.lfs-orig` 备份未改动、未提交。
此次为源码维护发布，未重新部署网站，未替换 OSS 安装包或 stable 指针。
托管平台按各仓库现有规则处理分支/Tag CI；本地验证通过不代表远端流水线全部通过。

## 版本基线

AbilityFramework 保持 v2.4.1、ability-py-sdk 保持 v0.4.0 对应的业务基线，
未升级到各自已有新业务改动的 main。
semantic-deployment 采用当前 `c7c539ec94c8d57492e53989b2b59c6dcef3f969` 基线，
保留此前已合并的 `grasp-object 0.4.23` 修复，未退回旧 v0.5.0 中的 0.4.22。
其他子仓库均基于清单原 Tag 对应提交。

各子仓库新 Tag 为 `原Tag-insightos.2026.1`；完整仓库地址、Tag 和提交 SHA
见 [repo-versions.json](../repo-versions.json)。quick-start 新 Tag 为 `v0.1.1`，
其父提交为 `160ed309d611f5bbccecdd001dbb17596de0287d`。

## 验证结果

逐文件核对差异只包含已声明的头部插入、装饰注释清理、三处许可证元数据修改和
卸载模块内嵌同步；第三方文件按 Git blob 或 LFS SHA-256 核对，本地未提交产物
按改动前 SHA-256 核对。

| 检查 | 结果 |
| --- | --- |
| Python AST（保留 docstring） | 315 文件一致 |
| Go scanner Token（含自动分号） | 495 文件一致 |
| C/C++/Go 去除注释后的文本 | 630 文件一致 |
| JavaScript AST（忽略位置/注释） | 190 文件一致 |
| Vue SFC template/script/style 内容 | 121 文件一致 |
| Shell `bash -n` | 23 文件通过 |
| TOML / CI YAML 解析值 | 13 / 9 文件一致，仅允许三处许可证元数据差异 |
| quick-start unittest | 149 通过 |
| Python 3.10 安装器兼容测试 | 89 通过 |
| artifacts gateway Go 测试 | 通过 |
| semantic-framework `go test ./... -timeout=120s` | 重跑全量通过 |
| semantic-deployment `go test ./...` | 通过 |
| semantic-web（Node 22.22.3） | 68 文件、483 测试通过 |
| semantic-web 生产构建 | 通过，有既有大 chunk / Sass 弃用提示 |
| r1pro-ability unittest | 79 项：78 通过、1 跳过 |
| robot-sdk conformance | 135 通过 |
| robot-skill | 122 通过 |
| mujoco-runtime 非 native/process 测试 | 57 通过、15 排除 |

首次前端测试使用本机 Node 20 时出现 jsdom/依赖环境错误，换用已安装的 Node 22 后
全量通过；未修改依赖。首次 SDK 测试缺少 Ruckig，在临时隔离测试环境补齐依赖后
全量通过。Runtime 现有虚拟环境缺少 pytest，使用隔离测试工具执行。
Framework 首次并发测试出现 Pilot 取消停止超时，原始源码 overlay 和改后源码的
独立测试均通过，改后全量重跑通过；未为消除此偶发超时修改业务代码。

未进行 C++ 全量重编译、真实机器人/GPU 仿真集成、文档站全量构建或线上安装回归。
网站端到端测试依赖 Playwright 且校验线上脚本与本地 SHA；本轮未部署网站，因此
不将该检查列为通过。
