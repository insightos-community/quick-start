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
  tagLabel: "Release tag / default channel",
  tagHelp: "stable keeps the default Linux channel; enter a Release tag to pin a version. musl/macOS use GitHub Releases.",
  macosTitle: "Native macOS installation (Apple Silicon)",
  macosIntro: "Requires macOS 15.5+ on Apple Silicon arm64. Use the same entry script and select a macOS Release with <code>--tag</code>. No OSS mirror is available yet; downloads come from GitHub with checksum verification.",
  macosRuntime: "Bundles Python 3.13.15, NumPy 2.3.5, MuJoCo and robot dependencies. No Homebrew or host Python is required. Web requests auto and the Runtime uses configured CGL. This preview is not notarized; physical GPU rendering still needs testing.",
  macosUpgrade: "Stop the old instance before installing another tag into a new <code>--dir</code>, then reload the browser. The installer neither overwrites other versions nor migrates databases automatically; old configuration and data remain in the original directory.",
  macosRelease: "<a href=\"https://github.com/insightos-community/quick-start/releases/tag/macos-v0.1.0-rc.3\">macos-v0.1.0-rc.3 ↗</a> · Approx. 412 MiB · Installation, API, physics and lifecycle checks passed.",
  terminal: "<span class=\"terminal-dot\"></span> Run on the target machine",
  downloadRegion: "Downloads via GitHub Releases",
  viewScript: "View installer ↗",
  supportNote: "Linux x86_64 (glibc / musl) · Native macOS 15.5+ Apple Silicon preview",
  supportRoadmap:
    "More Linux distributions will be tested soon, with compatibility results published as validation progresses.",
  installNote:
    "Linux requires Bash, curl and Python 3.10+. macOS uses bundled Python; no Homebrew is needed. Select a platform and tag, then copy the command.<br>Archives are SHA-256 verified. System dependencies use your existing package repositories.",
  preview: "Developer preview",
  downloadSize: "Download size varies by platform and version",
  muslTitle: "musl runtime: bundled or system (optional)",
  muslIntro: "On Linux x86_64, <code>--tag musl-v0.1.0-2</code> selects the musl package automatically; the existing <code>--musl</code> option remains available. Bundled musl works on glibc hosts too; use a separate directory.",
  muslRuntime: "<code>--musl-runtime bundled</code> uses the included musl 1.2.5; <code>--musl-runtime system</code> uses the host musl 1.2+ loader. Includes CPython 3.13.15, NumPy 2.3.5, robot libraries and Mesa, without source compilation. System /lib and package repositories are unchanged; use a new directory to switch runtimes.",
  muslRender: "By default, a working Mesa GPU is selected, with software rendering as a fallback. Add <code>--render-backend software</code> to force software rendering, or <code>--render-backend mesa-gpu</code> to require hardware rendering. AMD has been tested; Intel / Nouveau still need hardware validation. Use the default glibc installer for proprietary NVIDIA drivers.",
  muslRelease: 'Optional prerelease <a href="https://github.com/insightos-community/quick-start/releases/tag/musl-v0.1.0-2">musl-v0.1.0-2 ↗</a> · Approx. 626 MiB · Offline installation and software rendering verified on Ubuntu 22.04 / Alpine 3.23.',
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
  stepNetwork:
    "Linux Web defaults to <code>0.0.0.0:3000</code>; macOS defaults to <code>127.0.0.1:3000</code>. Customize with <code>--web-host</code> / <code>--web-port</code>. API/WS stay local; expose Web only to trusted networks.",
  stepManageTitle: "Check services and configure tasks",
  stepManage:
    "Replace these paths if you chose a custom directory. The default model is a mock; configure a real model separately. Installation does not create application tasks or start physical robots.",
  requirementsTitle: "Check first. Deploy next.",
  requirementsIntro:
    "Separate installer distributions support Linux x86_64 glibc/musl and native macOS Apple Silicon arm64. Each uses its own runtime and dependency set; binaries are not interchangeable.",
  validatedTitle: "Verified operating system",
  validated: "Ubuntu 24.04 (glibc); Ubuntu 22.04 / Alpine 3.23 (musl); macOS 15.5+ Apple Silicon (installation, API and physics checks)",
  compatibilityTitle: "Compatibility limits",
  compatibility:
    "glibc baseline ≥ 2.28; musl is bundled by default, while system mode needs host musl 1.2+. macOS uses system CGL; physical GPU rendering still needs validation. Intel Mac, Windows and Linux ARM64 are not supported.",
  updatesTitle: "Downloads and updates",
  updates:
    "The Chinese default Linux channel uses Aliyun OSS; English defaults to GitHub Releases. An explicit --tag selects its GitHub Release by default. musl/macOS have no OSS artifacts yet and use GitHub Releases. Install other versions/platforms into a new directory and migrate data explicitly.",
  faqTitle: "Frequently asked questions",
  faqLanTitle:
    "Already installed? How do I enable LAN access and desktop shortcuts?",
  faqLan:
    "This command updates management tools, listen settings and shortcuts only. It does not upgrade the application, database or runtime bundles. Replace the directory with your actual installation path.",
  faqShortcuts:
    "Shortcuts use the InsightOS icon and open your local Web console. Without a desktop environment, omit <code>--desktop-shortcut</code>. If marked untrusted, select Allow Launching. Add the PATH shown after installation, then run <code>semanticctl welcome</code> to view addresses and the terminal-only password again.",
  faqUninstallTitle: "How do I uninstall? Will my data be deleted?",
  faqUninstall:
    "Stop scenes and Robot Runtime first. By default, uninstall keeps configuration, data and logs. Review the plan with <code>--dry-run</code> and replace the directory with your absolute installation path.",
  faqUninstallSafety:
    "New management tools also support <code>semanticctl uninstall</code>. If a terminal is using the instance directory, run <code>cd ~</code> there. Deleted working directories do not block uninstall; no manual kill is needed. Only explicit <code>--purge</code> with confirmation permanently deletes the entire instance. System packages are not removed.",
  faqTroubleTitle: "What should I check if installation fails?",
  faqTrouble:
    "On Linux, check Python 3.10+; on macOS, check Apple Silicon and the OS version. Check disk space and networking, use <code>semanticctl doctor</code> and the instance <code>logs/</code>, or run the script with <code>--help</code>.",
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
const platformDefaults = { glibc: "stable", musl: "musl-v0.1.0-2", macos: "macos-v0.1.0-rc.3" };
function updateInstallCommand() {
  const target = installPlatform.value;
  const tag = installTag.value.trim();
  const en = currentLanguage === "en";
  const patterns = {
    glibc: /^(stable|v[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._+-]*)$/,
    musl: /^musl-v[0-9]+\.[0-9]+\.[0-9]+-[1-9][0-9]*$/,
    macos: /^macos-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$/,
  };
  const valid = patterns[target].test(tag);
  const error = document.getElementById("tag-error");
  error.hidden = valid;
  error.textContent = en ? "Enter a valid tag for the selected platform." : "请输入与所选平台匹配的版本标签。";
  installTag.setAttribute("aria-invalid", String(!valid));
  for (const lang of ["zh", "en"]) {
    const button = document.getElementById(lang === "en" ? "copy-command-en" : "copy-command");
    button.disabled = !valid;
    const command = document.getElementById(lang === "en" ? "install-command-en" : "install-command");
    if (!valid) { command.textContent = ""; continue; }
    const oss = target === "glibc" && tag === "stable" && lang === "zh";
    const release = tag === "stable" ? "v0.1.0" : tag;
    const source = oss ? "--source oss --version stable" : `--source github --tag ${release}`;
    const options = target === "macos" ? ' --dir "$HOME/semantic-macos"'
      : target === "musl" ? ' --install-system-deps --dir "$HOME/semantic-musl"'
      : " --install-system-deps";
    command.textContent = `curl -fsSL https://semantic.insightos.cn/install${lang === "en" ? "-en" : ""}.sh | bash -s -- ${source}${options}`;
  }
  document.getElementById("install-architecture").textContent = target === "macos" ? "arm64" : "x86_64";
  document.querySelector('[data-i18n="downloadRegion"]').textContent = target === "glibc" && tag === "stable" && !en
    ? "默认 Linux 渠道 · 阿里云 OSS" : en ? "Selected tag · GitHub Releases" : "指定标签 · GitHub Releases";
}
installPlatform.addEventListener("change", () => { installTag.value = platformDefaults[installPlatform.value]; updateInstallCommand(); });
installTag.addEventListener("input", updateInstallCommand);

function setLanguage(language, persist = false) {
  currentLanguage = language === "en" ? "en" : "zh";
  const en = currentLanguage === "en";
  document.documentElement.lang = en ? "en" : "zh-CN";
  document.title = en ? "Semantic — From semantics to action" : originalTitle;
  description.content = en
    ? "Install Semantic Server, Web, MuJoCo Runtime and the R1Pro Robot Bundle with one command. Linux x86_64 only; verified on Ubuntu 24.04."
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
        )
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
        ? "Command copied. Run it in a terminal on your Linux machine."
        : "安装命令已复制，请在目标 Linux 机器的终端中运行。";
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
