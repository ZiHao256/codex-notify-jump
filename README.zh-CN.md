# codex-notify-jump

[English README](README.md)

一个面向 Codex CLI 的 macOS 可点击通知工具。通知中会带有 `Jump` 按钮，点击后可回到原始的 Ghostty + tmux pane。

## 它能做什么

- 为 Codex CLI 事件发送 macOS 系统通知
- 在通知中加入 `Jump` 按钮
- 激活 Ghostty，并切回最初触发通知的 tmux pane

这个仓库刻意保持小而专。首版只支持 `macOS + Ghostty + tmux + Codex CLI`。

## 支持环境

- macOS
- Ghostty
- tmux
- Codex CLI
- zsh
- Python 3
- 可用的 Swift 编译器 `swiftc`

## 工作原理

1. shell wrapper 在启动 `codex` 之前，先采集当前 Ghostty terminal id 和 tmux pane 元信息。
2. Codex 调用配置好的 `notify.py` hook。
3. `notify.py` 使用本地 Swift helper 构建带 `Jump` 按钮的可点击通知。
4. 点击 `Jump` 后，Ghostty 被激活，tmux client 切回原 pane。

## 安装

### 1. 克隆仓库

```bash
git clone <REPO_URL>
cd codex-notify-jump
```

### 2. 检查依赖

```bash
python3 --version
tmux -V
swiftc --version
```

## 配置 Codex

在你的 Codex `config.toml` 中加入：

```toml
notify = ["python3", "/ABSOLUTE/PATH/TO/codex-notify-jump/bin/notify.py"]

[tui]
notifications = ["agent-turn-complete", "approval-requested"]
```

可以直接参考 [`examples/config.toml`](examples/config.toml)。

## 配置 Shell

把 [`examples/zshrc.snippet`](examples/zshrc.snippet) 中的 wrapper 片段加入你的 `~/.zshrc`，并把下面这个占位符：

- `"/ABSOLUTE/PATH/TO/codex-notify-jump"`

替换成真实仓库路径。

然后重新加载 shell：

```bash
source ~/.zshrc
```

## 验证安装

### 验证 Ghostty terminal id 获取

先在普通 Ghostty pane 中运行：

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/ghostty_current_terminal_id.py
```

再在 tmux pane 中运行同一条命令：

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/ghostty_current_terminal_id.py
```

两次都应该输出非空 terminal id。

### 验证 tmux 目标采集

在目标 tmux pane 中运行：

```bash
python3 /ABSOLUTE/PATH/TO/codex-notify-jump/bin/tmux_current_target.py
```

预期输出包含这些字段的 JSON：

- `socket_path`
- `session_id`
- `window_id`
- `pane_id`
- `client_tty`

### 验证通知跳转

触发一次 Codex 通知，然后点击 `Jump`。

预期结果：

- Ghostty 被激活
- tmux 切回原始 pane

## 排障

### 能看到通知，但没有 `Jump` 按钮

先确认本地 notifier 能被编译：

```bash
swiftc --version
```

### 点击 `Jump` 只激活了 Ghostty

通常说明在启动 `codex` 时，`CODEX_GHOSTTY_TERM_ID` 没有被正确采集。

### Ghostty 被激活了，但不是目标 pane

通常说明 tmux 在后台已经切换成功，但 Ghostty terminal 聚焦元信息不完整。

### `ghostty_current_terminal_id.py` 没有输出

确认 Ghostty 当前在前台，并且 AppleScript 接口在你的环境中可用。

### `tmux_current_target.py` 没有输出

确认你是在 tmux pane 中运行，并且 `TMUX_PANE` 已设置。

## 开发

运行测试：

```bash
python3 -m unittest -v \
  tests.bin.test_tmux_current_target \
  tests.bin.test_tmux_focus_target \
  tests.bin.test_notify
```

当前测试覆盖：

- tmux 目标采集
- tmux 聚焦与 fallback 逻辑
- 通知路由与点击命令构造

## 已知限制

- 仅支持 `macOS + Ghostty + tmux + Codex CLI`
- 当前只文档化 `zsh`
- 依赖 Ghostty 的 AppleScript 行为
- 当前使用显式 `Jump` 按钮，不依赖点击通知正文

## License

[MIT](LICENSE)
