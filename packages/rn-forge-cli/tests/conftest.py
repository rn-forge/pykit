import os

# Typer decides at import time whether to force ANSI colors, and colored help
# splits option names like `--log-level` across escape codes.
for _name in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(_name, None)
