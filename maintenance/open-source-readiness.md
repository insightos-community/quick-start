# Public snapshot verification

This release uses the previously verified maintenance product baseline, with
independent public commits and no imported source history. See
[publication scope](../PUBLICATION.md) and [pinned public manifest](../repo-versions.json).

- Public GitHub remotes are configured by default; self-hosted examples use placeholder hosts.
- Internal runner/image definitions and operational deployment defaults have been removed.
- AbilityFramework uses bundled dependency recipes and public upstream downloads.
- Galaxea model directories and their catalog entry are excluded, including LFS payloads.
- Original box/pallet/target assets have explicit source and Apache-2.0 declarations.
- Franka and third-party Wheel notices are preserved; native Wheel notices are supplemented.
- Generated first-party binaries/Wheels are built from source, not copied from local modifications.
- Public bootstrap scripts do not default to older full-stack binary channels.
- Existing services, website deployments and OSS objects are not changed by this repository publication.

## Verification boundary

The source snapshot is not a newly tested full-stack binary distribution. R1 Pro
simulation needs separately obtained, licensed, compatible local models. Public
source availability does not establish end-to-end compatibility on every platform.
The dependency-source build check does not certify bit-for-bit reproducibility of
host toolchains and all transitive dependency resolution.

Run `python3 maintenance/check_public_docs.py` from a populated quick-start workspace.
This checker is only a Markdown check, not a complete secret, media or license audit.
Keep credentials, locally imported models, caches and build products outside commits.
