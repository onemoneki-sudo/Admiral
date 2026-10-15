import sys

if sys.version_info < (3, 11):  # before anything that needs 3.11 (tomllib), so the reason is plain
    reason = (f"Admiral needs Python 3.11 or newer; {sys.executable} is {sys.version.split()[0]}. "
              "Run scripts/install.sh again, or point ADMIRAL_PYTHON at a newer python3.")
    if sys.argv[1:2] == ["statusline"]:
        print(reason)  # Claude Code draws a status line's stdout, and only when it exits 0
        sys.exit(0)
    sys.exit(reason)

from .cli import main  # noqa: E402

main()
