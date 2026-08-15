# CI Hotfix — Linux / GitHub Actions

This hotfix fixes the Linux CI error:

`ImportError: libEGL.so.1: cannot open shared object file`

Changes:
- installs Qt/PySide6 Linux runtime libraries on Ubuntu 24.04 before the UI import smoke test and PyInstaller build;
- sets `QT_QPA_PLATFORM=offscreen` for headless CI;
- updates GitHub-owned actions to Node 24 based major versions;
- publishes the Linux build as `.tar.gz` so its executable permission is preserved after extraction;
- keeps Windows as a single `.exe`.

After committing the workflow fix, create a new tag. Re-running an old tag run can still use the old workflow from the tagged commit.
