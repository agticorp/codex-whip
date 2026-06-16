# codex-whip

`codex-whip` supervises and orchestrates **Codex CLI** sessions running in
`tmux`. It captures a pane, classifies what the agent is doing
(working / waiting / needs-approval / idle / errored), and either nudges it
onward or hands control to a *manager* that decides the next move.

It supports two operating modes:

- **The whip (autonomous keep-alive):** when the Codex session stalls,
  inject a configured continuation prompt so it keeps working. Optional
  cron tick. This is the original behaviour — a slave-driver cracking the
  whip to keep the orc marching.
- **The Nazgûl / Orc loop (managed):** a manager process (typically another
  LLM agent — Claude, etc.) watches the session, and *at every stop decides
  what to do* — direct the agent onward, escalate to the human, or do the
  merge/documentation itself. The whip is the muscle; the manager is the
  mind.

This site documents the **managed loop** — the pattern, the mechanics, and
how to port it onto a new machine.

## The cast (so the rest of the docs make sense)

| role | who | job |
|---|---|---|
| **Sauron** | the human principal | sets the goal; signs off on anything reserved |
| **Nazgûl** | the manager agent (LLM) | reads the orc at each stop, decides, reports up, merges, scribes the docs |
| **Orc** (Uruk-hai) | the Codex CLI session | does the actual building, in `tmux` |
| **The Eye** | an idle-watcher | sees when the orc stops and wakes the Nazgûl |
| **The Whip** | `codex-whip` | drives the pane (capture / classify / inject); the dumb keep-alive fallback |

The loop: **the Eye watches → the orc stops → the Nazgûl descends, reads,
and commands (or escalates / merges) → the Eye watches again.**

## Start here

- **[The Nazgûl / Orc Pattern](nazgul-orc.md)** — the model and why
  manager-decides-on-stop beats a static nudge. Includes the **two agent
  classes / two keep-alive mechanisms** split (Codex orc = whip; Claude Code
  Nazgûl = harness scheduler).
- **[Managing a Claude Code Nazgûl](managing-claude.md)** — how to run a
  Claude Code session as the manager: keep it alive with the harness scheduler
  (NOT the whip — tmux injection gets stuck on Claude Code), and the read/decide/inject cycle against its Codex orc.
- **[The Operating Loop](operating-loop.md)** — the concrete mechanics:
  reading, deciding, injecting (with the bracketed-paste gotcha), the Eye
  watcher, and the guardrails.
- **[Porting to a New Machine](porting.md)** — copy-paste setup.
- **[Instrumentation Roadmap](instrumentation.md)** — baking the loop into
  `codex-whip` itself (`--on-idle` hook, library API).
