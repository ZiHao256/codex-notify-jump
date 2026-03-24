#!/usr/bin/env python3
import subprocess
import sys


SCRIPT = """
if application "Ghostty" is not running then
    return ""
end if

tell application "Ghostty"
    try
        return id of item 1 of terminals of selected tab of front window
    on error
        return ""
    end try
end tell
"""


def main() -> int:
    result = subprocess.run(
        ["osascript", "-e", SCRIPT],
        check=False,
        capture_output=True,
        text=True,
    )
    terminal_id = (result.stdout or "").strip()
    if result.returncode != 0 or not terminal_id:
        return 1

    sys.stdout.write(terminal_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
