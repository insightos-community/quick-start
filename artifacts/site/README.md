# Semantic installation website

Public entry: <https://semantic.insightos.cn/>. This is a static bilingual landing page, not a Semantic Server deployment. It uses no external fonts, analytics, or JavaScript CDN.

## Files and language selection

Publish only `index.html`, `style.css`, `site.js`, `favicon.svg`, `brand-logo-aa437690722d.png`, `install.sh`, and `install-en.sh` into the web root. Do not upload the whole artifacts workspace, environment files, credentials, signing material, or private deployment records.

The language selector supports `?lang=zh|en`, a saved preference, and browser language, in that order. Without JavaScript the Chinese page and native video remain usable.

```bash
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --install-system-deps
```

On Linux, the English script defaults to the verified GitHub `v0.1.0` installer Release; on macOS it selects the native preview. `--version 0.1.0` (or `v0.1.0`) selects an explicit tag; `--package` and an explicit `--base-url` remain available. `SEMANTIC_DOWNLOAD_BASE` does not change the English default. Release metadata, platform, source commit and SHA-256 are checked before execution.

Complete Releases already contain the Git LFS model objects. If an asset is missing or is a pointer, the English bootstrap uses the asset repository commit in `release-lock.json`, reads its GitHub pointer and downloads the object through the [Git LFS Batch API](https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md). Both object size and SHA-256 must match the original `files.json`; the archive and integrity inventory are never rewritten. No Git or Git LFS executable is needed on the installation target.

System dependencies use the target machine's existing apt/dnf/yum/pacman/zypper or Alpine APK configuration. The English manager also preserves uv user configuration and package-index environment variables. It does not write repository lists, install mirror configuration, or select a different package index. Bundled wheels remain installed offline with `--no-index`.

The corresponding Chinese entry is `/install.sh`. Both pages describe Linux x86_64 (glibc/musl) and native macOS 15.5+ Apple Silicon arm64, with the qualification boundaries below. Other package-manager support does not imply full validation of every distribution.

Both languages also state that more Linux distributions will be tested soon and compatibility results will be updated. This is a validation plan, not an expansion of the currently verified platform list.

## Platform and tag selection

The homepage has a platform selector and tag input. Language switches keep the
selected platform/tag and regenerate the corresponding `/install.sh` or
`/install-en.sh` command. Invalid or mismatched tags disable copying; user input
is never inserted as HTML or executable shell syntax. Static musl/macOS examples
remain available without JavaScript.

| Platform | Verified tag | Source | Target requirements |
|---|---|---|---|
| Linux glibc x86_64 | `v0.1.0` | GitHub Release; untagged Chinese `stable` retains the separate OSS channel | Python 3.10+, glibc >=2.28 |
| Linux musl x86_64 | `musl-v0.1.0-2` | GitHub Release; no OSS manifest currently exists | Bundled musl by default; host mode requires a musl loader |
| macOS arm64 | `macos-v0.1.0-rc.3` | GitHub Release; no OSS manifest currently exists | Apple Silicon, macOS 15.5+; bundled Python, no Homebrew |

```bash
# English; replace install-en.sh with install.sh for the Chinese entry.
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --source github --tag v0.1.0 --install-system-deps
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --source github --tag musl-v0.1.0-2 --musl-runtime bundled --install-system-deps --dir "$HOME/semantic-musl"
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --source github --tag macos-v0.1.0-rc.3 --dir "$HOME/semantic-macos"
# The existing Linux OSS channel is available from either language entry.
curl -fsSL https://semantic.insightos.cn/install-en.sh | bash -s -- --source oss --version stable --install-system-deps
```

`--tag` infers the target platform and cannot be combined with `--version`.
`--source auto|github|oss` selects the download route. Explicit tags default to
GitHub; without a tag, the Chinese Linux default stays OSS and English stays
GitHub. The OSS stable channel and GitHub v0.1.0 are separate distributions.
Linux custom `--base-url` and private tickets remain supported. macOS rejects
explicit OSS inputs until corresponding artifacts exist; it uses the embedded
native bootstrap before testing for a host Python. Offline `--package` /
`--sha256` remains supported. Native macOS uses the release's installer UI.

