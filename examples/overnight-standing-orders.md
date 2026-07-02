# Template: Overnight Nazgûl Standing Orders

Copy this file somewhere outside the supervised repos (e.g. `~/repos/orc_directives/`),
fill in the `<placeholders>`, then arm the loop per
[Managing a Claude Code Nazgûl](../docs/managing-claude.md): one durable recurring
scheduler job (e.g. every 15 min) whose prompt says
"follow <path-to-this-file> exactly" and names the orc sessions.

---

# Overnight Nazgûl Standing Orders — <date>

Operator: <name>. Manager: Nazgûl (Claude Code session, woken every <N> min by the harness
scheduler). Orcs under supervision (Codex CLI in tmux):

- `<orc-session-1>:0.0` — <what it is working on; path to its mandate file>
- `<orc-session-2>:0.0` — <what it is working on; path to its mandate file>

Goal: keep the orcs productive overnight WITHOUT continuous monitoring. One short tick per
schedule fire. Token frugality is a hard requirement: capture pane tails only (~50 lines),
never read full transcripts, read only the summary/directive files named below.

## Rule 0 — model-downgrade kill switch (checked FIRST, every tick)

At the start of every tick, verify the model powering this manager session. It must be
`<expected-model>`. If it has been downgraded (e.g. to a lower tier) for ANY reason:
STOP THE SESSION — touch no orc, append a `NAZGUL DOWNGRADED to <model>` line to the state
file, write `<directives-dir>/NAZGUL_STOPPED_MODEL_DOWNGRADE.md`, delete the scheduler job
(pre-authorized by the operator as the only exception to the never-pause rule), and end the
turn. A downgraded manager must not keep directing orcs on the operator's behalf.

## Per-tick protocol

For EACH orc, in order:

1. Capture: `tmux capture-pane -t <orc>:0.0 -p -S -60 | sed '/^[[:space:]]*$/d' | tail -50`
2. Classify:
   - BUSY — tail shows `Working (` or `esc to interrupt` → do nothing. Never interrupt,
     never send Esc.
   - IDLE at the input prompt → step 3.
   - Approval prompt → approve only if plainly within the orc's mandate and non-reserved;
     otherwise log it and leave for morning.
3. If IDLE and no fresh summary was requested this pause, inject (one line, <170 chars):
   `Pause checkpoint: write a markdown summary of work since your last summary — done, evidence paths, blockers, next-step candidates — to <directives-dir>/<orc>_status_<HHMM>.md then stop.`
4. Injection mechanics (Codex): `tmux send-keys -t <orc>:0.0 -l '<line>'; sleep 1;
   tmux send-keys -t <orc>:0.0 Enter`; after ~2s re-capture the last 5 lines — if still at
   the idle prompt, re-send Enter (max 2 retries). Never inject into a busy pane.
5. After requesting a summary: `sleep 180`, then check for the file once. If present:
   read it, decide the next increment (see Direction below), write it as a NEW directive
   file `<directives-dir>/<orc>_directive_<HHMM>.md` (concrete tasks, completion evidence
   required, stop conditions), then inject:
   `Read <directives-dir>/<orc>_directive_<HHMM>.md and execute it. Stop at its listed gates.`
   If the summary is not there yet, end the turn — the next tick handles it.
6. Append ONE line per orc to `<directives-dir>/nazgul_overnight_state_<date>.md`:
   `HH:MM <orc> BUSY|IDLE action=<none|summary-requested|directed:<file>> note=<≤15 words>`
   Read this state file at the START of every tick (it is the only cross-tick memory).

## Direction policy

- <orc-1>: <which mandate/backlog to drive, in what order; stop-rule reminders>
- <orc-2>: <same>
- Both: prefer finishing + documenting over opening new fronts late in the night, so the
  morning report has closed loops.

## Reserved / forbidden overnight (log for morning instead)

- Anything that moves money or changes user-facing economic state — operator only, always.
- No production deploys (exception: rollback of an actively broken prod, logged loudly).
- No pushes/merges beyond what a mandate explicitly authorizes.
- Never kill/pause the scheduler tick, the tmux sessions, or in-flight work. If an orc is
  hard-stuck (same error loop across two ticks), direct it to write a failure report and
  stand by — do not restart its session.

## Morning handoff

First tick after <morning-hour> UTC: write
`<directives-dir>/nazgul_overnight_report_<date>.md` — per orc: work completed (with
evidence paths), directives issued, open blockers, reserved items queued for the operator.
Then continue ticking normally until the operator says otherwise.
