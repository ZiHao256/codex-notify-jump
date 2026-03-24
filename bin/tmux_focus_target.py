#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class FocusContext:
    socket_path: str
    session_id: str
    window_id: str
    pane_id: str
    client_tty: str
    session_name: Optional[str] = None
    ghostty_term_id: Optional[str] = None


@dataclass(frozen=True)
class FocusPlan:
    action: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class FocusResult:
    ok: bool
    action: Optional[str] = None
    reason: Optional[str] = None


def plan_client_reuse(
    *, client_exists: bool, client_session_matches: Optional[bool]
) -> FocusPlan:
    if not client_exists:
        return FocusPlan(action="attach_new_window", reason="client_missing")
    return FocusPlan(action="reuse_client")


def plan_fallback_attach(*, attached_clients: int, prior_reason: str) -> FocusPlan:
    if attached_clients > 0:
        return FocusPlan(action="fail", reason="shared_session_unsupported")
    return FocusPlan(action="attach_new_window", reason=prior_reason)


def tmux_command(context: FocusContext, *args: str) -> list[str]:
    return ["tmux", "-S", context.socket_path, *args]


def fully_qualified_pane_target(context: FocusContext) -> str:
    return f"{context.session_id}:{context.window_id}.{context.pane_id}"


def _run_tmux(
    context: FocusContext,
    *args: str,
    run: RunCommand,
) -> subprocess.CompletedProcess[str]:
    return run(
        tmux_command(context, *args),
        check=False,
        capture_output=True,
        text=True,
    )


def validate_socket(context: FocusContext, *, run: RunCommand) -> bool:
    result = _run_tmux(context, "list-sessions", "-F", "#{session_id}", run=run)
    return result.returncode == 0


def session_exists(context: FocusContext, *, run: RunCommand) -> bool:
    result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-t",
        context.session_id,
        "#{session_id}",
        run=run,
    )
    return result.returncode == 0 and (result.stdout or "").strip() == context.session_id


def target_exists(context: FocusContext, *, run: RunCommand) -> bool:
    window_result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-t",
        context.window_id,
        "#{window_id}",
        run=run,
    )
    if window_result.returncode != 0 or (window_result.stdout or "").strip() != context.window_id:
        return False

    pane_result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-t",
        context.pane_id,
        "#{pane_id}",
        run=run,
    )
    if pane_result.returncode != 0 or (pane_result.stdout or "").strip() != context.pane_id:
        return False

    ownership_result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-t",
        fully_qualified_pane_target(context),
        "#{session_id}\t#{window_id}",
        run=run,
    )
    if ownership_result.returncode != 0:
        return False
    return (ownership_result.stdout or "").strip() == f"{context.session_id}\t{context.window_id}"


def client_exists(context: FocusContext, *, run: RunCommand) -> Optional[bool]:
    result = _run_tmux(context, "list-clients", "-F", "#{client_tty}", run=run)
    if result.returncode != 0:
        return None
    clients = {(line or "").strip() for line in (result.stdout or "").splitlines()}
    return context.client_tty in clients


def client_session_matches(context: FocusContext, *, run: RunCommand) -> Optional[bool]:
    result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-c",
        context.client_tty,
        "#{session_id}",
        run=run,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() == context.session_id


def count_attached_clients(context: FocusContext, *, run: RunCommand) -> Optional[int]:
    result = _run_tmux(
        context,
        "display-message",
        "-p",
        "-t",
        context.session_id,
        "#{session_group_attached}",
        run=run,
    )
    if result.returncode != 0:
        return None
    output = (result.stdout or "").strip()
    if not output:
        return 0
    if not output.isdigit():
        return None
    return int(output)


def select_target_for_client(context: FocusContext, *, run: RunCommand) -> bool:
    result = _run_tmux(
        context,
        "switch-client",
        "-c",
        context.client_tty,
        "-t",
        fully_qualified_pane_target(context),
        run=run,
    )
    return result.returncode == 0


