# 可选 musl Mesa EGL 运行环境

原安装器设置 `MUJOCO_GL=egl`，使用宿主系统的 EGL。系统可以通过 Mesa
驱动 Intel/AMD，也可以通过 NVIDIA 的厂商实现提供 EGL；EGL 不等于 Mesa。

这里提供独立的 musl Mesa 构建和 Python 启动入口，并接入安装器的显式 `--musl` 选项。
默认安装路径仍保持 glibc；Release 组装与验证见 [可选 musl 安装包](../musl/README.md)。

## 驱动与运行时

默认构建 Mesa 25.2.7，启用 `llvmpipe,iris,crocus,radeonsi,nouveau`：

| 显卡/用途 | Mesa 驱动 | 条件 |
| --- | --- | --- |
| CPU 软件渲染 | llvmpipe | musl LLVM 等运行库 |
| Intel | iris / crocus | 型号受支持，宿主内核驱动、固件、DRM 设备权限可用 |
| AMD | radeonsi | 型号受支持，宿主 amdgpu/radeon 驱动、固件、DRM 设备权限可用 |
| NVIDIA 开源路径 | nouveau | 宿主使用 Nouveau；型号、固件与性能需单独验证 |
| NVIDIA 官方驱动 | 系统 EGL，使用 glibc Python | 不属于本 musl Mesa 构建；不能直接加载 glibc 用户态驱动到 musl 进程 |

Mesa 根据实际设备匹配驱动，不按照品牌强制指定 `GALLIUM_DRIVER`。
Nouveau 不能接管正由 NVIDIA 官方内核驱动使用的设备；本工具不会安装或替换内核驱动。
本组件提供 OpenGL/EGL 渲染，不包含 Vulkan、CUDA、OpenCL 或 GPU 物理计算后端。

## 构建

