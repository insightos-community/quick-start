# Public maintenance snapshot

This repository contains a single source snapshot derived from maintenance tag
`v0.1.2`. Source revision: `162b74375c60476f178b6454bd1e87e44a0f9691`.
The source history and earlier tags/branches are not included. Public commit IDs
are therefore different. Use quick-start's public manifest for compatible pins.

This is the existing verified product line, not the latest upstream implementation.
Publication changes are limited to documentation, public configuration/dependency
sources, license notices and exclusion of non-distributable or generated assets.
Existing package/product version strings have not been bumped.

The initial public tag excluded Galaxea robot models. On 2026-09-10 the project
owner confirmed communication with the rights holder and instructed restoration
of the existing model baseline via Git LFS. The updated asset pin supplies these
models; see [downloads and attribution](https://github.com/insightos-community/mujoco-asset/blob/main/EXTERNAL_MODELS.md).
No new upstream business version or blanket Apache-2.0 license for these models is implied.
The initial source snapshot did not include a full-stack archive. Subsequent CI
publishes component Releases and assembles an installer from their pinned outputs.
Historical tags stay unchanged; release metadata records both the source and assembly
recipe commits. Installer smoke checks do not certify hardware or LLM task execution.
See [release CI](docs/release-ci.md).

中文：本仓库从上述旧业务维护 Tag 导出单次公开快照，不包含原提交历史及旧分支、旧
Tag。公开 SHA 与原仓库不同，请以 quick-start 的公开清单为准。首次公开版本排除了
星海图模型；后续按项目所有者确认恢复旧业务模型的 LFS 下载，不升级业务版本或重新授权第三方模型。
