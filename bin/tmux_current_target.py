import json
import os
import subprocess
import sys
from typing import Any


def parse_tmux_env(tmux_env: str) -> str:
    value = (tmux_env or "").strip()
    if not value:
        raise ValueError("TMUX is empty")
    parts = value.rsplit(",", 2)
    if len(parts) != 3:
        raise ValueError("TMUX must contain socket path plus server and client ids")
    socket_path = parts[0].strip()
    if not socket_path:
        raise ValueError("TMUX socket path is empty")
    return socket_path


def parse_tmux_target_line(line: str) -> dict[str, str]:
    text = (line or "").strip()
    if not text:
        raise ValueError("tmux output is empty")

    parts = text.split("\t")
    if len(parts) != 5:
        raise ValueError("tmux output must have exactly five tab-separated fields")

    session_id, window_id, pane_id, session_name, client_tty = [part.strip() for part in parts]
    if not session_id or not window_id or not pane_id or not session_name or not client_tty:
        raise ValueError("tmux output contains incomplete fields")
    if not session_id.startswith("$") or not window_id.startswith("@") or not pane_id.startswith("%"):
        raise ValueError("tmux output contains malformed target ids")

    return {
        "session_id": session_id,
        "window_id": window_id,
        "pane_id": pane_id,
        "session_name": session_name,
        "client_tty": client_tty,
    }


def _parse_tmux_target_query_line(line: str) -> dict[str, str]:
    text = (line or "").strip()
    if not text:
        raise ValueError("tmux target query output is empty")

    parts = text.split("\t")
    if len(parts) != 5:
        raise ValueError("tmux target query must have exactly five tab-separated fields")

    session_id, window_id, pane_id, session_name, socket_path = [part.strip() for part in parts]
    if not session_id or not window_id or not pane_id or not session_name or not socket_path:
        raise ValueError("tmux target query contains incomplete fields")
    if not session_id.startswith("$") or not window_id.startswith("@") or not pane_id.startswith("%"):
        raise ValueError("tmux target query contains malformed target ids")

    return {
        "session_id": session_id,
        "window_id": window_id,
        "pane_id": pane_id,
        "session_name": session_name,
        "socket_path": socket_path,
    }


def _run_tmux_target_query(target_pane: str) -> subprocess.CompletedProcess[str]:
    command = [
        "tmux",
        "display-message",
        "-p",
        "-t",
        target_pane,
        "#{session_id}\t#{window_id}\t#{pane_id}\t#{session_name}\t#{socket_path}",
    ]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _run_tmux_client_tty_query() -> subprocess.CompletedProcess[str]:
    command = [
        "tmux",
        "display-message",
        "-p",
        "#{client_tty}",
    ]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def main() -> int:
    target_pane = os.environ.get("TMUX_PANE", "").strip()
    if not target_pane:
        return 1

    try:
        result = _run_tmux_target_query(target_pane)
    except OSError:
        return 1
    if result.returncode != 0:
        return 1

    try:
        target = _parse_tmux_target_query_line(result.stdout or "")
    except ValueError:
        return 1

    try:
        client_result = _run_tmux_client_tty_query()
    except OSError:
        return 1
    if client_result.returncode != 0:
        return 1

    client_tty = (client_result.stdout or "").strip()
    if not client_tty:
        return 1

    payload: dict[str, Any] = {
        "socket_path": target["socket_path"],
        "session_id": target["session_id"],
        "window_id": target["window_id"],
        "pane_id": target["pane_id"],
        "session_name": target["session_name"],
        "client_tty": client_tty,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
