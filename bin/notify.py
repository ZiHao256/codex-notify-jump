#!/usr/bin/env python3
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from typing import Mapping, Optional

SUPPORTED_NOTIFICATION_TYPES = {
    "agent-turn-complete",
    "approval-requested",
}
CODEX_NOTIFIER_APP_NAME = "CodexNotifier.app"
CODEX_NOTIFIER_EXECUTABLE_NAME = "codex-notifier"
CODEX_NOTIFIER_SOURCE_NAME = "codex_notifier.swift"
CODEX_NOTIFIER_ACTION_TITLE = "Jump"


def truncate(s: str, limit: int = 180) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def escape_applescript_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_osascript_notification_command(title: str, message: str) -> list[str]:
    script = (
        f'display notification "{escape_applescript_string(message)}" '
        f'with title "{escape_applescript_string(title)}"'
    )
    return ["osascript", "-e", script]

def _script_bin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))

def _codex_repo_root() -> str:
    return os.path.dirname(_script_bin_dir())


def _helper_path(filename: str) -> str:
    return os.path.join(_script_bin_dir(), filename)


def _codex_notifier_paths() -> dict[str, str]:
    source_dir = _script_bin_dir()
    app_dir = os.path.join(_codex_repo_root(), "cache", "codex-notifier", CODEX_NOTIFIER_APP_NAME)
    contents_dir = os.path.join(app_dir, "Contents")
    executable = os.path.join(contents_dir, "MacOS", CODEX_NOTIFIER_EXECUTABLE_NAME)
    return {
        "source": os.path.join(source_dir, CODEX_NOTIFIER_SOURCE_NAME),
        "app_dir": app_dir,
        "contents_dir": contents_dir,
        "macos_dir": os.path.join(contents_dir, "MacOS"),
        "info_plist": os.path.join(contents_dir, "Info.plist"),
        "executable": executable,
    }

