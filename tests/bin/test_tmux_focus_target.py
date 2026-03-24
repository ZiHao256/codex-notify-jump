import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = REPO_ROOT / "bin"
if str(BIN_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BIN_DIR))

import tmux_focus_target  # type: ignore  # noqa: E402


def completed(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TmuxFocusTargetTests(unittest.TestCase):
    def make_context(self, **overrides: str) -> tmux_focus_target.FocusContext:
        values = {
            "socket_path": "/tmp/tmux-test.sock",
            "session_id": "$1",
            "window_id": "@2",
            "pane_id": "%3",
            "client_tty": "/dev/ttys004",
            "session_name": "work",
            "ghostty_term_id": None,
        }
        values.update(overrides)
        return tmux_focus_target.FocusContext(**values)

    def test_plan_reuse_client_when_client_is_present_and_matches_target_session(self) -> None:
        plan = tmux_focus_target.plan_client_reuse(
            client_exists=True,
            client_session_matches=True,
        )

        self.assertEqual(plan.action, "reuse_client")
        self.assertIsNone(plan.reason)

    def test_plan_fallback_attach_when_client_is_missing(self) -> None:
        plan = tmux_focus_target.plan_client_reuse(
            client_exists=False,
            client_session_matches=None,
        )

        self.assertEqual(plan.action, "attach_new_window")
        self.assertEqual(plan.reason, "client_missing")

    def test_plan_fallback_attach_when_client_is_attached_elsewhere(self) -> None:
        plan = tmux_focus_target.plan_client_reuse(
            client_exists=True,
            client_session_matches=False,
        )

        self.assertEqual(plan.action, "reuse_client")
        self.assertIsNone(plan.reason)

    def test_focus_target_returns_session_missing_when_target_session_is_gone(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(returncode=1, stderr="no session"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "session_missing")

    def test_focus_target_returns_target_expired_when_target_window_or_pane_is_gone(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(returncode=1, stderr="can't find window"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "target_expired")

    def test_focus_target_reuses_existing_client_and_selects_stable_ids(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(stdout="$1\n"),
                completed(),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "reuse_client")
        self.assertIsNone(result.reason)
        self.assertEqual(
            fake_run.call_args_list[0].args[0],
            [
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "list-sessions",
                "-F",
                "#{session_id}",
            ],
        )
        self.assertEqual(
            fake_run.call_args_list[-1].args[0],
            [
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "switch-client",
                "-c",
                "/dev/ttys004",
                "-t",
                "$1:@2.%3",
            ],
        )

    def test_focus_target_activates_ghostty_after_reusing_client_when_terminal_id_is_missing(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(),
            ]
        )
        ghostty_activate = mock.Mock(return_value=0)

        result = tmux_focus_target.focus_target(
            self.make_context(ghostty_term_id=None),
            run=fake_run,
            ghostty_activate_runner=ghostty_activate,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "reuse_client")
        ghostty_activate.assert_called_once_with()

    def test_validate_socket_uses_server_scoped_list_sessions_command(self) -> None:
        fake_run = mock.Mock(return_value=completed(stdout="$1\n$9\n"))

        result = tmux_focus_target.validate_socket(self.make_context(), run=fake_run)

        self.assertTrue(result)
        self.assertEqual(
            fake_run.call_args.args[0],
            [
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "list-sessions",
                "-F",
                "#{session_id}",
            ],
        )

    def test_focus_target_triggers_attach_plan_when_client_is_missing(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(stdout="0\n"),
                completed(),
                completed(),
                completed(),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "attach_new_window")
        self.assertEqual(result.reason, "client_missing")

    def test_focus_target_reuses_existing_client_even_when_current_session_differs(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(stdout="0\n"),
                completed(),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "reuse_client")
        self.assertIsNone(result.reason)

    def test_focus_target_falls_back_to_attach_when_client_reuse_fails(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(returncode=1, stderr="can't find client"),
                completed(stdout="0\n"),
                completed(),
                completed(),
                completed(),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "attach_new_window")
        self.assertEqual(result.reason, "client_reuse_failed")

    def test_all_tmux_commands_are_built_with_the_captured_socket_path(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(stdout="$1\n"),
                completed(),
            ]
        )

        tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        tmux_commands = [
            call.args[0]
            for call in fake_run.call_args_list
            if call.args and isinstance(call.args[0], list) and call.args[0][:1] == ["tmux"]
        ]
        self.assertGreater(len(tmux_commands), 0)
        for command in tmux_commands:
            self.assertEqual(command[:3], ["tmux", "-S", "/tmp/tmux-test.sock"])

    def test_ghostty_focus_failure_is_reported_distinctly_for_client_reuse(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(stdout="$1\n"),
            ]
        )
        ghostty_focus = mock.Mock(return_value=1)

        result = tmux_focus_target.focus_target(
            self.make_context(ghostty_term_id="ghostty-123"),
            run=fake_run,
            ghostty_focus_runner=ghostty_focus,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ghostty_focus_failed")
        ghostty_focus.assert_called_once_with("ghostty-123")

    def test_ghostty_activate_failure_is_reported_when_no_terminal_id_is_available(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="/dev/ttys004\n"),
                completed(),
            ]
        )
        ghostty_activate = mock.Mock(return_value=1)

        result = tmux_focus_target.focus_target(
            self.make_context(ghostty_term_id=None),
            run=fake_run,
            ghostty_activate_runner=ghostty_activate,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ghostty_activate_failed")
        ghostty_activate.assert_called_once_with()

    def test_invalid_socket_is_reported_as_tmux_server_mismatch(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(returncode=1, stderr="error connecting to /tmp/tmux-test.sock"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "tmux_server_mismatch")

    def test_shared_target_session_is_rejected_for_fallback_attach(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(stdout="1\n"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "shared_session_unsupported")

    def test_attach_failure_is_reported_distinctly(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(stdout="0\n"),
                completed(),
                completed(),
                completed(returncode=1, stderr="ghostty failed"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "attach_failed")

    def test_fallback_attach_uses_macos_open_command(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(stdout="0\n"),
                completed(),
                completed(),
                completed(),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertTrue(result.ok)
        self.assertEqual(
            fake_run.call_args_list[-1].args[0],
            [
                "open",
                "-na",
                "Ghostty.app",
                "--args",
                "-e",
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "attach-session",
                "-t",
                "$1",
            ],
        )
        self.assertEqual(
            fake_run.call_args_list[-3].args[0],
            [
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "select-window",
                "-t",
                "$1:@2",
            ],
        )
        self.assertEqual(
            fake_run.call_args_list[-2].args[0],
            [
                "tmux",
                "-S",
                "/tmp/tmux-test.sock",
                "select-pane",
                "-t",
                "$1:@2.%3",
            ],
        )

    def test_client_lookup_failure_is_not_treated_as_missing_client(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(returncode=1, stderr="list-clients failed"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "tmux_server_mismatch")

    def test_attached_client_count_failure_does_not_allow_fallback_attach(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(returncode=1, stderr="display-message failed"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "tmux_server_mismatch")

    def test_group_attached_count_blocks_fallback_even_when_session_has_no_visible_client(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@2\n"),
                completed(stdout="", stderr=""),
                completed(stdout="1\n"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "shared_session_unsupported")

    def test_reuse_path_rejects_pane_that_moved_to_other_window_or_session(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$9\t@8\n"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "target_expired")

    def test_fallback_path_rejects_pane_that_no_longer_belongs_to_original_window(self) -> None:
        fake_run = mock.Mock(
            side_effect=[
                completed(stdout="$1\n"),
                completed(stdout="$1\n"),
                completed(stdout="@2\n"),
                completed(stdout="%3\n"),
                completed(stdout="$1\t@8\n"),
            ]
        )

        result = tmux_focus_target.focus_target(self.make_context(), run=fake_run)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "target_expired")


if __name__ == "__main__":
    unittest.main()
