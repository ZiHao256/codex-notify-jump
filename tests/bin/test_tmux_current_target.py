import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = REPO_ROOT / "bin"
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))

import tmux_current_target  # type: ignore  # noqa: E402


class TmuxCurrentTargetTests(unittest.TestCase):
    def test_parse_tmux_target_line_extracts_fields(self) -> None:
        line = "$1\t@12\t%3\twork\t/dev/ttys004"

        result = tmux_current_target.parse_tmux_target_line(line)

        self.assertEqual(
            result,
            {
                "session_id": "$1",
                "window_id": "@12",
                "pane_id": "%3",
                "session_name": "work",
                "client_tty": "/dev/ttys004",
            },
        )

    def test_parse_tmux_env_extracts_socket_path(self) -> None:
        env_value = "/private/tmp/tmux,501/default,12345,0"

        result = tmux_current_target.parse_tmux_env(env_value)

        self.assertEqual(result, "/private/tmp/tmux,501/default")

    def test_parse_tmux_target_line_rejects_empty_output(self) -> None:
        with self.assertRaises(ValueError):
            tmux_current_target.parse_tmux_target_line("")

    def test_parse_tmux_target_line_rejects_malformed_output(self) -> None:
        with self.assertRaises(ValueError):
            tmux_current_target.parse_tmux_target_line("$1\t%12\t%3\twork")

    def test_parse_tmux_target_line_rejects_incomplete_fields(self) -> None:
        with self.assertRaises(ValueError):
            tmux_current_target.parse_tmux_target_line("$1\t%12\t%3\twork\t")

    def test_main_returns_nonzero_outside_tmux(self) -> None:
        fake_run = mock.Mock()
        stdout = io.StringIO()

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(tmux_current_target.subprocess, "run", fake_run):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertNotEqual(exit_code, 0)
        fake_run.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")

    def test_main_emits_json_for_valid_tmux_state(self) -> None:
        target_output = "$1\t@12\t%3\twork\t/private/tmp/tmux,501/default\n"
        client_output = "/dev/ttys004\n"
        fake_run = mock.Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout=target_output, stderr=""),
                SimpleNamespace(returncode=0, stdout=client_output, stderr=""),
            ]
        )
        stdout = io.StringIO()

        with mock.patch.dict(
            os.environ,
            {"TMUX": "/wrong/socket,12345,0", "TMUX_PANE": "%3"},
            clear=True,
        ):
            with mock.patch.object(tmux_current_target.subprocess, "run", fake_run):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload,
            {
                "socket_path": "/private/tmp/tmux,501/default",
                "session_id": "$1",
                "window_id": "@12",
                "pane_id": "%3",
                "session_name": "work",
                "client_tty": "/dev/ttys004",
            },
        )

    def test_main_invokes_tmux_with_expected_argv(self) -> None:
        target_output = "$1\t@12\t%3\twork\t/private/tmp/tmux,501/default\n"
        client_output = "/dev/ttys004\n"
        fake_run = mock.Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout=target_output, stderr=""),
                SimpleNamespace(returncode=0, stdout=client_output, stderr=""),
            ]
        )
        stdout = io.StringIO()
        expected_pane = "%3"

        with mock.patch.dict(
            os.environ,
            {"TMUX": "/wrong/socket,12345,0", "TMUX_PANE": expected_pane},
            clear=True,
        ):
            with mock.patch.object(tmux_current_target.subprocess, "run", fake_run):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_run.call_count, 2)
        self.assertEqual(
            fake_run.call_args_list[0].args[0],
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                expected_pane,
                "#{session_id}\t#{window_id}\t#{pane_id}\t#{session_name}\t#{socket_path}",
            ],
        )
        self.assertEqual(
            fake_run.call_args_list[1].args[0],
            [
                "tmux",
                "display-message",
                "-p",
                "#{client_tty}",
            ],
        )

    def test_main_returns_nonzero_when_subprocess_raises_oserror(self) -> None:
        stdout = io.StringIO()

        with mock.patch.dict(
            os.environ,
            {"TMUX": "/wrong/socket,12345,0", "TMUX_PANE": "%3"},
            clear=True,
        ):
            with mock.patch.object(
                tmux_current_target.subprocess,
                "run",
                side_effect=OSError("tmux missing"),
            ):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertNotEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_main_returns_nonzero_without_tmux_pane(self) -> None:
        fake_run = mock.Mock()
        stdout = io.StringIO()

        with mock.patch.dict(
            os.environ,
            {"TMUX": "/wrong/socket,12345,0"},
            clear=True,
        ):
            with mock.patch.object(tmux_current_target.subprocess, "run", fake_run):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertNotEqual(exit_code, 0)
        fake_run.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")

    def test_main_returns_nonzero_when_target_query_fails(self) -> None:
        fake_run = mock.Mock(
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="error")
        )
        stdout = io.StringIO()

        with mock.patch.dict(
            os.environ,
            {"TMUX": "/wrong/socket,12345,0", "TMUX_PANE": "%3"},
            clear=True,
        ):
            with mock.patch.object(tmux_current_target.subprocess, "run", fake_run):
                with redirect_stdout(stdout):
                    exit_code = tmux_current_target.main()

        self.assertNotEqual(exit_code, 0)
        self.assertEqual(fake_run.call_count, 1)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