def _codex_notifier_info_plist(executable_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>{executable_name}</string>
    <key>CFBundleIdentifier</key>
    <string>io.github.codexnotifyjump.notifier</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>CodexNotifier</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""

def _write_codex_notifier_info_plist(info_plist_path: str) -> None:
    os.makedirs(os.path.dirname(info_plist_path), exist_ok=True)
    with open(info_plist_path, "w", encoding="utf-8") as handle:
        handle.write(_codex_notifier_info_plist(CODEX_NOTIFIER_EXECUTABLE_NAME))

def ensure_codex_notifier() -> Optional[str]:
    paths = _codex_notifier_paths()
    source_path = paths["source"]
    executable_path = paths["executable"]
    info_plist_path = paths["info_plist"]
    swiftc = shutil.which("swiftc")

    if not os.path.isfile(source_path) or not swiftc:
        return None

    source_mtime = os.path.getmtime(source_path)
    executable_exists = os.path.isfile(executable_path)
    info_plist_exists = os.path.isfile(info_plist_path)
    build_required = (
        not executable_exists
        or not info_plist_exists
        or os.path.getmtime(executable_path) < source_mtime
    )
    if not build_required:
        return executable_path

    os.makedirs(paths["macos_dir"], exist_ok=True)
    _write_codex_notifier_info_plist(info_plist_path)
    result = subprocess.run(
        [
            swiftc,
            source_path,
            "-framework",
            "AppKit",
            "-o",
            executable_path,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    os.chmod(executable_path, 0o755)
    return executable_path

def build_codex_notifier_command(
    notifier_path: str,
    *,
    title: str,
    message: str,
    identifier: str,
    click_command: str,
) -> list[str]:
    return [
        notifier_path,
        "--title",
        title,
        "--message",
        message,
        "--identifier",
        identifier,
        "--action-title",
        CODEX_NOTIFIER_ACTION_TITLE,
        "--command",
        click_command,
    ]

def send_codex_clickable_notification(
    title: str,
    message: str,
    *,
    thread_id: str,
    click_command: str,
) -> bool:
    paths = _codex_notifier_paths()
    notifier_path = ensure_codex_notifier()
    if not notifier_path:
        return False

    process = subprocess.Popen(
        [
            "open",
            "-na",
            paths["app_dir"],
            "--args",
            *build_codex_notifier_command(
                notifier_path,
                title=title,
                message=message,
                identifier=f"codex-{thread_id}",
                click_command=click_command,
            )[1:],
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    time.sleep(0.3)
    return process.poll() is None


def is_supported_notification_type(notification_type: object) -> bool:
    return str(notification_type or "") in SUPPORTED_NOTIFICATION_TYPES


def _env_value(env: Mapping[str, str], key: str) -> str:
    return (env.get(key) or "").strip()


def _tmux_click_command(env: Mapping[str, str], home_dir: str) -> Optional[str]:
    socket_path = _env_value(env, "CODEX_TMUX_SOCKET_PATH")
    session_id = _env_value(env, "CODEX_TMUX_SESSION_ID")
    window_id = _env_value(env, "CODEX_TMUX_WINDOW_ID")
    pane_id = _env_value(env, "CODEX_TMUX_PANE_ID")
    client_tty = _env_value(env, "CODEX_TMUX_CLIENT_TTY")
    session_name = _env_value(env, "CODEX_TMUX_SESSION_NAME")
    ghostty_term_id = _env_value(env, "CODEX_GHOSTTY_TERM_ID")

    if not all([socket_path, session_id, window_id, pane_id, client_tty]):
        return None

    helper = _helper_path("tmux_focus_target.py")
    parts = [
        "python3",
        shlex.quote(helper),
        "--socket-path",
        shlex.quote(socket_path),
        "--session-id",
        shlex.quote(session_id),
        "--window-id",
        shlex.quote(window_id),
        "--pane-id",
        shlex.quote(pane_id),
    ]
    parts.extend(["--client-tty", shlex.quote(client_tty)])
    if session_name:
        parts.extend(["--session-name", shlex.quote(session_name)])
    if ghostty_term_id:
        parts.extend(["--ghostty-term-id", shlex.quote(ghostty_term_id)])
    return " ".join(parts)


def _ghostty_click_command(env: Mapping[str, str], home_dir: str) -> Optional[str]:
    ghostty_terminal_id = _env_value(env, "CODEX_GHOSTTY_TERM_ID")
    if not ghostty_terminal_id:
        return None

    helper = _helper_path("ghostty_focus_terminal.py")
    return f"python3 {shlex.quote(helper)} {shlex.quote(ghostty_terminal_id)}"


def build_click_command(
    env: Optional[Mapping[str, str]] = None,
    *,
    home_dir: Optional[str] = None,
) -> str:
    active_env = dict(os.environ) if env is None else env
    resolved_home_dir = home_dir or os.path.expanduser("~")

    tmux_command = _tmux_click_command(active_env, resolved_home_dir)
    if tmux_command:
        return tmux_command

    ghostty_command = _ghostty_click_command(active_env, resolved_home_dir)
    if ghostty_command:
        return ghostty_command

    return 'osascript -e \'tell application "Ghostty" to activate\''


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    try:
        notification = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return 1

    if not is_supported_notification_type(notification.get("type")):
        return 0

    last_msg = notification.get("last-assistant-message") or "Turn complete"
    inputs = notification.get("input-messages") or []
    cwd = notification.get("cwd") or ""
    thread_id = str(notification.get("thread-id") or "codex")

    title = f"Codex: {truncate(last_msg, 80)}"

    parts = []
    if inputs:
        parts.append(f"Prompt: {truncate(' | '.join(map(str, inputs)), 120)}")
    if cwd:
        parts.append(f"Dir: {cwd}")
    message = "\n".join(parts) if parts else "Codex finished the current turn."
    click_cmd = build_click_command()
    if send_codex_clickable_notification(
        title,
        message,
        thread_id=thread_id,
        click_command=click_cmd,
    ):
        return 0

    notifier = shutil.which("terminal-notifier")

    if notifier:
        cmd = [
            notifier,
            "-title", title,
            "-message", message,
            "-group", f"codex-{thread_id}",
            "-sound", "default",
        ]
        cmd += ["-execute", click_cmd]

        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return 0

    subprocess.run(
        build_osascript_notification_command(title, message),
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
