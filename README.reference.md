# Repository configuration reference

[English overview](README.md) | [中文概览](README.zh-CN.md)

This reference retains the useful version-management concepts from the earlier guide. Hosting-specific administration and private operational records are intentionally omitted.

## Profiles and manifests

`repo_versions.py` reads a profile from `--env PATH`, detects a compatible profile from the repository origin, or falls back to `.env`. The public profile [github.env](github.env) defaults to `insightos-community` with explicit repository-name mappings. Override `GITHUB_ORG` only for a complete compatible fork.

```bash
python3 repo_versions.py --env github.env --show-config
python3 repo_versions.py --env github.env
```

`--show-config` inspects configuration without cloning. The interactive view probes the repositories listed in the manifest; it does not discover arbitrary unrelated projects in an organization.

The manifest maps workspace directories to remote URLs and revisions:

```json
{
  "version": 1,
  "repos": {
    "semantic-framework": {
      "url": "https://github.com/insightos-community/Sementic-Framework.git",
      "ref": "your-release-tag",
      "commit": "replace-with-the-matching-full-commit-id"
    }
  }
}
```

This is a schema example, not a usable release manifest. Every selected URL and commit must exist and be accessible to its intended users. Keep nested local directory keys even if remote repository names are flat.

## Freeze and build

After checking out and verifying a consistent workspace:

```bash
python3 repo_versions.py --env github.env --freeze VERSION
bash build.sh VERSION
```

Replace `VERSION` with your release name. Freezing writes a release snapshot under `releases/`; `build.sh` builds using that snapshot. Inspect the snapshot before distribution: a Git commit pin does not remove private URLs, secrets, or unlicensed assets.

The source installer consumes a manifest; it does not accept `repo_versions.py`'s `--env` switch. Keep local credentials outside committed profiles and use your Git credential helper or SSH setup as appropriate for the selected host.

See the [TUI guide](semantic-installer-README.md), [deployment artifacts](artifacts/README.md), and [publication checklist](maintenance/open-source-readiness.md).