def prepare_target_for_attach(context: FocusContext, *, run: RunCommand) -> bool:
    commands: Sequence[Sequence[str]] = (
        ("select-window", "-t", f"{context.session_id}:{context.window_id}"),
        ("select-pane", "-t", fully_qualified_pane_target(context)),
    )
    for command in commands:
        result = _run_tmux(context, *command, run=run)
        if result.returncode != 0:
            return False
    return True


def run_ghostty_focus_terminal(terminal_id: str) -> int:
    helper_path = Path(__file__).with_name("ghostty_focus_terminal.py")
    result = subprocess.run(
        [sys.executable, str(helper_path), terminal_id],
        check=False,
    )
    return result.returncode


def activate_ghostty_app() -> int:
    result = subprocess.run(
        ["osascript", "-e", 'tell application "Ghostty" to activate'],
        check=False,
    )
    return result.returncode


def open_ghostty_attach(context: FocusContext, *, run: RunCommand) -> bool:
    result = run(
        [
            "open",
            "-na",
            "Ghostty.app",
            "--args",
            "-e",
            "tmux",
            "-S",
            context.socket_path,
            "attach-session",
            "-t",
            context.session_id,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def focus_target(
    context: FocusContext,
    *,
    run: RunCommand = subprocess.run,
    ghostty_focus_runner: Optional[Callable[[str], int]] = None,
    ghostty_activate_runner: Optional[Callable[[], int]] = None,
) -> FocusResult:
    if not validate_socket(context, run=run):
        return FocusResult(ok=False, reason="tmux_server_mismatch")

    if not session_exists(context, run=run):
        return FocusResult(ok=False, reason="session_missing")

    if not target_exists(context, run=run):
        return FocusResult(ok=False, reason="target_expired")

    existing_client = client_exists(context, run=run)
    if existing_client is None:
        return FocusResult(ok=False, reason="tmux_server_mismatch")

    reuse_plan = plan_client_reuse(
        client_exists=existing_client,
        client_session_matches=None,
    )

    if reuse_plan.action == "reuse_client":
        if context.ghostty_term_id:
            runner = ghostty_focus_runner or run_ghostty_focus_terminal
            if runner(context.ghostty_term_id) != 0:
                return FocusResult(ok=False, reason="ghostty_focus_failed")
        if select_target_for_client(context, run=run):
            if not context.ghostty_term_id and ghostty_activate_runner is not None:
                if ghostty_activate_runner() != 0:
                    return FocusResult(ok=False, reason="ghostty_activate_failed")
            return FocusResult(ok=True, action="reuse_client")
        reuse_plan = FocusPlan(action="attach_new_window", reason="client_reuse_failed")

    attached_clients = count_attached_clients(context, run=run)
    if attached_clients is None:
        return FocusResult(ok=False, reason="tmux_server_mismatch")

    fallback_plan = plan_fallback_attach(
        attached_clients=attached_clients,
        prior_reason=reuse_plan.reason or "client_missing",
    )
    if fallback_plan.action == "fail":
        return FocusResult(ok=False, reason=fallback_plan.reason)

    if not prepare_target_for_attach(context, run=run):
        return FocusResult(ok=False, reason="target_expired")

    if not open_ghostty_attach(context, run=run):
        return FocusResult(ok=False, reason="attach_failed")

    return FocusResult(ok=True, action="attach_new_window", reason=fallback_plan.reason)


def parse_args(argv: Sequence[str]) -> FocusContext:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--pane-id", required=True)
    parser.add_argument("--client-tty", required=True)
    parser.add_argument("--session-name")
    parser.add_argument("--ghostty-term-id")
    args = parser.parse_args(argv)
    return FocusContext(
        socket_path=args.socket_path,
        session_id=args.session_id,
        window_id=args.window_id,
        pane_id=args.pane_id,
        client_tty=args.client_tty,
        session_name=args.session_name,
        ghostty_term_id=args.ghostty_term_id,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    context = parse_args(argv or sys.argv[1:])
    result = focus_target(context, ghostty_activate_runner=activate_ghostty_app)
    sys.stdout.write(json.dumps(asdict(result), ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
