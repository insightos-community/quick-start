# Maintenance release policy / 维护版本发布策略

Releases and future repository/mirror synchronization use the current verified quick-start iteration. They do **not** select the newest upstream or default-branch implementation automatically.

## Rules

1. Start maintenance changes from the tag pinned in `repo-versions.json`, retain that product baseline, and increment its maintenance suffix. The current sequence is `*-insightos.2026.1` → `*-insightos.2026.2`; quick-start advances from `v0.1.1` to `v0.1.2`.
2. Pin every component to both its new immutable tag and its full commit SHA. A repository's latest tag by timestamp, default-branch HEAD, or package registry's latest version is not a substitute for this manifest.
3. Do not move, delete, or overwrite existing published tags. Future maintenance begins from the current pinned iteration, not from the old original tag or leading upstream development.
4. Where the default branch has diverged, forward-port only explicitly scoped maintenance changes. Preserve its existing business implementation. A main-branch maintenance merge does not redefine the tested release baseline.
5. AbilityFramework remains on the `v2.4.1` product line, and ability-py-sdk remains on the `v0.4.0` product line for this quick-start release. Their maintenance tags intentionally need not point to default-branch HEAD.
6. Any deliberate business-version upgrade requires separate approval, dependency/bundle alignment, and compatibility validation. It is not part of documentation, copyright, website, or mirror maintenance.
7. Before a public mirror is published, also satisfy the [open-source readiness checks](open-source-readiness.md). Copying the correct Git refs does not remove private history, credentials, or asset-license restrictions.

## 中文摘要

- 保持旧业务基线，在当前已验证的维护 Tag 上继续迭代，不发布最领先版本。
- 后续构建、发布和仓库同步以清单中的 Tag + SHA 为唯一版本依据，不自动使用 main / develop / upstream 的最新提交。
- 已分叉主分支仅同步本次范围内的维护改动，不能将其新业务功能带入维护发布，也不能用旧基线覆盖其现有功能。
- 旧 Tag 不移动、不覆盖；需要升级业务版本时，另行确认并完成整栈兼容验证。
