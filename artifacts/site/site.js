// Copyright 2026 InsightOS
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use strict";
// Translations are trusted, static site copy. Never insert URL or user input as HTML.
const englishCopy = {
  windowsSteps: "① Download the ZIP and checksums → ② Verify and extract completely → ③ Open CMD in the extracted folder and run the installation command below.",
  windowsZip: "Download Windows ZIP ↗",
  windowsVerify: "First use PowerShell to calculate the ZIP SHA-256 and compare it with the matching filename in SHA256SUMS:",
  windowsTagNote: "Choose a published windows-v tag available from the selected source. Chinese uses OSS; English uses GitHub. Switch to English for versions not yet mirrored.",
  portsTableTitle: "Component TCP ports",
  portsScroll: "Scroll the table horizontally for listen addresses and YAML settings →",
  stepNetwork: "Web defaults to port <code>3000</code>; API / WS communication stays local. To avoid port conflicts or enable LAN access, see the <a href=\"#ports\">port table and configuration guide below ↓</a>.",
  portsTitle: "Ports and configuration.",
  portsIntro: "Check port availability before installation and configure with one YAML file.<br>Component connections and discovery addresses update together.",
  portTableLabel: "Component ports table, scroll horizontally",
  portsCaption: "Default TCP ports for new installations. Existing instances keep their configuration; export it to check actual values.",
  portComponent: "Component / purpose",
  portDefault: "Default port",
  portBinding: "Listen address",
  portKey: "YAML settings",
  portWeb: "Browser console entry point",
  portWebBinding: "Linux: <code>0.0.0.0</code><br>macOS / Windows: <code>127.0.0.1</code>",
  portHttp: "Application and task API",
  portWs: "Live status and events",
  portRuntime: "Listens when the simulation runtime starts",
  portAbility: "Allocated per Robot instance",
  portsScope: "The Ability range is allocated on demand; all 100 ports are not occupied at once. <code>127.0.0.1</code> is local only; <code>0.0.0.0</code> listens on all IPv4 interfaces. Expose Web only to trusted networks. API, WS and Runtime do not need LAN access.",
  portsConflict: "The installer checks for port conflicts before installation and never terminates other programs. If a port is occupied, edit the configuration and retry; verified archives are reused from cache. The four service ports must be distinct, within 1024–65535, and outside the Ability allocation range.",
  configTitle: "Install and reconfigure with YAML",
  configPlatformLink: "Select platform and version ↑",
  configIntro: "Commands below follow the platform, tag and page language selected above. Run them from the same working directory and replace <code>--dir</code> with your actual instance directory. To reconfigure an existing instance, use its original directory.",
  configExportTitle: "Export the configuration",
  configExport: "A new directory exports defaults; an existing instance exports its current values. This only fetches the small entry script, without downloading the full installer archive. Export never overwrites a file; choose another filename when exporting again.",
  configCopy: "Copy",
  configEditTitle: "Edit the ports you need",
  configEdit: "Open <code>components.yaml</code> in a text editor. For example, change <code>web_port: 3000</code> to <code>web_port: 33000</code>, then visit <code>http://127.0.0.1:33000</code> after applying it. The template below shows new-install defaults for the selected platform; use exported values for existing instances.",
  configRules: "Keep the flat <code>key: value</code> format. Comments are supported; nested mappings, anchors, unknown or duplicate keys are not. Explicit command-line options override YAML. Unspecified values retain existing settings, or use defaults for new instances. No passwords or tokens are included.",
  configInstallTitle: "Install using the configuration",
  configInstall: "For a new installation, load the file with <code>-f</code> alongside the platform, release tag and download source options. System dependencies use your machine’s existing package repositories.",
  configTagError: "Select a valid platform and release tag above before copying the install command.",
  configReconfigureTitle: "Already installed? Reconfigure it.",
  configReconfigure: "Stop scenes and Robot Runtime first, export and edit the current configuration, then run the command below. Skip the installation step: no full archive download is needed. The application version, data and credentials are preserved. This entry also supports older management tools.",
  configSync: "Reconfiguration checks ports, backs up configuration, updates Server, Web proxy, Robot / Pilot connections and MuJoCo discovery addresses, then restarts affected services. If startup fails, the original configuration is restored. Applied settings are saved in the instance’s <code>configs/components.yaml</code>, with backups under <code>configs/reconfigure-backup-*</code>.",
  configAbilityLimit: "Once Robot configurations exist, changing the Ability allocation range requires a new installation directory. Other component ports can be reconfigured as shown above.",

  home: "Semantic home",
  navigation: "Main navigation",
  navProduct: "Product",
  navGuide: "Deploy guide",
  navInstall: 'Install <span aria-hidden="true">↗</span>',
  headline:
    'From semantics<span class="comma">,</span><br>to <span class="accent">action.</span>',
  intro:
    '<span class="hero-copy-line">A robotics application stack, installed with one command.</span><span class="hero-copy-line">From orchestration to simulation, bring your ideas to life.</span>',
  platformLabel: "Installation platform",
  uninstallFallback: "For older or incomplete installations, fetch the small entry script to uninstall. It does not download the full archive:",
  tagLabel: "Release tag / default channel",
  tagHelp: "stable keeps the default Linux channel; enter a Release tag to pin a version. Chinese commands use OSS mirrors; English uses GitHub Releases.",
  macosTitle: "Native macOS installation (Apple Silicon)",
  macosIntro: "Requires macOS 15.5+ on Apple Silicon arm64. Use the same entry script and select a macOS Release with <code>--tag</code>. English downloads use GitHub Releases; Chinese commands use the identical OSS mirror. Both verify SHA-256.",
  macosRuntime: "Bundles Python 3.13.15, NumPy 2.3.5, MuJoCo and robot dependencies. No Homebrew or host Python is required. Web requests auto and the Runtime uses configured CGL. This preview is not notarized; physical GPU rendering still needs testing.",
  macosUpgrade: "Stop the old instance before installing another tag into a new <code>--dir</code>, then reload the browser. The installer neither overwrites other versions nor migrates databases automatically; old configuration and data remain in the original directory.",
  macosRelease: "<a href=\"https://github.com/insightos-community/quick-start/releases/tag/macos-v0.1.0-rc.5\">macos-v0.1.0-rc.5 ↗</a> · Approx. 412 MiB · Installation, API, physics and lifecycle checks passed.",
  terminal: "<span class=\"terminal-dot\"></span> Run on the target machine",
  downloadRegion: "Downloads via GitHub Releases",
  viewScript: "View installer ↗",
  supportNote: "Linux x86_64 (glibc / musl) · Native macOS 15.5+ Apple Silicon / Windows x64 preview",
  supportRoadmap:
    "More Linux distributions will be tested soon, with compatibility results published as validation progresses.",
  installNote:
    "Linux requires Bash, curl and Python 3.10+. macOS uses bundled Python; no Homebrew is needed. Select a platform and tag, then copy the command.<br>Archives are SHA-256 verified. System dependencies use your existing package repositories.",
  preview: "Developer preview",
  downloadSize: "Download size varies by platform and version",
  muslTitle: "musl runtime: bundled or system (optional)",
  muslIntro: "On Linux x86_64, <code>--tag musl-v0.1.0-3</code> selects the musl package automatically; the existing <code>--musl</code> option remains available. Bundled musl works on glibc hosts too; use a separate directory.",
  muslRuntime: "<code>--musl-runtime bundled</code> uses the included musl 1.2.5; <code>--musl-runtime system</code> uses the host musl 1.2+ loader. Includes CPython 3.13.15, NumPy 2.3.5, robot libraries and Mesa, without source compilation. System /lib and package repositories are unchanged; use a new directory to switch runtimes.",
  muslRender: "By default, a working Mesa GPU is selected, with software rendering as a fallback. Add <code>--render-backend software</code> to force software rendering, or <code>--render-backend mesa-gpu</code> to require hardware rendering. AMD has been tested; Intel / Nouveau still need hardware validation. Use the default glibc installer for proprietary NVIDIA drivers.",
  muslRelease: 'Optional prerelease <a href="https://github.com/insightos-community/quick-start/releases/tag/musl-v0.1.0-3">musl-v0.1.0-3 ↗</a> · Approx. 626 MiB · Offline installation and software rendering verified on Ubuntu 22.04 / Alpine 3.23.',
  demoTitle: "See the installation in action",
  demoLength: "35 seconds · 1080p · Silent",
  videoLabel: "Semantic installation demonstration",
  videoFallback:
    "Your browser does not support embedded video. Use the link below to watch.",
  demoCaption:
    "Installation confirmation, task progress and opening the console. The recording is condensed; actual installation time varies.",
  videoLink: "Watch in a new window ↗",
  videoError:
    "Video could not load. Check your connection or watch using the link above.",
  flowLabel: "Semantic execution stack",
  flowServer: "Applications and task orchestration",
  flowWeb: "Visual management console",
  flowRobot: "Abilities, skills and simulation",
  stackTitle: "The complete stack. Ready together.",
  stackIntro:
    "Download prebuilt artifacts. No source checkout or compilation<br>on the target machine. Stay focused on your robots.",
  cardServerTitle: "Server and console",
  cardServer:
    "Deploy Semantic Server and the production Web console together. Initialize an administrator account and manage applications, projects and tasks in one place.",
  cardRobotTitle: "Start with simulation",
  cardRobot:
    "Includes Native MuJoCo Runtime and the R1Pro Robot Bundle. Initialize the runtime, then configure scenes and tasks from the console.",
  cardManageTitle: "Inspect and manage",
  cardManage:
    "Verified archives, isolated instance directories, diagnostics and file logs. Uninstall while keeping data, or explicitly confirm a complete removal.",
  guideTitle: "Get up and running.",
  guideIntro:
    "Linux defaults to <code>~/.local/share/semantic</code>; macOS to <code>~/Library/Application Support/Semantic</code>. Run installation commands on your own machine.",
  stepInstallTitle: "Choose a directory and install",
  stepInstall:
    "The command above asks for confirmation. Add <code>--yes</code> for unattended installation; use an absolute path for a custom directory.",
  stepPackages:
    "Linux supports apt-get, dnf/yum, pacman, zypper and APK, using existing repositories. macOS bundles its dependencies and needs no package manager.",
  stepWebTitle: "Open your console",
  stepWeb:
    "Open <code>http://127.0.0.1:3000</code> and sign in as <code>admin</code>. The random password appears in the interactive terminal and is saved to <code>configs/secrets.json</code> in the instance directory, never to installation logs.",
  stepManageTitle: "Check services and configure tasks",
  stepManage:
    "Replace these paths if you chose a custom directory. The default model is a mock; configure a real model separately. Installation does not create application tasks or start physical robots.",
  requirementsTitle: "Check first. Deploy next.",
  requirementsIntro:
    "Separate installer distributions support Linux x86_64 glibc/musl and native macOS Apple Silicon arm64 / Windows x64. Each uses its own runtime and dependency set; binaries are not interchangeable.",
  validatedTitle: "Verified operating system",
  validated: "Ubuntu 24.04 (glibc); Ubuntu 22.04 / Alpine 3.23 (musl); macOS 15.5+ Apple Silicon (installation, API and physics checks)",
  compatibilityTitle: "Compatibility limits",
  compatibility:
    "glibc baseline ≥ 2.28; musl is bundled by default, while system mode needs host musl 1.2+. macOS uses system CGL; physical GPU rendering still needs validation. Intel Mac and Linux ARM64 are not supported. Windows x64 has a separate ZIP preview; see below.",
  updatesTitle: "Downloads and updates",
  updates:
    "Chinese installation uses Aliyun OSS mirrors; English uses GitHub Releases. All four platforms have identical GitHub/OSS archives and checksums; Windows uses a separate ZIP installer. The OSS glibc stable channel now selects GitHub v0.1.0. Install other versions/platforms into a new directory and migrate data explicitly.",
  faqTitle: "Frequently asked questions",
  faqAppsTitle: "Where are the app icons and system uninstall entries?",
  faqApps: "New installers include the InsightOS icon and app entries. Linux adds application-menu entries and desktop shortcuts on graphical desktops. macOS creates Semantic and Uninstall Semantic apps in your user <code>~/Applications</code> folder and registers them with the system app launcher. Windows adds Start menu and desktop shortcuts, plus an entry in Settings → Apps → Installed apps. Opening Semantic starts services and opens the Web console using its current configuration.",
  faqAppsUninstall: "Stop scenes and Robot Runtime before opening Uninstall Semantic. Windows also supports removal from Installed apps. Configuration, data and logs are kept by default; no installer archive download is needed. On macOS, moving only the Semantic launcher to Trash does not remove the runtime; use the uninstall app.",
  faqAppsRefresh: "Existing Linux / macOS installations can refresh management tools and create app entries with the command below, without upgrading application components or downloading the full archive. Stop scenes first and replace the directory with your actual installation path; the example follows the platform selected above. Use <code>--no-desktop-shortcut</code> during installation to skip app entries.",
  faqWindowsChecksum: 'In PowerShell, run <code>Get-FileHash .\\semantic-0.1.0-rc.2-windows-amd64.zip -Algorithm SHA256</code> and compare the ZIP entry in SHA256SUMS above. The <a href="https://github.com/insightos-community/quick-start/releases/tag/windows-v0.1.0-rc.2">GitHub Release</a> includes all validation reports.',
  faqWindowsTitle: "How do I install on Windows?",
  faqWindows: 'Download the <a href="https://github.com/insightos-community/quick-start/releases/download/windows-v0.1.0-rc.2/semantic-0.1.0-rc.2-windows-amd64.zip">Windows x64 ZIP (v0.1.0-rc.2 · GitHub)</a>, verify it against <a href="https://github.com/insightos-community/quick-start/releases/download/windows-v0.1.0-rc.2/SHA256SUMS">SHA256SUMS</a>, extract the complete ZIP and run <code>install.cmd</code>. Select Windows in the platform picker above to choose a release tag and view matching download links and CMD commands. This version includes the Skill environment fix, app icons and uninstall entries.',
  faqWindowsUpgrade: "To switch from an older version, stop scenes and old services, install into a new dedicated directory, retain old data and migrate it explicitly. Native Windows CI verifies installation, Abilities / Skills, physics simulation and uninstall. Physical GPU rendering still needs validation.",
  faqLanTitle:
    "Already installed? How do I enable LAN access and desktop shortcuts?",
  faqLan:
    "This command updates management tools, listen settings and shortcuts only. It does not upgrade the application, database or runtime bundles. Replace the directory with your actual installation path.",
  faqShortcuts:
    "Shortcuts use the InsightOS icon and open your local Web console. Without a desktop environment, omit <code>--desktop-shortcut</code>. If marked untrusted, select Allow Launching. Add the PATH shown after installation, then run <code>semanticctl welcome</code> to view addresses and the terminal-only password again.",
  faqUninstallTitle: "How do I uninstall? Will my data be deleted?",
  faqUninstall:
    "Use the installed management command directly; no installer archive download is needed. Stop scenes and Robot Runtime first. The directory below follows the selected platform; replace it with your actual installation path. Configuration, data and logs are kept by default.",
  faqUninstallSafety:
    "New management tools also support <code>semanticctl uninstall</code>. If a terminal is using the instance directory, run <code>cd ~</code> there. Deleted working directories do not block uninstall; no manual kill is needed. Only explicit <code>--purge</code> with confirmation permanently deletes the entire instance. System packages are not removed.",
  faqTroubleTitle: "What should I check if installation fails?",
  faqTrouble:
    "On Linux, check Python 3.10+; on macOS, check Apple Silicon and the OS version. Ports are checked before installation; choose available ports with <code>--http-port / --ws-port / --web-port / --runtime-port</code>. Verified archives are cached for retries; use <code>--cache-dir</code> to choose the cache location. Check disk space and networking, use <code>semanticctl doctor</code> and the instance <code>logs/</code>, or run the script with <code>--help</code>.",
  faqSiteTitle: "Is this a hosted robot console?",
  faqSite:
    "No. This is the Semantic introduction and installation site; it does not run your robot services. Your console, model keys and robot data belong to your own deployment. Configure access controls, network isolation and backups for production use.",
  closing: "Bring your ideas beyond the screen.",
  cta: 'Install Semantic <span aria-hidden="true">↗</span>',
  footer: "From semantics to action · Developer preview",
};
const translated = [...document.querySelectorAll("[data-i18n]")].map(
  (element) => ({
    element,
    key: element.dataset.i18n,
    original: element.innerHTML,
  }),
);
const labels = [...document.querySelectorAll("[data-i18n-label]")].map(
  (element) => ({
    element,
    key: element.dataset.i18nLabel,
    original: element.getAttribute("aria-label"),
  }),
);
const guideCommands = [
  ...document.querySelectorAll("[data-install-command]"),
].map((element) => ({ element, original: element.textContent }));
const originalTitle = document.title;
const description = document.querySelector('meta[name="description"]');
const originalDescription = description.content;
let currentLanguage = "zh";
const status = document.getElementById("copy-status");
const video = document.getElementById("install-video");
const videoSource = video.querySelector("source");
const videoError = document.getElementById("video-error");
let toastTimer;
const installPlatform = document.getElementById("install-platform");
const installTag = document.getElementById("install-tag");

