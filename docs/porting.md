# Porting to a New Machine

Everything here is local to one box: a `tmux` session running the orc, an
Eye watcher, and a manager that reads/decides/injects. To stand it up
somewhere new:

## Prerequisites

- `tmux`, `python3`, and the **Codex CLI** (`codex`) installed.
- The target repo checked out, with whatever toolchain the work needs.
- A **manager** able to run shell commands and reason — another LLM agent
  (Claude Code, etc.) is the intended Nazgûl.
- `codex-whip` installed from this repo:

```bash
git clone https://github.com/agticorp/codex-whip.git
cd codex-whip && python3 -m pip install -e .
```

## 1. Start the orc in a named tmux session

Use a stable name (not an anonymous pane id) so injection targets survive.

```bash
tmux new -s codex          # then, inside it:
cd /path/to/repo
codex --yolo               # or your preferred permission mode
```

Detach with `Ctrl-b d`. Re-attach read-only to watch: `tmux attach -t codex -r`.

## 2. Give the orc its mandate (AGENTS.md)

Codex reads `AGENTS.md` at the repo root on startup. Put the **role split,
the hard guardrails, and the first task** there so the orc ramps without
the manager's conversation context. Minimum contents:

- Roles: manager vs execution orchestrator; what each owns.
- Guardrails: read-only by default; never touch secrets/keys/funds; reserved
  actions escalate to the manager.
- Ground-truth reconciliation requirement.
- The current task + acceptance criteria.

## 3. Drop in the Eye

Save `orc_watch.sh` (see [The Operating Loop](operating-loop.md)) and run it
so its **exit notifies the manager**. With Claude Code as the manager, run
it as a background task — its completion re-invokes the manager, which then
reads the pane and dispatches. On other managers, wire the exit to whatever
"wake me" channel you have (a webhook, a queue, a file the manager polls).

## 4. Run the loop

The manager, on each Eye wake:

```bash
tmux capture-pane -t codex -p -S -60 | tail -60   # read
# ...decide...
printf '%s' "next directive (one line)" > /tmp/dir.txt
tmux load-buffer /tmp/dir.txt && tmux paste-buffer -p -t codex
tmux capture-pane -t codex -p -S -4 | tail -4     # verify one chip
sleep 1 && tmux send-keys -t codex Enter          # submit
bash orc_watch.sh codex &                         # re-arm the Eye
```

## Multiple orcs

Run one named session per orc (`codex_l1`, `codex_frontend`, …) and one Eye
each. The manager fans out — read whichever Eye fired, dispatch to that
session. `codex-whip` uses one *profile* per instance for the same reason.

## Fallback: the dumb whip

If no manager is attached, keep the orc alive with `codex-whip`'s static
nudge + cron (dry-run the target first):

```bash
codex-whip run --target codex:0.0 --repo /path/to/repo --once --dry-run --start-codex
codex-whip run --target codex:0.0 --repo /path/to/repo --once --force --start-codex
codex-whip install-cron --profile myorc --target codex:0.0 --repo /path/to/repo \
  --start-codex --stable-seconds 60 --cooldown-seconds 120
```

The managed loop and the dumb whip are not exclusive: the whip is the
safety net for when the Nazgûl is away.
