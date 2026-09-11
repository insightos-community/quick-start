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
  terminal: '<span class="terminal-dot"></span> Run in your Linux terminal',
  downloadRegion: "Downloads via GitHub Releases",
  viewScript: "View installer ↗",
  supportNote: "Linux x86_64 only · Verified on Ubuntu 24.04",
  supportRoadmap:
    "More Linux distributions will be tested soon, with compatibility results published as validation progresses.",
  installNote:
    "Requires Bash, curl, Python 3.10+ and glibc ≥ 2.28. You will be prompted for sudo before system dependencies are installed.<br>Review the script first. The installer confirms the directory and verifies the archive SHA-256.",
  preview: "Developer preview",
  downloadSize: "Approx. 346 MiB download",
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
    "Installs to <code>~/.local/share/semantic</code> by default.<br>Run commands on your own machine. Never enter credentials on this website.",
  stepInstallTitle: "Choose a directory and install",
  stepInstall:
    "The command above asks for confirmation. Add <code>--yes</code> for unattended installation; use an absolute path for a custom directory.",
  stepPackages:
    "Dependency installation supports apt-get, dnf/yum, pacman and zypper. It does not perform a full system upgrade.",
  stepWebTitle: "Open your console",
  stepWeb:
    "New installs support both <code>http://127.0.0.1:3000</code> and LAN access at <code>http://HOST_IP:3000</code>. The username is <code>admin</code>. A random password is shown in the interactive terminal and saved to <code>configs/secrets.json</code> in the instance directory, never to installation logs.",
  stepNetwork:
    "Web listens on <code>0.0.0.0:3000</code> by default. Use <code>--web-host 127.0.0.1</code> for localhost only, or <code>--web-port</code> for another port. Allow only trusted LAN traffic; API/WS remain local. Use an HTTPS reverse proxy or SSH tunnel for remote access.",
  stepManageTitle: "Check services and configure tasks",
  stepManage:
    "Replace these paths if you chose a custom directory. The default model is a mock; configure a real model separately. Installation does not create application tasks or start physical robots.",
  requirementsTitle: "Check first. Deploy next.",
  requirementsIntro:
    "Currently Linux x86_64 only. Main application binaries are statically built, but Python, MuJoCo wheels and graphics libraries still have system dependencies.",
  validatedTitle: "Verified operating system",
  validated: "Ubuntu 24.04 (Linux x86_64)",
  compatibilityTitle: "Compatibility limits",
  compatibility:
    "glibc ≥ 2.28 is a baseline, not a guarantee that other distributions have passed full validation. Full deployment on macOS, Windows, ARM64 or Alpine is not currently supported.",
  updatesTitle: "Downloads and updates",
  updates:
    "Prebuilt installers are downloaded from GitHub Releases. Missing model assets use pinned GitHub LFS objects with SHA-256 verification. Dependencies use your machine's configured package sources. For cross-version upgrades, install to a new directory and explicitly migrate data.",
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
    "Check Python, CPU architecture, disk space and network connectivity. Runtime logs are in the instance <code>logs/</code> directory. Use <code>semanticctl doctor</code> for diagnostics and <code>bash semantic-install.sh --help</code> for installer options.",
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