const windowsCopy = {
  zh: {
    terminal: '<span class="terminal-dot"></span> 在已解压的 ZIP 目录中打开命令提示符（CMD）',
    installNote: 'Windows x64 原生安装包包含 Python 和依赖，无需 WSL、Bash 或编译器。先下载并校验 ZIP，再完整解压、运行安装命令。',
    guideIntro: 'Windows 默认安装目录为 <code>%LOCALAPPDATA%\\Semantic</code>。下方安装与管理命令使用 CMD；首次安装前，请先下载并完整解压上方选择的 ZIP。',
    stepInstall: '在 ZIP 解压目录打开 CMD，执行下方命令。可通过 <code>--dir</code> 修改安装目录；自动安装可增加 <code>--yes</code>。',
    stepPackages: '随包提供原生运行时和依赖，无需预装 Python。安装器先检查端口占用，可使用下方 YAML 配置调整端口。',
    stepManage: '命令使用 CMD；自定义安装目录时请替换路径，运行日志位于实例的 logs 目录。停止服务前请先在 Web 中释放场景。',
    configIntro: '下方命令跟随平台切换，Windows 使用 CMD。安装与首次导出在已解压的 ZIP 目录执行；重新配置使用已安装的管理命令。请把目录替换为实际实例目录。',
    configExport: '在已解压的 ZIP 目录执行：新目录导出默认值，已有实例导出当前值。已有实例也可使用 bin\\semanticctl.cmd export-config --output components.yaml，无需重新下载安装包。',
    configInstall: '在 ZIP 解压目录用 <code>-f</code> 加载编辑后的 YAML。安装程序和依赖随包提供，默认 Web 端口为 3000。',
    configReconfigure: '先在 Web 中释放场景，再导出并编辑配置，使用已安装的管理命令重新配置。无需下载 ZIP，已有版本、配置与数据保留。',
    configSync: '重新配置会检查端口，更新 Server、Web、Robot / Pilot 与 MuJoCo 的连接地址，并重启受影响的服务；启动失败时恢复原配置。',
    faqUninstall: '先在 Web 中释放场景，再从“已安装的应用”、Uninstall Semantic 或下方 CMD 命令卸载。使用本地文件，默认保留配置、数据和日志。请替换为实际安装路径。',
    faqUninstallSafety: '清理会在管理进程退出后完成，结果日志路径会显示在终端中。只有显式增加 <code>--purge</code> 并确认，才会删除全部实例数据。',
    faqTrouble: '确认使用 Windows x64 包，ZIP 已完整解压且校验和正确。端口冲突时修改 components.yaml 并重试；可复用已解压的文件。使用 semanticctl.cmd status 和实例 logs 目录排查。',
  },
  en: {
    terminal: '<span class="terminal-dot"></span> Open Command Prompt (CMD) in the extracted ZIP folder',
    installNote: 'The native Windows x64 ZIP includes Python and dependencies; no WSL, Bash or compiler is needed. Download and verify the ZIP, extract it completely, then run the installation command.',
    guideIntro: 'Windows defaults to <code>%LOCALAPPDATA%\\Semantic</code>. Installation and management commands below use CMD. Download and fully extract the selected ZIP before first installation.',
    stepInstall: 'Open CMD in the extracted ZIP folder and run the command below. Set <code>--dir</code> to choose an installation directory; add <code>--yes</code> for unattended installation.',
    stepPackages: 'Native runtimes and dependencies are bundled; no host Python is needed. Ports are checked before installation. Use the YAML guide below to change them.',
    stepManage: 'Use CMD and replace the path for a custom directory. Runtime logs are in the instance logs folder. Release scenes in Web before stopping services.',
    configIntro: 'Commands follow the selected platform; Windows uses CMD. Run installation and initial export from the extracted ZIP folder. Reconfigure with the installed manager. Replace the directory with your actual instance path.',
    configExport: 'From the extracted ZIP folder, export defaults for a new directory or current values for an existing instance. Installed instances can also use bin\\semanticctl.cmd export-config --output components.yaml without downloading the archive again.',
    configInstall: 'From the extracted ZIP folder, load your edited YAML with <code>-f</code>. The installer and dependencies are bundled. Web defaults to port 3000.',
    configReconfigure: 'Release scenes in Web first, export and edit the configuration, then use the installed manager to reconfigure. No ZIP download is needed; the installed version, configuration and data are kept.',
    configSync: 'Reconfiguration checks ports, updates Server, Web, Robot / Pilot and MuJoCo connections, then restarts affected services. Failed startup restores the previous configuration.',
    faqUninstall: 'Release scenes in Web, then uninstall from Installed apps, Uninstall Semantic or the CMD command below. Local files are used; configuration, data and logs are kept by default. Replace the installation path as needed.',
    faqUninstallSafety: 'Cleanup finishes after the manager exits; the terminal shows the result log path. Only explicit <code>--purge</code> with confirmation deletes all instance data.',
    faqTrouble: 'Check that you have the Windows x64 ZIP, have verified its checksum and extracted it completely. Edit components.yaml for port conflicts and retry using the extracted files. Use semanticctl.cmd status and the instance logs folder for diagnostics.',
  },
};

