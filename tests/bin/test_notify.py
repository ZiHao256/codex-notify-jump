import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = REPO_ROOT / "bin"
if str(BIN_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BIN_DIR))

import notify  # type: ignore  # noqa: E402


class NotifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmux_focus_helper = str((BIN_DIR / "tmux_focus_target.py").resolve())
        self.ghostty_focus_helper = str((BIN_DIR / "ghostty_focus_terminal.py").resolve())

    def test_supported_notification_types_are_explicit(self) -> None:
        self.assertTrue(notify.is_supported_notification_type("agent-turn-complete"))
        self.assertTrue(notify.is_supported_notification_type("approval-requested"))

    def test_unrelated_notification_type_is_ignored(self) -> None:
        self.assertFalse(notify.is_supported_notification_type("task-started"))

    def test_tmux_click_command_uses_tmux_focus_helper_when_required_env_present(self) -> None:
        env = {
            "CODEX_TMUX_SOCKET_PATH": "/tmp/tmux.sock",
            "CODEX_TMUX_SESSION_ID": "$1",
            "CODEX_TMUX_WINDOW_ID": "@2",
            "CODEX_TMUX_PANE_ID": "%3",
            "CODEX_TMUX_CLIENT_TTY": "/dev/ttys004",
            "CODEX_TMUX_SESSION_NAME": "work",
            "CODEX_GHOSTTY_TERM_ID": "ghostty-tab-1",
        }

        command = notify.build_click_command(env, home_dir="/Users/tester")

        self.assertEqual(
            command,
            f"python3 {self.tmux_focus_helper} "
            "--socket-path /tmp/tmux.sock "
            "--session-id '$1' "
            "--window-id @2 "
            "--pane-id %3 "
            "--client-tty /dev/ttys004 "
            "--session-name work "
            "--ghostty-term-id ghostty-tab-1",
        )

    def test_tmux_click_command_requires_all_core_tmux_env_vars(self) -> None:
        env = {
            "CODEX_TMUX_SOCKET_PATH": "/tmp/tmux.sock",
            "CODEX_TMUX_SESSION_ID": "$1",
            "CODEX_TMUX_WINDOW_ID": "@2",
            "CODEX_GHOSTTY_TERM_ID": "ghostty-tab-1",
        }

        command = notify.build_click_command(env, home_dir="/Users/tester")

        self.assertEqual(
            command,
            f"python3 {self.ghostty_focus_helper} ghostty-tab-1",
        )

    def test_tmux_click_command_requires_client_tty(self) -> None:
        env = {
            "CODEX_TMUX_SOCKET_PATH": "/tmp/tmux.sock",
            "CODEX_TMUX_SESSION_ID": "$1",
            "CODEX_TMUX_WINDOW_ID": "@2",
            "CODEX_TMUX_PANE_ID": "%3",
            "CODEX_GHOSTTY_TERM_ID": "ghostty-tab-1",
        }

        command = notify.build_click_command(env, home_dir="/Users/tester")

        self.assertEqual(
            command,
            f"python3 {self.ghostty_focus_helper} ghostty-tab-1",
        )

    def test_ghostty_click_command_is_used_when_tmux_context_is_absent(self) -> None:
        env = {
            "CODEX_GHOSTTY_TERM_ID": "ghostty-tab-1",
        }

        command = notify.build_click_command(env, home_dir="/Users/tester")

        self.assertEqual(
            command,
            f"python3 {self.ghostty_focus_helper} ghostty-tab-1",
        )

    def test_activate_fallback_is_used_when_no_focus_context_exists(self) -> None:
        command = notify.build_click_command({}, home_dir="/Users/tester")

        self.assertEqual(
            command,
            'osascript -e \'tell application "Ghostty" to activate\'',
        )

    def test_explicit_empty_env_does_not_read_process_environment(self) -> None:
        with mock.patch.dict("os.environ", {"CODEX_GHOSTTY_TERM_ID": "ambient-ghostty"}, clear=True):
            command = notify.build_click_command({}, home_dir="/Users/tester")

        self.assertEqual(
            command,
            'osascript -e \'tell application "Ghostty" to activate\'',
        )

    def test_build_codex_notifier_command_wraps_click_command(self) -> None:
        command = notify.build_codex_notifier_command(
            "/Users/tester/.codex/bin/CodexNotifier.app/Contents/MacOS/codex-notifier",
            title="Codex: ready",
            message="Dir: /Users/tester/.codex",
            identifier="codex-thread-1",
            click_command="python3 /Users/tester/.codex/bin/tmux_focus_target.py --pane-id %1",
        )

        self.assertEqual(
            command,
            [
                "/Users/tester/.codex/bin/CodexNotifier.app/Contents/MacOS/codex-notifier",
                "--title",
                "Codex: ready",
                "--message",
                "Dir: /Users/tester/.codex",
                "--identifier",
                "codex-thread-1",
                "--action-title",
                "Jump",
                "--command",
                "python3 /Users/tester/.codex/bin/tmux_focus_target.py --pane-id %1",
            ],
        )

    def test_send_codex_clickable_notification_uses_open_returncode(self) -> None:
        with mock.patch.object(notify, "ensure_codex_notifier", return_value="/tmp/codex-notifier"):
            with mock.patch.object(
                notify.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as run_mock:
                sent = notify.send_codex_clickable_notification(
                    "Codex: ready",
                    "Dir: /Users/tester/project",
                    thread_id="thread-1",
                    click_command="python3 /tmp/focus.py",
                )

        self.assertTrue(sent)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0][0:4], ["open", "-na", mock.ANY, "--args"])

    def test_main_prefers_codex_notifier_over_terminal_notifier(self) -> None:
        payload = (
            '{"type":"agent-turn-complete","last-assistant-message":"prefer native",'
            '"input-messages":[],"cwd":"/Users/tester/.codex","thread-id":"native-first"}'
        )

        with mock.patch.object(
            notify,
            "send_codex_clickable_notification",
            return_value=True,
        ) as send_native:
            with mock.patch.object(notify.shutil, "which", return_value="/opt/homebrew/bin/terminal-notifier"):
                with mock.patch.object(notify.subprocess, "run") as run_mock:
                    with mock.patch.object(notify.sys, "argv", ["notify.py", payload]):
                        exit_code = notify.main()

        self.assertEqual(exit_code, 0)
        send_native.assert_called_once()
        run_mock.assert_not_called()

    def test_main_falls_back_to_osascript_when_terminal_notifier_fails(self) -> None:
        payload = (
            '{"type":"agent-turn-complete","last-assistant-message":"fallback debug",'
            '"input-messages":[],"cwd":"/Users/tester/.codex","thread-id":"fallback-test"}'
        )
        fake_run = mock.Mock(
            side_effect=[
                SimpleNamespace(returncode=1, stdout="", stderr="notifier failed"),
                SimpleNamespace(returncode=0, stdout="", stderr=""),
            ]
        )

        with mock.patch.object(notify, "send_codex_clickable_notification", return_value=False):
            with mock.patch.object(notify.shutil, "which", return_value="/opt/homebrew/bin/terminal-notifier"):
                with mock.patch.object(notify.subprocess, "run", fake_run):
                    with mock.patch.object(notify.sys, "argv", ["notify.py", payload]):
                        exit_code = notify.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_run.call_count, 2)
        self.assertEqual(
            fake_run.call_args_list[0].args[0][0],
            "/opt/homebrew/bin/terminal-notifier",
        )
        self.assertEqual(
            fake_run.call_args_list[1].args[0],
            [
                "osascript",
                "-e",
                'display notification "Dir: /Users/tester/.codex" with title "Codex: fallback debug"',
            ],
        )


if __name__ == "__main__":
    unittest.main()