下载 [Mesa 官方 25.2.7 源码](https://archive.mesa3d.org/mesa-25.2.7.tar.xz)，
校验 SHA-256 为
`b40232a642011820211aab5a9cdf754e106b0bce15044bc4496b0ac9615892ad`，
然后解压到工作目录的 `mesa-25.2.7/`。以下命令从该工作目录执行：

```sh
docker build -t insightos-mesa-musl:25.2.7 /path/to/quick-start/artifacts/mesa
docker run --rm --network=none --cpus=6 --memory=14g \
  -v "$PWD:/work" \
  -e MESA_SOURCE=/work/mesa-25.2.7 -e MESA_OUTPUT=/work/output \
  insightos-mesa-musl:25.2.7
```

`output` 必须不存在。默认使用 3 个编译/测试进程；可以设置 `MESA_JOBS`。
`MESA_DRIVERS` 可显式选择构建的驱动列表，建议始终保留 llvmpipe。
输出包括 `prefix/` 和配置、编译、上游测试日志。
基础镜像固定 digest，APK 包使用 Alpine 配置的源；APK 版本并非全部锁定，
因此需保留实际版本清单，不宣称逐字节可复现。

prefix 仍依赖 LLVM、libdrm、libelf 等动态库。可以在同一个构建环境中执行：

```sh
python collect-runtime.py /work/output/prefix /work/output/runtime
```

该脚本检查 ELF 的 GLIBC 符号依赖并收集外部 musl 库，用于本地离线验证。
发布流程使用 [锁定的依赖 Release](../musl/releases.json) 及其许可证、源码对应关系和发布清单；此收集工具保留用于本地实验。
静态 ELF 依赖审计不能代替硬件驱动实际加载与渲染验证。

## 选择后端并启动

用**目标应用自身的 Python** 执行 `launch.py`，确保探测与应用使用相同解释器。
必须事先安装该解释器对应的 MuJoCo、NumPy、PyOpenGL 等依赖。

```sh
/path/to/musl/python artifacts/mesa/launch.py \
  --profile auto --mesa-prefix /path/to/output/prefix \
  --mesa-runtime /path/to/output/runtime --check

/path/to/musl/python artifacts/mesa/launch.py \
  --profile auto --mesa-prefix /path/to/output/prefix \
  --mesa-runtime /path/to/output/runtime \
  --report /path/to/render-report.json -- -m your_runtime_module
```

`--` 后是 Python 参数，不要再写一次 Python 可执行文件。

| profile | 行为 |
| --- | --- |
| `auto` | musl：遍历 Mesa EGL 设备，优先成功的硬件渲染，失败后用 llvmpipe；glibc：使用系统 EGL |
| `mesa-gpu` | 要求 musl Mesa 硬件渲染成功，否则报错，不接受软件渲染冒充 GPU |
| `software` | 使用 musl Mesa llvmpipe |
| `system` | 使用系统 EGL 和用户已有厂商配置，报告实际软/硬件渲染结果 |

多显卡可以用 `--device N` 指定 **EGL 枚举索引**，它不等于 CUDA 索引或 PCI 地址。
指定设备时不会自动回退到另一设备或软件渲染；不与 `software` 同用。
`system` 模式保留宿主厂商库配置；bundled Mesa 模式清除冲突的驱动覆盖变量。
库搜索顺序为 Mesa prefix、应用已有 `LD_LIBRARY_PATH`、Mesa 收集的外部依赖，
以保留应用已固定的 zlib 等共享库版本。
配置应在应用启动前选定，切换时重启进程，不能在已经导入 MuJoCo 的进程中切换。

每个候选设备在独立子进程中完成 RGB/深度渲染，记录 OpenGL vendor、renderer、
version、实际库路径与失败原因。单次探测超时为 30 秒。输出的 `software` 字段
表示检测到了 llvmpipe/softpipe 等软件渲染器，不用 `MUJOCO_GL=egl` 推断硬件加速。

在容器中测试 AMD/Intel 时，需要额外传入可访问的 `/dev/dri` 设备；
无设备的容器用于验证软件回退。普通用户还需宿主机对应的 render/video 组权限。

## 本地验证（2026-09-11）

| 检查 | 结果 |
| --- | --- |
| 五个 Gallium 驱动的源码构建 | 成功；Mesa 上游测试 72 passed，0 failed |
| 后端选择与依赖优先级测试 | 9 passed |
| Mesa 动态依赖审计 | 18 个 ELF 无 GLIBC 符号版本要求；收集 13 个外部 musl 库 |
| AMD 实机无头渲染 | Ryzen 9 9950X 核显，radeonsi，OpenGL 4.6；RGB/深度/物理检查通过 |
| 无 GPU 自动回退 | llvmpipe，OpenGL 4.5；RGB/深度/物理检查通过 |
| 单一 Python 联合测试 | 两种渲染模式均通过 MuJoCo 3.4.0、Pinocchio 3.9.0、Coal 3.0.2、Ruckig 0.19.4 联合检查 |

联合测试使用断网的全新 Python 3.13 Alpine 容器，NumPy 2.3.5；没有挂载宿主机图形库，
AMD 测试只透传相应 DRM 设备。检查实际加载的 Mesa 路径，并确保 Assimp、Qhull、
TinyXML2、zlib 从项目已发布的 Release 目录加载。
Intel 和 Nouveau 目前只有源码构建与上游测试结果，**尚未实机验证**。
NVIDIA 官方 EGL 路径没有通过本轮验证，也没有变成 musl 兼容路径。

本地完整源码构建使用已有 MuJoCo musl 工具链补充 Intel 编译依赖；本目录的
独立 Dockerfile 已完成镜像构建与同配置 Meson 配置检查。
Mesa prefix 约 47 MiB，收集的外部依赖约 177 MiB，仍为动态链接。
首次联合测试发现 Mesa 的 zlib 覆盖应用已固定版本；调整加载顺序后两种模式均复测通过。
这些组件测试不代表完整 installer、所有业务场景或显卡性能已完成验收。

## 参考

- [Mesa EGL 驱动架构](https://docs.mesa3d.org/egl.html)
- [Mesa 驱动环境变量](https://docs.mesa3d.org/envvars.html)
- [NVIDIA 官方驱动系统要求](https://download.nvidia.com/XFree86/Linux-x86_64/580.76.05/README/minimumrequirements.html)

## Reproduce from source and Releases

See the [three-platform build guide](../../README.build.md) for complete local/CI commands, pinned versions, output paths and all component/dependency repository recipes.
