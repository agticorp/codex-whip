# Template: Multi-Orc Supervision Tick

Arm this as a durable recurring scheduler job in the manager session (e.g. every 15
minutes). Use it alongside a domain-specific monitor tick if you have one (for example
a read-only risk monitor every 15 minutes, offset by 7). Fill in the `<placeholders>`.

```text
<PROJECT> orc supervision tick (Nazgûl). Check the <N> Codex orcs in tmux:
<orc-a> (<track A>), <orc-b> (<track B>), <orc-c> (<track C>). For each: capture the
pane tail; confirm the model line reads `<expected-model> <effort>` (if downgraded or
a capacity dialog appeared, fix via /model per Rule 0; on a capacity dialog choose
"Dismiss and keep waiting", never "Retry with a faster model"); if idle at the
prompt, read its last output + <STATUS-LOG>.md and push it to the next item (Codex
false-positive halts get a nudge; a deliberate HOLD gets a decision). Check
<directives-dir>/HOLD-<PROJECT>-*.md for new HOLD files and review/approve/deny them
(verify hashes, byte-identity vs the last approved bundle, scope, abort and rollback;
validator/fleet changes must keep quorum live with per-host rollback). Independently
verify any item an orc marks DONE against the spec's acceptance criteria (never
accept an orc's 'done' at face value). Report to the human only on: an item verified
DONE, a RED, a HOLD needing the human, or a phase completing. Otherwise stay quiet
(one short line).
```

## Companion files

- `<directives-dir>/NAZGUL-DECISIONS-<project>.md`: numbered decisions, append-only.
  Template entry:

  ```markdown
  ## D<n> (<HH:MM>Z <date>). <one-line title> (<TRACK>, <priority>)

  **Facts (verified by the Nazgûl):** <what you checked yourself, with evidence>.
  **Approved:** 1. <scope> 2. <conditions> 3. <deliverable: exact operator commands / evidence path>.
  **Not approved / still gated:** <…>.
  ```

- `<directives-dir>/<STATUS-LOG>.md`: append-only. Each orc writes
  `### <ISO time> — <TRACK> <item> <result>` entries.
- `<directives-dir>/HOLD-<PROJECT>-<item>-<ts>.md`: written by the orc. See the
  checklist in [Multi-Orc Supervision Playbook §5](../docs/multi-orc-playbook.md).
- `<directives-dir>/<ITEM>-TRACKER.md`: the human-facing step table plus a log.

## Directive injection (one line, references the decision)

```bash
tmux send-keys -t <orc> "Nazgûl D<n>: <one-line summary + the key facts + what to do next>. Details D<n>." Enter
sleep 3; tmux send-keys -t <orc> Enter          # long lines often need a 2nd Enter
sleep 6; tmux capture-pane -t <orc> -p | grep -v '^\s*$' | tail -3   # confirm "Working ("
```

To preempt a working orc, send `tmux send-keys -t <orc> Escape` first. Without it the
line is only queued.
