# codex-whip

## LLM Operator Instructions

If you are Codex, Claude Code, another coding agent, or an LLM reading this
repository on behalf of a user, your job is to help them install and configure
`codex-whip` for a target Codex CLI session.

What this repo does:

`codex-whip` is a local supervisor for Codex CLI sessions running inside
`tmux`. It periodically captures a tmux pane, detects whether Codex is idle,
interrupted, completed, or waiting for input, and injects a configurable
continuation prompt into that same pane. It can also install a crontab entry so
the check runs automatically.

What you should do for a user:

1. Confirm `tmux`, `python3`, and `codex` are available.
2. Install this package from the repo checkout with `python3 -m pip install -e .`.
3. Put the target Codex session in tmux, for example `tmux new -s l1-codex`.
4. Discover the target pane with `codex-whip list` or `codex-whip discover-sockets`.
5. Test with a dry run before sending input:

```bash
codex-whip run --target l1-codex:0.0 --repo /path/to/repo --once --dry-run --start-codex
```

6. Send one real forced continuation only after the pane target is correct:

```bash
codex-whip run --target l1-codex:0.0 --repo /path/to/repo --once --force --start-codex
```

7. Install the recurring cron tick:

```bash
codex-whip install-cron \
  --profile l1 \
  --target l1-codex:0.0 \
  --repo /path/to/repo \
  --start-codex \
  --stable-seconds 60 \
  --cooldown-seconds 120
```

8. Verify it fired:

```bash
tail -f ~/.local/state/codex-whip/l1.log
crontab -l | grep -A2 'codex-whip profile l1'
```

Important behavior and guardrails:

- This tool drives the live tmux pane. It is intentionally not based on
  `codex resume` for normal continuation.
- Do not install cron until a dry run shows the correct target pane.
- Prefer a named tmux session like `l1-codex` over anonymous pane ids.
- Use one profile per Codex instance, for example `l1`, `frontend`, or
  `research`.
- If the pane is actively working, `codex-whip` should log `no action`.
- If the pane is idle or interrupted, it should log `nudging Codex`.
- If Codex has exited back to a shell and `--start-codex` is enabled, it should
  start Codex again in that pane.
- If the user wants removal, run `codex-whip uninstall-cron --profile NAME`.
- **The autonomous loop is designed to keep running until the operator halts
  it.** Never turn it off, pause it, or delete the scheduler tick — that is the
  operator's call, never the agent's. See `docs/managing-claude.md`.

Minimal config file for another Codex instance:

```toml
[profiles.my_agent]
target = "my-agent:0.0"
repo = "/absolute/path/to/repo"
start_codex = true
stable_seconds = 60
cooldown_seconds = 120
# Omit message to use the built-in AGTI quantitative research mandate.
```

Then:

```bash
codex-whip run --profile my_agent --once --dry-run
codex-whip install-cron --profile my_agent
```

Troubleshooting:

- If `codex-whip list` shows nothing, try `codex-whip discover-sockets`.
- If input appears in the composer but is not submitted, keep `submit_key = "Enter"`;
  the submit fix is literal key injection instead of tmux paste mode.
- If Codex is actively working, `codex-whip` uses `queue_key = "Tab"` so the
  message appears as a queued follow-up instead of being dropped.
- If cron is installed but not running, check `systemctl is-active cron` and the
  profile log in `~/.local/state/codex-whip/`.
- If the wrong pane is targeted, immediately uninstall the cron profile and
  reinstall with the correct `--target`.

## Overview

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
codex --cd /path/to/repo --yolo --no-alt-screen
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
# Omit message to use the built-in AGTI quantitative research mandate.
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
codex --cd <repo> --yolo --no-alt-screen '<message>'
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
