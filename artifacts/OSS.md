# 阿里云 OSS 发布

真实下载根路径：`https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic`。
Endpoint：`https://oss-cn-shanghai.aliyuncs.com`；地域：`cn-shanghai`。

凭据配置位于仓库外：`~/.config/semantic-artifacts/oss.env`（目录 0700、文件 0600）。
客户端只解析 KEY=value，不执行 shell；拒绝仓库内凭据、符号链接凭据及权限过宽文件。
不要把 AccessKey 放入命令参数、README、安装脚本或发布归档中。

## 初次发布记录

以下为首次公开发布 .3 的历史记录；当前发布版本与最新验收结果见 [VERIFICATION.md](VERIFICATION.md)。

版本 `0.5.0-dev.20260910.3`，362387241 bytes，SHA256：
`ea6874612f8ac957adea6d2de18a4a6563b8a0acac67a7c042f88f1f18ba7fa8`。

```text
semantic/
├── install.sh
├── channels/stable.json
└── releases/0.5.0-dev.20260910.3/linux-x86_64/
    ├── semantic-0.5.0-dev.20260910.3-linux-x86_64.tar.gz
    ├── semantic-0.5.0-dev.20260910.3-linux-x86_64.tar.gz.sha256
    ├── manifest.json
    └── release.json
```

按用户明确要求，本批六个对象已从 private 改为 **public-read（匿名可读、写入需授权）**。
Bucket 原有 public-read 设置未改，未操作其他版本或对象。原始制品内容及 internal-only /
license pending 标识未改；公开读取的授权不等于已经完成第三方资产许可审查。

## 中国用户公开安装入口

```bash
curl -fsSL https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/install.sh | \
  bash -s -- --yes --install-system-deps
```

可以追加 `--dir /绝对路径` 或端口参数。不需要 AccessKey、签名票据或 GitHub 访问权限；
普通公开 URL 没有签名的一小时有效期限制。全球 GitHub Releases 入口尚未配置。

## 客户端

使用官方 OSS Python V2 SDK（本次验证版本 1.4.0），仅在构建/发布机运行：

```bash
# 只检查 Bucket 权限
uv run --no-project --with alibabacloud-oss-v2==1.4.0 \
  python artifacts/oss_client.py check

# 校验并公开上传指定版本，最后更新 stable 通道
uv run --no-project --with alibabacloud-oss-v2==1.4.0 \
  python artifacts/oss_client.py publish --version 0.5.0-dev.20260910.3 --allow-public-internal-assets

# 票据过期后重新签发，不重新上传安装包
uv run --no-project --with alibabacloud-oss-v2==1.4.0 \
  python artifacts/oss_client.py ticket --version 0.5.0-dev.20260910.3
```

配置字段：OSS_REGION、OSS_ENDPOINT、OSS_BUCKET、OSS_PREFIX、OSS_DOWNLOAD_BASE、
OSS_ACCESS_MODE、OSS_SIGNED_URL_TTL、OSS_ACCESS_KEY_ID、OSS_ACCESS_KEY_SECRET。
可通过 `--config /仓库外路径/oss.env` 切换配置。

上传使用文件白名单，不递归上传 artifacts 或工作区。上传前验证本地 SHA256/大小，
上传后检查远端长度、SHA256 元数据和对象 ACL。同版本不同内容拒绝覆盖；相同内容校验后跳过。
只有带本客户端管理标记的 install.sh / stable.json 可更新。更新前通过 GET 的 ETag 条件读取并校验旧文件，
备份至仓库外的 `~/.config/semantic-artifacts/backups/`（0600），重新检查 ETag 后再写入。
OSS 的 PutObject 不支持本客户端尝试的 `If-Match` 条件写入（实际返回 400 NotImplemented）；
因此这不是原子 CAS。本机通过文件锁串行发布，多机发布仍须由运维串行调度。
接口参数见 [OSS PutObject 官方文档](https://www.alibabacloud.com/help/zh/oss/developer-reference/putobject)。
每次运行默认把不含凭据和签名 URL 的日志写入 `~/.config/semantic-artifacts/logs/`（0600）。
不会自动上传配置、签名票据、日志或源代码，不修改 Bucket ACL。

## 可选的私有一键安装（不再是当前默认入口）

private 模式发布或显式执行 ticket 命令时，客户端生成两个仓库外文件：

- `~/.config/semantic-artifacts/download/download.json`：限时 GET URL、版本、SHA256、过期时间。
- `~/.config/semantic-artifacts/download/install-current.sh`：读取票据，下载并校验入口，再运行安装。

```bash
bash "$HOME/.config/semantic-artifacts/download/install-current.sh" --yes
# 可继续加 --dir /绝对路径、--install-system-deps、端口等安装选项。
```

默认有效期 3600 秒。安装目标机不需要 AccessKey；需要把票据及入口通过安全方式交付给目标机，
并在该机器重新生成正确的本地票据路径或直接运行：

```bash
bash install.sh --ticket /绝对路径/download.json --yes
```

这里的 install.sh 必须来自可信来源；生成的 install-current.sh 则会先验证入口 SHA256。
票据包含临时下载权限，持有者在过期前可下载制品；应按秘密文件处理，不提交 Git、不上传到 Bucket。
入口不会将长期 AccessKey 传给目标机。长期密钥轮换后需重新签发票据。

仓库外配置 OSS_ACCESS_MODE 已改为 public-read。后续发布当前仍标记为 internal-only 的制品，
仍须显式传 `--allow-public-internal-assets`。客户端不会在普通上传时静默迁移已有对象的 ACL；
本次六个对象的 ACL 迁移是用户明确授权后的单独操作。

官方参考：[OSS Python V2 SDK](https://www.alibabacloud.com/help/en/oss/developer-reference/2-0-manual-preview-version/)、
[限时签名下载](https://www.alibabacloud.com/help/en/oss/developer-reference/download-an-object-using-a-signed-url-generated-with-oss-sdk-for-python-v2)。

## 验证记录

- 制品、校验文件、两份版本清单、stable 通道与 install.sh 已从 private 改为 public-read；
  匿名 HTTPS 读取验证通过。ACL 操作日志在仓库外 `logs/oss-public-read-tkl1w6k8.log`。
- 经真实签名入口下载整个归档，SHA256 和逐文件校验通过；新目录初始化、Python 环境、
  Native MuJoCo 场景 smoke 通过。本次使用 --no-start，未启动 Server/Web 或真实 Robot。
- 测试实例在验证后由卸载器清理，不涉及已有部署。
- 长期凭据从未复制入源码树或发布白名单；临时票据也只保存在仓库外。