The musl guide retains bundled/system loader selection, Mesa GPU/software
selection and validated-driver boundaries. Older musl tags may require a musl
host and system mode; do not assume they include the bundled loader introduced
in `musl-v0.1.0-2`. macOS uses CGL with Web requests set to auto; physical GPU
rendering remains unqualified. Versions/platforms require separate install
directories; stop an old instance before reusing its ports. Existing databases
are not migrated automatically. Linux Web defaults to all interfaces; macOS
Web defaults to localhost.

## Installer generation

`artifacts/install.sh` is the canonical unified bootstrap. `artifacts/platform_bootstrap.sh` and `artifacts/macos/bootstrap.sh` generate its native macOS dispatch; `artifacts/github_bootstrap.py` supplies the Linux Release/LFS helpers. Run `python3 artifacts/build_installers.py` to generate both repository-root scripts and `artifacts/install-en.sh`. The English generator uses `artifacts/installer.en.json`; do not maintain a second installation implementation by hand. Publish the root `install.sh` and `install-en.sh` to the matching website paths.

The English bootstrap validates the original payload checksum and extracts it safely before running translated management modules from a separate temporary directory. It does not modify the verified archive. Installed management commands retain English messages; upstream package-manager and application logs remain in their native language.

## Video

The page uses HTML5 `<video controls playsinline preload="none">`. No autoplay or third-party player is required; playback and seeking fetch the media directly from OSS.

- [Chinese demo](https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/media/semantic-install-d282bc52483d.mp4)
- SHA-256: `d282bc52483d0a94778311f537eb6541732e221fc8ada1b04ba899713fa681e5`
- [English demo](https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/media/semantic-install-en-03290f9242db.mp4)
- SHA-256: `03290f9242db4bcd1649cd57e4d1e26ad82fd6e2b6dc402bb5b929f042890c1e`; 3,272,162 bytes.
- H.264, 1920×1080, approximately 35 seconds, no audio.
- Public-read playback; writes require authentication. The public URL has no expiring signature.
- Use content-hash object names and immutable caching; publish a new object when replacing the demo.
- Language selection switches both the recording and the direct viewing link. Switching to another recording pauses/resets playback; selecting the same language leaves playback alone.
- `preload="none"` is a browser hint. Browsers may still request media data when the selected source is reloaded; playback never starts automatically.

Keep the video out of Git and the web server's static directory. Restrict CSP `media-src` to the configured media host.

## Copyright and filing information

Both language versions retain the supplied Chinese legal notice: `Copyright © 上海具识智能科技有限公司版权所有`, `沪公网安备31011502404136号`, and `沪ICP备2025112430号`. The filing links lead to the official public-security and ICP portals.

The public-security filing icon is loaded from <https://assets.insightos.cn/assets/images/guohui.png>, with an accessible label and fixed 20 px display size. CSP permits images from that asset host only in addition to same-origin images. Legal text and the icon remain visible on narrow screens and without JavaScript.

## Deploy and verify

Adapt [compose.yaml](compose.yaml), [nginx-static.conf](nginx-static.conf), and [nginx-edge.conf](nginx-edge.conf) to your own server, network, image, TLS certificate paths, and domain. These templates still require deployment-specific configuration; do not assume an existing private environment is available.

Before publishing, from the quick-start root:

```bash
bash -n install.sh
bash -n install-en.sh
python3 artifacts/build_installers.py --check
node --check artifacts/site/site.js
```

Back up the current public files and configuration privately. Copy only the public allowlist. Validate Nginx configuration before reloading the affected service. When configuration is a single-file bind mount, preserve the mounted inode or explicitly recreate the mount.

Verify HTTPS, both installer hashes, content types, unknown-path rejection, and that configuration and credential paths are inaccessible. Test language selection, copy buttons, narrow screens, video playback, and seeking.

`tests/test_artifact_site.cjs` provides browser checks with Playwright/Chrome and supports `SEMANTIC_SITE_URL`. Deployment credentials, machine addresses, backup locations, and rollback records belong in a private operations system, not this repository.

The bilingual-video/footer update was verified locally and on the public site at 1440, 768, 390, and 320 px: both recordings play and seek, language switching resets only a different recording, the filing icon loads under CSP, and the legal footer remains available without JavaScript. The English OSS object passed SHA-256 verification and a Range/206 request. Installer contents and the business artifact release were unchanged.

See [installer management](../README.md), [OSS publishing](../OSS.md), and [verification history](../VERIFICATION.md).