const platformDefaults = { glibc: "stable", musl: "musl-v0.1.0-3", macos: "macos-v0.1.0-rc.5", windows: "windows-v0.1.0-rc.2" };
function updateInstallCommand() {
  const target = installPlatform.value;
  for (const button of document.querySelectorAll('[data-platform]')) {
    button.setAttribute('aria-pressed', String(button.dataset.platform === target));
  }
  const windows = target === 'windows';
  for (const node of document.querySelectorAll('[data-unix-only], #musl-install, #macos-install')) node.hidden = windows;
  document.getElementById('windows-download-panel').hidden = !windows;
  const directory = target === 'macos' ? '$HOME/semantic-macos' : target === 'musl' ? '$HOME/semantic-musl' : '$HOME/.local/share/semantic';
  document.getElementById('uninstall-local-command').textContent = `"${directory}/bin/semanticctl" uninstall --dry-run\n"${directory}/bin/semanticctl" uninstall`;
  document.getElementById('uninstall-bootstrap-command').textContent = `curl -fsSL https://semantic.insightos.cn/install${currentLanguage === 'en' ? '-en' : ''}.sh | bash -s -- --uninstall --dir "${directory}"`;

  const tag = installTag.value.trim();
  const en = currentLanguage === "en";
  const patterns = {
    glibc: /^(stable|v[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._+-]*)$/,
    musl: /^musl-v[0-9]+\.[0-9]+\.[0-9]+-[1-9][0-9]*$/,
    macos: /^macos-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$/,
  };
  patterns.windows = /^windows-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$/;
  const valid = tag.length <= 100 && patterns[target].test(tag);
  document.getElementById("release-version").textContent = valid ? (tag === "stable" ? "v0.1.1" : tag) : "—";
  const error = document.getElementById("tag-error");
  error.hidden = valid;
  error.textContent = en ? "Enter a valid tag for the selected platform." : "请输入与所选平台匹配的版本标签。";
  installTag.setAttribute("aria-invalid", String(!valid));
  for (const lang of ["zh", "en"]) {
    const button = document.getElementById(lang === "en" ? "copy-command-en" : "copy-command");
    button.disabled = !valid;
    const command = document.getElementById(lang === "en" ? "install-command-en" : "install-command");
    if (!valid) { command.textContent = ""; continue; }
    const oss = lang === "zh";
    const release = tag === "stable" ? "v0.1.1" : tag;
    const source = oss ? (tag === "stable" ? "--source oss --version stable" : `--source oss --tag ${release}`) : `--source github --tag ${release}`;
    const options = target === "macos" ? ' --dir "$HOME/semantic-macos"'
      : target === "musl" ? ' --install-system-deps --dir "$HOME/semantic-musl"'
      : " --install-system-deps";
    command.textContent = `curl -fsSL https://semantic.insightos.cn/install${lang === "en" ? "-en" : ""}.sh | bash -s -- ${source}${options}`;
  }
  const bootstrap = `curl -fsSL https://semantic.insightos.cn/install${en ? '-en' : ''}.sh | bash -s --`;
  const platformOption = target === 'musl' ? ' --musl' : '';
  document.getElementById('app-shortcuts-command').textContent = `${bootstrap} --configure-existing --dir \"${directory}\" --desktop-shortcut`;
  document.getElementById('config-export-command').textContent = `${bootstrap}${platformOption} --dir "${directory}" --export-config components.yaml`;
  document.getElementById('config-reconfigure-command').textContent = `${bootstrap} reconfigure --dir "${directory}" -f components.yaml`;
  const installCommand = document.getElementById(en ? 'install-command-en' : 'install-command').textContent;
  document.getElementById('config-install-command').textContent = valid
    ? `${installCommand}${target === 'glibc' ? ` --dir "${directory}"` : ''} -f components.yaml` : '';
  document.querySelector('[data-copy-target="config-install-command"]').disabled = !valid;
  document.getElementById('config-tag-error').hidden = valid;
  document.getElementById('config-yaml').textContent = `schema_version: 1
http_port: 8034
ws_port: 8035
web_port: 3000
runtime_port: 8036
ability_port_first: 18100
ability_port_last: 18199
web_host: ${['macos', 'windows'].includes(target) ? '127.0.0.1' : '0.0.0.0'}`;
  document.getElementById("install-architecture").textContent = target === "macos" ? "arm64" : "x86_64";
  document.querySelector('[data-i18n="downloadRegion"]').textContent = !en
    ? "中国大陆 · 阿里云 OSS 镜像" : en ? "Selected tag · GitHub Releases" : "指定标签 · GitHub Releases";
  // Restore common copy/commands on every platform change, including after Windows.
  for (const {element, key, original} of translated) {
    if (Object.hasOwn(windowsCopy.zh, key)) element.innerHTML = windows ? windowsCopy[en ? 'en' : 'zh'][key] : en ? englishCopy[key] : original;
  }
  const selectedCommand = document.getElementById(en ? 'install-command-en' : 'install-command').textContent;
  document.getElementById('guide-install-command').textContent = selectedCommand;
  document.getElementById('guide-manage-command').textContent = `"${directory}/bin/semanticctl" status\n"${directory}/bin/semanticctl" doctor\n"${directory}/bin/semanticctl" logs`;
  const scriptLink = document.getElementById('script-link');
  scriptLink.href = en ? '/install-en.sh' : '/install.sh';
  scriptLink.textContent = en ? englishCopy.viewScript : translated.find(item => item.key === 'viewScript').original;
  for (const node of document.querySelectorAll('.command-row .prompt')) node.textContent = windows ? '>' : '$';
  if (windows) updateWindowsCommands(tag, valid, en);
}

