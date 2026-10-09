# LIBERO extension scenario — user manual

**English** | [简体中文](README.zh-CN.md)

LIBERO is a tabletop manipulation benchmark (robosuite 1.4, Franka and SmolVLA). This manual takes
you from zero to a running LIBERO scenario inside Semantic, then through the web Studio. It follows
one path:

```text
① Environment preparation → ② Install into the framework → ③ Reproduce in the web Studio
```

> Once the base environment is installed, the LIBERO code artifacts are **self-contained**: no
> engine image required. The **scene dataset is not distributed with this channel** — you obtain
> `libero-scenes.zip` yourself under the upstream license (see [1.2](#12-scene-dataset-and-model-weights)).

---

## 0. End-to-end overview

```text
① Base environment   install.sh (no extension) → usable Server + Studio
② Install LIBERO     install.sh --extension libero --extension-project <PROJECT-ID>
③ Web reproduction   scene configuration → add a compatible scene; project content → bind ability and model; device centre → install the Robot Skill (physical hosts also need a join code)
④ Acceptance         pick an initial state → start the scene → robot online → dispatch the expected robot skill
```

Fixed installation order: **runtime → scene catalog → robot base → ability → model → skill**. The
robot base (Bundle) is the foundation; the last three plug into it, so the reverse order does not
work. The manifest enforces this order and `install.sh` / `semanticctl` follow it automatically.

---

## 1. Environment preparation

### 1.1 Hardware and system

| Item | Requirement | Notes |
|---|---|---|
| CPU / memory | 16 GB RAM or more recommended | Integrated graphics works; inference is just slower |
| Disk | about **25 GB** free | six artifacts total about 11.5 GB, plus an unpacked copy |
| GPU | optional; a discrete GPU is faster | **Integrated graphics works**: CPU inference has automatic thread tuning (`OMP_NUM_THREADS`, etc.) |
| Network | access to OSS (default channel) | on the GitHub channel the three largest artifacts still fall back to OSS, so use `--extension-package-dir` for a fully offline install |

### 1.2 Scene dataset and model weights

**Scene dataset (you provide it — and build it).** The LIBERO scene dataset (`libero-scenes.zip`)
is an upstream third-party asset and is **not distributed with this channel** (neither OSS nor
GitHub Releases), and the upstream benchmark does not ship a ready-made zip either. Build it from
the pinned upstream commit with the packaging tool bundled in the mujoco-runtime repository
(~239 MB; upstream is MIT-licensed and its LICENSE rides along in the package):

```bash
# 1. Clone the upstream benchmark and check out the locked commit (the authoritative pin is
#    libero.commit in mujoco-runtime/profiles/sources.lock.yaml; use a proxy/mirror if GitHub
#    is unreachable)
git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git
git -C LIBERO checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01

# 2. The build enumerates the upstream task catalog, so it needs an importable LIBERO
#    environment (pulls in robosuite/mujoco, a few minutes)
python3 -m venv ~/.venvs/libero-build && source ~/.venvs/libero-build/bin/activate
pip install -e ./LIBERO pyyaml

# 3. Build the scenes package with the bundled tool
git clone https://github.com/insightos-community/mujoco-runtime.git
python3 mujoco-runtime/tools/libero_packages.py \
  --source "$PWD/LIBERO" --output ~/libero-packages/libero-scenes.zip --version 1.0.0
```

Put the built zip in a local directory, then install fully offline (channel artifacts are verified
byte-for-byte against the manifest sha256/size; your own scenes zip is not digest-pinned — the
importing command validates its content):

```bash
install.sh --extension libero --extension-package-dir ~/libero-packages
```

**Model weights (the only other external dependency).** SmolVLA weights come from HuggingFace.
**huggingface.co is unreachable from mainland China**; use a mirror (a proxy or the mirror, either
one):

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 1.3 Ports

| Purpose | Default | Decided by |
|---|---|---|
| LIBERO runtime | `8092` | manifest `runtime.endpoint` (different from the base environment's native-mujoco `8036`, so both can coexist) |
| Ability range | `18100–18199` | `ability_port_first` / `ability_port_last` in `semantic-server.yaml` |
| Server HTTP / WS | `8034` / `8035` | `semantic-server.yaml` |
| Web front end | `3000` | `semantic-web` |

> **BEHAVIOR and LIBERO on one host** both default to `18100–18199`. Allocate different ranges, or you
> will see `http server bind ... failed`.

---

## 2. Install into the framework

> **First time? Create a Project first.** A fresh instance has no Project, and extension components
> must install into a `mode=development` Project (otherwise the install fails with
> `无法在 Server 上找到可用 Project`). Sign in to the web Studio as described at the start of
> section 3, create a Project from **Projects** on the left, copy its project ID, and pass it to
> `--extension-project`.

Same entry script as the base install; it continues into the extension once the base environment is
ready:

```bash
curl -fsSL https://semantic.insightos.cn/install.sh | bash -s -- \
  --extension libero --extension-project <PROJECT-ID> --install-system-deps
```

| Flag | Purpose |
|---|---|
| `--extension libero` | select the scenario (required) |
| `--extension-project <PROJECT-ID>` | target project; defaults to the current user's Default Project (component install requires `mode=development`) |
| `--extension-source oss\|github` | channel, default `oss` |
| `--extension-package-dir <dir>` | install **fully offline** from the six artifacts plus the manifest |
| `--extension-manifest <file>` | override the manifest source with a local file |
| `--extension-dry-run` | print the command plan without changing anything |

Once the base environment is installed, preview the plan first (dry-run prints
commands only and changes nothing):

```bash
semanticctl extension install libero --dry-run
# with an offline directory, validate it too: semanticctl extension install libero --dry-run --extension-package-dir <dir>
```

With the base environment already installed, the bundled manager works too:

```bash
semanticctl extension list
semanticctl extension show libero        # artifacts, sizes, order, license
semanticctl extension verify libero      # download and verify only, no install
semanticctl extension install libero --project <PROJECT-ID>
```

> If `semanticctl` is not on your PATH, first `export PATH="$HOME/.local/share/semantic/bin:$PATH"`
> (use your actual dir when you passed `--dir`); the base install prints these two lines and tells you
> to persist them. See the entry point.

---

## 3. Reproduce in the web Studio

The base install creates the administrator `admin` with a random password stored as
`SEMANTIC_ADMIN_PASSWORD` in `configs/secrets.json`; `semanticctl welcome` prints the file location:

```bash
"$HOME/.local/share/semantic/bin/semanticctl" welcome
```

Open the web Studio (default `http://127.0.0.1:3000`), sign in as `admin`, and open the target
project. Three steps are required in the web Studio — add a compatible scene, bind the ability and
model, and install the Robot Skill on the robot — before a scene can run (a physical robot host
additionally needs the one-time join code in 3.3).

### 3.1 Scene configuration → add a compatible scene

Installation only registers the scene in the **scene catalog**; it does not add it to the project. In
Studio, open **Scene → Project scenes** on the left and click **Add** (or **Browse scenes** when the
panel is empty):

![Click Add in the project scenes panel](../images/libero/step-1-scene-panel.png)

In the **Add compatible scene** dialog, click the scene card you want (for example
`libero-spatial-0`), then **Add to Project**:

![Select a scene card and Add to Project](../images/libero/step-2-add-scene.png)

> **Do not generate previews for everything.** The manifest holds 130 tasks / 6500 initial states;
> without limiting `--scene`, previews are generated for every initial state, which is very slow. Add
> only the cards you need. When free VRAM is below 6144 MiB the installer **automatically** skips
> preview generation (no flag needed); to control it yourself, pass `--no-previews` to
> `semanticctl extension install`.

After adding, the scene appears under **Project scenes**. The **Runtime** row confirms `LIBERO / LIBERO-Pro`, and the initial states of the task are ready to start:

![The LIBERO scene running in Studio](../images/libero/overview.png)

### 3.2 Project content → bind the ability and model

Installation **imports** the ability and model into the project but **does not bind them to the
robot**. Without binding, the ability stays in `Standby` (`abilityPort: 0`) until it times out, the
Pilot stays `offline`, and the device page shows no executable robot.

1. In Studio, open **Project → Import project content** and scroll the dialog to the **Robot and
   model configuration** section at the bottom:

   ![Robot and model configuration in Import project content](../images/common/step-2-bind.png)

2. On a robot card, click **Select ability / model** (to make the current choice the default for
   future robots instead, click **Set project default** in the top right);
3. In the dialog choose, in order, **robot model** `franka_panda` → **ability (one implementation per
   role)** → **policy model** (e.g. SmolVLA, package `franka-smolvla-model`), then click **Save
   binding**;
4. With a robot already present, back on that robot's card click **Apply now / retry** — this **stops
   and restarts that robot's components once** (the scene keeps its current state), so confirm the
   robot is idle first. **On a fresh project with no robot yet, skip this step**: the binding takes
   effect automatically when the robot registers (clicking it now only yields "当前项目中没有该受管
   Robot").

**Done when**: the card's "pending configuration" and "running model" agree and it no longer sits in
`Standby`. A project default only applies to **future first-time bindings**; each robot's own choice
is stored independently.

### 3.3 Device centre → install the Robot Skill (simulated robots need no join code)

**Simulated robots register with the scene.** For simulation scenes such as LIBERO, the Server brings
the robot (e.g. `franka-0`) online automatically when the scene starts in 3.4 — **no one-time join
code is needed**; the join-code flow below is for **physical robot hosts**. Once the simulated robot
is online there is exactly one thing left to do here, because it does not pick up the Robot Skill by
itself:

1. After starting the scene (3.4), open **Device centre** and confirm `franka-0` is online with the
   AbilityFramework ready;
2. On the `franka-0` device page, install the `vla-manipulation` Skill (the version imported by the
   extension install);
3. With the Skill enabled, dispatch the task as in 3.4.

The physical-host onboarding flow follows below.

Open **Device centre** (top menu `Device / Device centre`) and click **Add Pilot**:

![Click Add Pilot in the device centre](../images/common/step-3-devices.png)

Note that **"Add Pilot" does not add a robot directly**: it only mints a one-time join code, and the
robot is registered only after you run the launcher on the **robot host** and the launcher exchanges
that code for a credential.

1. The dialog shows the **one-time join code** (6 digits, valid about 5 minutes, claimable only once)
   and a launcher command; click **Copy command** to take both (do not commit the join code or the
   later credential to a repository):

   ![Copy the one-time join code and launcher command](../images/common/step-4-add-pilot.png)

2. On the **robot host**, run that command in the foreground and keep it running (replace
   `<robot-id>` with the actual robot):

   ```bash
   semantic-robot-instance start --config /etc/semantic/robots/<robot-id>/robot-deployment.yaml --join-code <JOIN-CODE>
   ```

   The launcher discovers the Server over the LAN (mDNS service `_semantic-server._tcp`; mDNS is
   often unavailable on container networks, so you may append
   `--server-http http://<server>:8034 --server-ws ws://<server>:8035/ws/pilot`), exchanges the join
   code for that Pilot's dedicated credential and stores it on the robot host (in the instance
   directory's `connection.yaml`, mode `0600`), then starts **AbilityFramework → the seven ability
   classes → Pilot** in order, after which the Server reconciles and dispatches the expected robot
   skill.
3. Back in the dialog, click **Done** — it only closes the dialog; pairing completed the moment the
   launcher claimed the join code. After a moment the robot should appear in the device list with
   connection **online**.

Restarting the robot afterwards **no longer needs a join code** (the credential is already on the
robot host):

```bash
semantic-robot-instance start --config /etc/semantic/robots/<robot-id>/robot-deployment.yaml
```

Check the instance state itself:

```bash
semantic-robot-instance status --instance ~/.local/state/semantic/robots/<robot-id>
# expect status: running, a non-zero pilot_pid, and 7 ability_instance_ids
```

> **Pilot online ≠ robot executable.** If the Pilot shows online but the robot is not executable,
> keep checking the expected/actual state of AbilityFramework, the seven ability classes and the robot
> skill, plus project occupancy — do not watch only the Pilot heartbeat.

### 3.4 Acceptance

Accept the result in this order (screenshots above):

1. the scene is under **Project scenes** — you can pick an initial state and start the scene;
2. the robot appears in **Device centre** with connection **online** and a status other than `degraded`;
3. dispatching the expected robot skill shows events under **Current execution / Execution history**.

---

## 4. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Runtime install failed: ... requires content ...` | the runtime package is missing content; LIBERO does not need `--asset-root`, so do not pass an empty value |
| `http server bind ... failed` | the ability port range collides with another scenario; give each environment its own range |
| The project does not show the scene | the compatible scene was never added (3.1) |
| The robot stays `offline` / the ability stays `Standby` | the ability and model were not bound (3.2), or no Pilot was added (3.3) |
| Model download fails | huggingface.co is unreachable; set `HF_ENDPOINT=https://hf-mirror.com` |
| Preview generation is extremely slow | previews for all 6500 initial states; add only the needed scenes, or pass `--no-previews` to `semanticctl extension install` |

For troubleshooting and acceptance you can verify without installing:

```bash
semanticctl extension verify libero --source oss
```

---

## 5. Uninstall

Stop the scene and the robot first, then remove the extension. The base environment's native-mujoco
runtime is unaffected (`installation_id` and endpoint are independent):

```bash
semanticctl extension remove libero
```

---

## Reference

### The six artifacts

| Role | Artifact | Size | Channel |
|---|---|---|---|
| `runtime` | `semantic-libero-robosuite-1.4-0.4.0-dev.0.runtime.tar.zst` | about 2.2 GB | OSS + GitHub |
| `scene_catalog` | `libero-scenes.zip` | about 239 MB | **not distributed — you provide it** (see [1.2](#12-scene-dataset-and-model-weights)) |
| `robot_base` | `franka-libero-robot.zip` | about 2.9 GB | OSS only (>2 GiB) |
| `robot_ability` | `franka-ability.zip` | about 2.9 GB | OSS only (>2 GiB) |
| `model` | `franka-smolvla-model.zip` | about 3.3 GB | OSS only (>2 GiB) |
| `robot_skill` | `vla-manipulation.zip` | about 12 KB | OSS + GitHub |

The runtime `installation_id` is `local-libero-robosuite-1.4` and its endpoint is fixed at `8092`.

### License

LIBERO is an upstream third-party benchmark (`github.com/Lifelong-Robot-Learning/LIBERO`). Its scene
dataset is **not redistributed through this channel** — you obtain it separately under the upstream
license, the same principle as the BEHAVIOR dataset. The `license` field on the code artifacts makes
the installer add `--accept-license LIBERO` automatically (you may also pass it explicitly).
"Downloadable" does not mean freely redistributable; do not upload the scene dataset to OSS or a
GitHub Release either.

### Design

Manifest structure, channel layout and the release flow are in
[`../../docs/extensions.md`](../../docs/extensions.md); the entry point and directory convention are
in [`../README.md`](../README.md).
