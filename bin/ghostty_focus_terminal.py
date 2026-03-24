#!/usr/bin/env python3
import subprocess
import sys


def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> int:
    if len(sys.argv) != 2:
        return 2

    terminal_id = sys.argv[1].strip()
    if not terminal_id:
        return 2

    quoted_terminal_id = escape_applescript_string(terminal_id)
    script = f"""
if application "Ghostty" is not running then
    return "not-running"
end if

tell application "Ghostty"
    try
        focus (first terminal whose id is "{quoted_terminal_id}")
        return "focused"
    on error
        activate
        return "not-found"
    end try
end tell
"""

    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    outcome = (result.stdout or "").strip()
    if result.returncode == 0 and outcome == "focused":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
