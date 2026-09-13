Semantic Installer — macOS arm64 preview

Requirements: Apple Silicon, macOS 15.5 or newer.
This archive includes Python 3.13.15, offline wheels, native executables,
Web UI, Robot abilities/skills and the native MuJoCo scene assets.
No Homebrew, system Python, compiler or package mirror changes are required.

Install from Terminal:
  bash install.command
  bash install.command --dir "$HOME/semantic" --yes

Default location: ~/Library/Application Support/Semantic
Default Web address: http://127.0.0.1:3000
Login: admin; a random password is generated during installation.
Display credentials in your terminal with:
  "$HOME/Library/Application Support/Semantic/bin/semanticctl" welcome

Management: semanticctl start | stop | status | doctor | logs | welcome
Uninstall while preserving data: semanticctl uninstall
Remove this instance and all its data: semanticctl uninstall --purge
The installer does not replace an installed version with different files;
use a separate --dir to evaluate another release.

Verification boundary: native installation, HTTP/API, Python math and MuJoCo
physics are tested in CI. Physical Mac CGL graphics and complete LLM-driven
pallet tasks are not yet qualified. This is an unsigned preview, not a
notarized DMG. macOS may ask for approval when opening downloaded software.
No security settings are modified by this installer.

This preview covers native MuJoCo only, not LIBERO/Robosuite or vendor drivers.
Models and Web content are included under their respective notices/licenses.
Configure your model provider in Semantic before requesting AI plans.
