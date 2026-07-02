# Managing a Claude Code Nazgûl

A **Claude Code** session makes an excellent Nazgûl (the manager): it reads the
orc, decides, and injects the next directive. But it is **not** kept alive the
same way a Codex orc is. Getting this wrong is how you end up with a tick
pasted into the manager's input box that never submits — stuck.

## The loop is designed to KEEP RUNNING — never turn it off

This autonomous loop is **designed to run continuously**, driving the orc
toward the goal (mainnet) until the **operator** explicitly halts it. The
Nazgûl (the manager LLM) **must never turn off, pause, or delete the loop** —
not the scheduler tick, not the cron, nothing. If the orc hits a gate (a spec
ruling, a push, a money decision), the Nazgûl **keeps the loop running**: it
does more spec work, packages evidence, or holds the orc *inside* the loop —
but it does **not** turn off the whip. Turning it off wastes wall-clock time and
is **never the Nazgûl's call**. The operator set this loop running precisely
so they don't have to babysit it; unilaterally stopping it defeats the entire
purpose. **The spec decides everything else — implement it, don't question it.**

## The rule: drive the manager with the harness scheduler, not the whip

The whip's cron injects into a tmux pane via `tmux send-keys` + an Enter key.
That model fits **Codex's** TUI. It does **not** fit Claude Code's:

- Claude Code's composer does **not** reliably submit a pre-filled line on a
  tmux `Enter` — the pasted text lands in the input box but the submit doesn't
  fire, so the tick sits there unsubmitted.
- Claude Code's busy signal (`… · esc to interrupt`) is intermittent (it comes
  and goes from the status bar rather than tracking work cleanly), so the
  whip's busy/idle classifier can't reliably tell working from idle — it either
  never chooses to nudge or thinks a stuck pane is busy.

Net effect of pointing the whip at a Claude pane: the tick gets **pasted but
not submitted** — the manager is never actually prompted. Patching the submit
(verify-and-retry, longer settle, `Enter` vs `C-m`) does not fix it, because
the paste/submit/detection layer underneath does not match Claude Code's TUI.

The reliable keep-alive for a Claude Code manager is the **harness's own
scheduler**: it enqueues the Nazgûl tick as the manager's next turn whenever
the REPL is idle. No tmux, no `send-keys`, no Enter, no busy-detection — the
turn is delivered natively.

## Setup (recurring self-prompt)

Create one recurring job per manager session, via the harness scheduler (e.g.
the `CronCreate` tool in Claude Code):

```
cron      = "*/2 * * * *"      # every 2 min
recurring = true
durable   = true               # survives session restarts
prompt    = "Nazgûl: drive your orc <orc-session>:0.0 toward <goal>. "
            "Follow <standing-orders.md>; work the next increment of <spec>. "
            "Spend authorized. Read the orc, decide, inject; don't pause."
```

Notes:

- The job fires **only while the manager is idle** — it will not interrupt a
  working turn.
- Recurring jobs auto-expire after 7 days; recreate if the push runs longer.
- One job per manager session. **Only the operator cancels it when the work is
  done — the Nazgûl NEVER turns off, pauses, or deletes the loop.** (See
  "The loop is designed to KEEP RUNNING" above.)

## The cycle (each scheduler tick)

1. **Read the orc** (Codex, in its own tmux session):
   `tmux capture-pane -t <orc>:0.0 -p -S -60 | sed '/^[[:space:]]*$/d' | tail -50`
2. **Decide** against the spec/mandate: still working → end the turn; finished
   a unit → inject the next directive; produced a commit → review (diff + gate
   + reproduce) then accept; errored → inject a fix; hit a gate/question →
   answer or escalate.
3. **Inject** into the orc (Codex — tmux works here):
   `tmux send-keys -t <orc>:0.0 -l '<one-line directive>'; sleep 1; tmux send-keys -t <orc>:0.0 Enter`
   (keep directives to one line, no embedded newlines; for a long directive use
   `load-buffer` + `paste-buffer -p`, verify exactly one chip, then `Enter`).
4. End the turn; the scheduler re-ticks when idle.

## What the manager touches via tmux: the orc, never itself

The manager uses tmux to **read and inject the Codex orc**. It must **not**
tmux-inject into its *own* Claude Code pane — that is the broken path above.
Its own re-prompting comes from the harness scheduler; its tmux traffic is
entirely against the orc.

## Files

- Standing orders (the manager reads these each cycle): a markdown mandate the
  tick points at, e.g. `~/.config/codex-whip/<orc>-nazgul.md`.
- The spec/roadmap under test: the repo's master spec, named in the tick.

## Replicating this setup in a fresh Claude Code session

Everything a new manager session needs is in this repo. Give the session one prompt:

```
Clone https://github.com/agticorp/codex-whip and read docs/nazgul-orc.md and
docs/managing-claude.md. Then supervise the tmux orc session(s) <name>:0.0 against
<path-to-mandate>: copy examples/overnight-standing-orders.md to a directives
directory outside the supervised repos, fill in the placeholders, and arm a durable
recurring scheduler job (every 15 min) whose prompt tells you to follow that
standing-orders file exactly. Never interrupt a busy orc; never pause the loop.
```

Two things intentionally do NOT live in this repo and must be created per machine:
the scheduler job itself (it lives in the Claude Code harness, e.g.
`.claude/scheduled_tasks.json` when durable), and the directives directory with its
standing-orders/state/summary files (working state, not source).
