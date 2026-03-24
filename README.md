# codex-notify-jump

[中文说明](README.zh-CN.md)

Clickable macOS notifications for Codex CLI that jump back to the originating Ghostty + tmux pane.

## What It Does

- Sends macOS notifications for Codex CLI events
- Adds a `Jump` button to each notification
- Activates Ghostty and switches back to the originating tmux pane

This repository is intentionally narrow in scope. The first release only targets `macOS + Ghostty + tmux + Codex CLI`.

## Supported Environment

- macOS
- Ghostty
- tmux
- Codex CLI
- zsh
- Python 3
- Swift toolchain with `swiftc`

## How It Works

1. A shell wrapper captures the current Ghostty terminal id and tmux pane metadata before launching `codex`.
2. Codex calls the configured `notify.py` hook.
3. `notify.py` builds a clickable local notifier with a `Jump` action.
4. Clicking `Jump` focuses Ghostty and switches the tmux client back to the original pane.

## Installation

### 1. Clone the repository

```bash
git clone <REPO_URL>
cd codex-notify-jump
```

### 2. Verify required tools

```bash
python3 --version
tmux -V
swiftc --version
```

## Configure Codex

Add the notify hook to your Codex `config.toml`:

```toml
notify = ["python3", "/ABSOLUTE/PATH/TO/codex-notify-jump/bin/notify.py"]

[tui]
notifications = ["agent-turn-complete", "approval-requested"]
```

You can use [`examples/config.toml`](examples/config.toml) as a template.

## Configure Your Shell

Add the wrapper from [`examples/zshrc.snippet`](examples/zshrc.snippet) to your `~/.zshrc`, then replace:

- `"/ABSOLUTE/PATH/TO/codex-notify-jump"`

with the real repository path.

Reload your shell:

```bash
source ~/.zshrc
```

## Verify the Setup

### Verify Ghostty terminal id lookup

Run this in a normal Ghostty pane:

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/ghostty_current_terminal_id.py
```

Run the same command inside a tmux pane:

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/ghostty_current_terminal_id.py
```

Both should print a non-empty terminal id.

### Verify tmux target capture

Inside the target tmux pane:

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/tmux_current_target.py
```

This should print JSON with:

- `socket_path`
- `session_id`
- `window_id`
- `pane_id`
- `client_tty`

### Verify notifications

Trigger a Codex notification, then click `Jump`.

Expected result:

- Ghostty becomes active
- tmux switches back to the originating pane

## Troubleshooting

### I see a notification, but there is no `Jump` button

Check that the bundled notifier can be compiled:

```bash
swiftc --version
```

### Clicking `Jump` only activates Ghostty

This usually means `CODEX_GHOSTTY_TERM_ID` was not captured correctly when `codex` started.

### Ghostty activates, but not on the correct pane

This usually means tmux client switching succeeded in the background, but Ghostty terminal focus metadata was incomplete.

### `ghostty_current_terminal_id.py` prints nothing

Verify that Ghostty is frontmost and that AppleScript access works in your environment.

### `tmux_current_target.py` prints nothing

Make sure you are running it inside a tmux pane and that `TMUX_PANE` is set.

## Development

Run the test suite with:

```bash
python3 -m unittest -v \
  tests.bin.test_tmux_current_target \
  tests.bin.test_tmux_focus_target \
  tests.bin.test_notify
```

The tests cover:

- tmux target capture
- tmux focus planning and fallback behavior
- notification routing and click command construction

## Known Limitations

- Only supports `macOS + Ghostty + tmux + Codex CLI`
- Only documented for `zsh`
- Depends on Ghostty AppleScript behavior
- Uses an explicit `Jump` button rather than notification body clicks

## License

[MIT](LICENSE)