function updateWindowsCommands(tag, valid, en) {
  const install = '.\\install.cmd --dir "%LOCALAPPDATA%\\Semantic"';
  const ctl = '"%LOCALAPPDATA%\\Semantic\\bin\\semanticctl.cmd"';
  const version = tag.slice('windows-v'.length);
  const archive = `semantic-${version}-windows-amd64.zip`;
  const base = en ? `https://github.com/insightos-community/quick-start/releases/download/${tag}`
    : `https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/releases/${version}/windows-amd64`;
  for (const [id, name] of [['windows-archive-link', archive], ['windows-checksums-link', 'SHA256SUMS']]) {
    const link = document.getElementById(id);
    if (valid) link.href = `${base}/${name}`; else link.removeAttribute('href');
    link.setAttribute('aria-disabled', String(!valid));
  }
  document.getElementById('windows-checksum-command').textContent = valid ? `Get-FileHash .\\${archive} -Algorithm SHA256` : '';
  for (const id of ['install-command', 'install-command-en', 'guide-install-command']) document.getElementById(id).textContent = valid ? install : '';
  document.getElementById('config-export-command').textContent = `.\\install.cmd --dir "%LOCALAPPDATA%\\Semantic" --export-config components.yaml`;
  document.getElementById('config-install-command').textContent = valid ? `${install} -f components.yaml` : '';
  document.getElementById('config-reconfigure-command').textContent = `${ctl} reconfigure -f components.yaml`;
  document.getElementById('uninstall-local-command').textContent = `${ctl} uninstall`;
  document.getElementById('guide-manage-command').textContent = `${ctl} status\n${ctl} start\n${ctl} stop`;
  document.getElementById('install-architecture').textContent = 'x64 · CMD';
  const scriptLink = document.getElementById('script-link');
  if (valid) scriptLink.href = `https://github.com/insightos-community/quick-start/releases/tag/${tag}`; else scriptLink.removeAttribute('href');
  scriptLink.textContent = en ? 'View release ↗' : '查看版本说明 ↗';
}
for (const button of document.querySelectorAll('[data-platform]')) {
  button.addEventListener('click', () => {
    installPlatform.value = button.dataset.platform;
    installPlatform.dispatchEvent(new Event('change'));
  });
}
installPlatform.addEventListener("change", () => { installTag.value = platformDefaults[installPlatform.value]; updateInstallCommand(); });
installTag.addEventListener("input", updateInstallCommand);

