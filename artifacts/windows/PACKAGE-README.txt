Semantic for Windows x64 — preview

Extract this complete ZIP into a short directory, then run install.cmd.
The installer uses the bundled Python and wheels without downloading dependencies.

install.cmd --export-config components.yaml
install.cmd --yes --dir "%LOCALAPPDATA%\Semantic" -f components.yaml

Installed management commands:
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" status
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" reconfigure -f components.yaml
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" stop
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" start

"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" uninstall --yes
Uninstall uses local files, preserves configuration/data/logs, and prints an external cleanup result path.
Add --purge only to permanently delete the whole instance.

Release active scenes in the Web UI before stopping or reconfiguring.
Default Web port: 3000. API: 8034. WebSocket: 8035. Runtime: 8036.
Application-local native DLLs are bundled. A working OpenGL GPU driver is needed for rendering.
Physical desktop GPU qualification is still pending.

Native application entries
Open Semantic from your application launcher to start services and open the current Web URL.
Use Uninstall Semantic to remove programs locally while preserving configuration and data.
Release simulation scenes first. --no-desktop-shortcut skips entry creation.
