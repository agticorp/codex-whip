# The Nazgûl / Orc Pattern

## The problem with a dumb whip

The simplest way to keep an autonomous coding agent productive is to detect
when it stalls and inject *"keep going."* That works until the agent
**finishes a unit of work and stops on purpose** — because the next move
isn't "keep going," it's a *decision*: commit and move to the next task?
escalate a question to the human? this output needs review and a merge?
A static nudge can't tell these apart, so it either barrels the agent past
a gate it should have stopped at, or wastes cycles re-prompting it to do
something it already finished.

## The fix: a mind at every stop

Put a **manager** between the human and the agent. The agent (the **Orc**)
does the building. A lightweight **Eye** watches the agent's terminal and
fires the moment it stops. That wakes the **Nazgûl** — the manager, usually
another LLM agent — which *reads the agent's actual state* and chooses:

- **Direct onward** — the agent finished a unit; inject the next concrete
  task. Keep it moving without bothering the human.
- **Report up** — the agent hit a gate, asked a question, or needs a
  human-reserved decision (credentials, spend, a design call). Surface it
  to **Sauron**.
- **Merge / document** — the agent produced a reviewable deliverable. The
  Nazgûl reviews it against acceptance criteria, merges, and writes the
  docs itself.

The manager is the intelligence; `codex-whip` is the muscle that reads the
pane and injects what the manager decides.

## Why this scales

- **The human is only interrupted at real decisions**, not every idle tick.
- **The agent never sits at a gate** *as long as the manager loads it with
  all non-blocked work* — the most common failure mode is the manager being
  too conservative and under-dispatching, leaving the orc idle next to a
  full backlog. Load the queue; reserve only what truly needs the human.
- **Guardrails are enforced by the manager**, not hoped for: read-only by
  default, escalate the reserved actions, reconcile every output against a
  ground-truth oracle, and gate phase transitions on review.

## Roles in one table

| role | maps to | reserved powers |
|---|---|---|
| **Sauron** | human principal | the goal; final sign-off; anything that spends, signs, or ships |
| **Nazgûl** | manager LLM | direct / escalate / merge / document; enforces guardrails |
| **Orc** | Codex CLI in tmux | build, test, commit within the mandate; escalate the rest |
| **The Eye** | idle-watcher | detect "stopped"; wake the Nazgûl |
| **The Whip** | `codex-whip` | capture / classify / inject; dumb keep-alive fallback |

> The discipline that makes it work: **the orc is read-only and bounded by
> default.** It proves, tests, and commits, but it never touches secrets,
> funds, or anything reserved — it escalates those to the Nazgûl, who
> escalates to Sauron. Power flows down only by explicit grant.

## Two agent classes, two keep-alive mechanisms

The cast splits into two classes, and they are **kept alive differently**.
Conflating them is the classic failure:

| role | example | keep-alive |
|---|---|---|
| **Orc** (builder) | Codex CLI in tmux | **the whip**: tmux cron captures the pane, classifies state, injects a continuation. Built for this. |
| **Nazgûl** (manager) | Claude Code in tmux | **the harness scheduler**: enqueues the next turn when the REPL is idle. *Not* the whip. |

Why the split: the whip drives a pane via `tmux send-keys` + Enter, which
Codex's TUI accepts but **Claude Code's does not** — Claude Code leaves a
pasted line unsubmitted and its `esc to interrupt` busy signal is intermittent,
so the whip can't reliably nudge a Claude pane (the tick gets pasted but never
fires). The harness scheduler enqueues a Claude Code turn natively, so a Claude
manager is kept looping by the scheduler, while it uses tmux only to read and
inject its Codex orc. Full guide: **[Managing a Claude Code Nazgûl](managing-claude.md)**.