function setLanguage(language, persist = false) {
  currentLanguage = language === "en" ? "en" : "zh";
  const en = currentLanguage === "en";
  document.documentElement.lang = en ? "en" : "zh-CN";
  document.title = en ? "Semantic — From semantics to action" : originalTitle;
  description.content = en
    ? "Install Semantic Server, Web, MuJoCo Runtime and the R1Pro Robot Bundle with one command. Linux x86_64, macOS Apple Silicon and Windows x64."
    : originalDescription;
  for (const { element, key, original } of translated)
    element.innerHTML = en ? englishCopy[key] : original;
  for (const { element, key, original } of labels)
    element.setAttribute("aria-label", en ? englishCopy[key] : original);
  for (const { element, original } of guideCommands)
    element.textContent = en
      ? original.replaceAll(
          "https://semantic.insightos.cn/install.sh",
          "https://semantic.insightos.cn/install-en.sh",
        ).replaceAll("--source oss", "--source github")
      : original;
  for (const panel of document.querySelectorAll("[data-language-panel]"))
    panel.hidden = panel.dataset.languagePanel !== currentLanguage;
  for (const button of document.querySelectorAll("button[data-language]"))
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.language === currentLanguage),
    );
  document.getElementById("script-link").href = en
    ? "/install-en.sh"
    : "/install.sh";
  updateInstallCommand();
  const videoUrl = (en ? videoSource.dataset.srcEn : videoSource.dataset.srcZh)
    || videoSource.getAttribute("src");
  document.querySelector("#demo-caption a").href = videoUrl;
  if (videoSource.getAttribute("src") !== videoUrl) {
    // Pause/reset on a different recording; never start playback automatically.
    video.pause();
    videoSource.src = videoUrl;
    videoError.hidden = true;
    video.load();
  }
  clearTimeout(toastTimer);
  status.classList.remove("visible");
  document.getElementById("copy-command").textContent = "复制";
  document.getElementById("copy-command-en").textContent = "Copy";
  if (persist) {
    try {
      localStorage.setItem("semantic-site-language", currentLanguage);
    } catch {
      /* Storage may be blocked. */
    }
    const url = new URL(window.location.href);
    url.searchParams.set("lang", currentLanguage);
    history.replaceState(null, "", url);
  }
}
let preferred;
try {
  preferred = localStorage.getItem("semantic-site-language");
} catch {
  /* Use browser preference. */
}
const requested = new URLSearchParams(window.location.search).get("lang");
const supported = (value) => value === "zh" || value === "en";
setLanguage(
  supported(requested)
    ? requested
    : supported(preferred)
      ? preferred
      : navigator.language.toLowerCase().startsWith("zh")
        ? "zh"
        : "en",
);
for (const button of document.querySelectorAll("button[data-language]"))
  button.addEventListener("click", () =>
    setLanguage(button.dataset.language, true),
  );
