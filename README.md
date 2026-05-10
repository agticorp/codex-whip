# codex-whip

`codex-whip` keeps a long-running Codex CLI session moving from a `tmux` pane.
It captures a target pane, detects idle/interrupted/stopped states, and sends a
continuation mandate back into the live Codex TUI. It can also install a cron
tick so the check runs every minute.

The tool is intentionally small and local:

- no Python runtime dependencies,
- no `codex resume` dependency for normal nudges,
- configurable prompt, target pane, tmux socket, state/log paths, and start command,
- cron install/uninstall helpers with marked crontab blocks,
- dry-run mode for safe testing.

## Install

From a checkout:

```bash
python3 -m pip install -e .
```

## Quick Start

Start Codex in tmux:

```bash
tmux new -s l1-codex
codex --cd /path/to/repo --dangerously-bypass-approvals-and-sandbox --ask-for-approval never --no-alt-screen
```

From another terminal:

```bash
codex-whip list
codex-whip run --target l1-codex:0.0 --repo /path/to/repo --once --force
```

Install a cron tick:

```bash
codex-whip install-cron \
  --profile l1 \
  --target l1-codex:0.0 \
  --repo /path/to/repo \
  --start-codex \
  --stable-seconds 60 \
  --cooldown-seconds 120
```

Inspect logs:

```bash
tail -f ~/.local/state/codex-whip/l1.log
```

Remove the cron tick:

```bash
codex-whip uninstall-cron --profile l1
```

## Config File

By default, `codex-whip` reads:

```text
~/.config/codex-whip/config.toml
```

Example:

```toml
[profiles.l1]
target = "l1-codex:0.0"
repo = "/home/postfiat/repos/postfiatl1v2"
start_codex = true
stable_seconds = 60
cooldown_seconds = 120
message = "You are the CTO. Keep going without interruption and use your best judgement to advance the project."
```

Then run:

```bash
codex-whip run --profile l1 --once
codex-whip install-cron --profile l1
```

## How Detection Works

`codex-whip` uses `tmux capture-pane` and looks for:

- interrupted/completed Codex output,
- idle composer prompts,
- approval prompts,
- output that has stayed stable longer than `stable_seconds`.

It avoids injecting while Codex is actively working by checking for the live
`Working (... esc to interrupt)` indicator.

## Runtime Assumptions

- `tmux` is installed.
- Codex is running in a tmux pane.
- Cron install assumes a Unix-like crontab and uses `flock` when available.
- The default restart command launches:

```bash
codex --cd <repo> --dangerously-bypass-approvals-and-sandbox --ask-for-approval never --no-alt-screen '<message>'
```

You can override it:

```bash
codex-whip run --target l1-codex:0.0 --start-command 'codex --cd {repo} --no-alt-screen {prompt}'
```

Placeholders:

- `{repo}` shell-quoted repo path,
- `{prompt}` shell-quoted continuation prompt,
- `{prompt_raw}` raw prompt text.

## Development

```bash
python3 -m unittest discover -s tests
python3 -m codex_whip.cli --help
```