video.addEventListener("error", () => {
  videoError.hidden = false;
});
videoSource.addEventListener("error", () => {
  videoError.hidden = false;
});
video.addEventListener("playing", () => {
  videoError.hidden = true;
});
for (const language of ["", "-en"]) {
  const button = document.getElementById("copy-command" + language);
  const command = document.getElementById("install-command" + language);
  const english = language === "-en";
  button.addEventListener("click", async () => {
    clearTimeout(toastTimer);
    document.getElementById("copy-command").textContent = "复制";
    document.getElementById("copy-command-en").textContent = "Copy";
    try {
      await navigator.clipboard.writeText(command.textContent);
      button.textContent = english ? "Copied" : "已复制";
      status.textContent = english
        ? "Command copied. Run it in the indicated terminal on your target machine."
        : "安装命令已复制，请在目标机器的指定终端中运行。";
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(command);
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = english
        ? "Please copy the selected command manually."
        : "请手动复制已选中的安装命令。";
    }
    if ((english ? "en" : "zh") !== currentLanguage) return;
    status.classList.add("visible");
    status.lang = english ? "en" : "zh-CN";
    toastTimer = setTimeout(() => {
      status.classList.remove("visible");
      button.textContent = english ? "Copy" : "复制";
    }, 4000);
  });
}

// Configuration commands share the current platform and language selection.
for (const button of document.querySelectorAll('[data-copy-target]')) {
  button.addEventListener('click', async () => {
    const command = document.getElementById(button.dataset.copyTarget);
    const language = currentLanguage;
    clearTimeout(toastTimer);
    let copied = false;
    try {
      await navigator.clipboard.writeText(command.textContent);
      copied = true;
    } catch {
      const range = document.createRange();
      range.selectNodeContents(command);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
    if (language !== currentLanguage) return;
    status.textContent = copied
      ? (language === 'en' ? 'Command copied.' : '命令已复制。')
      : (language === 'en' ? 'Please copy the selected command manually.' : '请手动复制已选中的命令。');
    status.lang = language === 'en' ? 'en' : 'zh-CN';
    status.classList.add('visible');
    toastTimer = setTimeout(() => status.classList.remove('visible'), 4000);
  });
}
