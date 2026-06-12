# The Operating Loop

The managed loop is four moves: **watch → read → decide → inject**, then
re-arm the watcher. Each move is a thin tmux operation; the intelligence is
entirely in *decide*.

## 1. Watch — the Eye

A background process tails the Codex pane and exits the instant the agent
goes idle, so the manager only spends a cycle when there is actually
something to do (event-driven, not a timer). Idle = the pane has been
**byte-stable for ~36s and shows no active "Working (" spinner.**

```bash
# orc_watch.sh — exits when the Codex session stops
SESSION="${1:-codex}"
prev=""; stable=0; max=200
for i in $(seq 1 $max); do
  cur=$(tmux capture-pane -t "$SESSION" -p -S -45 2>/dev/null) || { echo "SESSION GONE"; exit 0; }
  if [ "$cur" = "$prev" ]; then stable=$((stable+1)); else stable=0; fi
  prev="$cur"
  if [ "$stable" -ge 3 ] && ! printf '%s' "$cur" | grep -q "Working ("; then
    echo "=== STOPPED (elapsed ~$((i*12))s) ==="; break
  fi
  sleep 12
done
echo "=== FINAL PANE ==="
tmux capture-pane -t "$SESSION" -p -S -60 2>/dev/null | tail -60
```

Run it so its completion *notifies the manager* (e.g. as a background task
whose exit re-invokes the manager agent). The spinner increments every
second while the orc works, so the pane is never stable mid-task — it only
stabilises once the orc has genuinely stopped.

## 2. Read

```bash
tmux capture-pane -t codex -p -S -60 | tail -60
```

Read the orc's last actions and its final summary. Classify: did it *finish
a unit* (→ direct onward), *ask / hit an approval prompt* (→ answer or
escalate), *complete a reviewable deliverable* (→ merge + doc), or *error*
(→ debug)?

## 3. Decide

This is the Nazgûl's judgement, against the mandate. The only rule the
mechanics enforce: **reserved actions escalate, everything else proceeds.**

## 4. Inject — the recipe (and the gotcha)

Codex's TUI takes a paste, not typed keys. Use a tmux buffer with
**bracketed paste (`-p`)**, a short delay, then the submit key.

```bash
printf '%s' "your full directive on ONE line, no newlines" > /tmp/dir.txt
tmux load-buffer /tmp/dir.txt
tmux paste-buffer -p -t codex          # -p = bracketed paste (required)
# verify exactly ONE copy is in the box before submitting:
tmux capture-pane -t codex -p -S -4 | tail -4
sleep 1                                  # a beat before Enter, or it won't submit
tmux send-keys -t codex Enter
```

!!! warning "Two failure modes that will bite you"
    - **No delay before Enter** → the paste lands but the prompt does not
      submit. Wait ~1s (this is why `codex-whip`'s own injector sleeps
      `paste_submit_delay` before the submit key).
    - **Double paste** → Codex collapses a big paste into a
      `[Pasted Content N chars]` chip; pasting twice stacks two chips and
      submits the directive duplicated. Paste **once**, verify one chip,
      then Enter. To clear a stray chip, `send-keys -t codex BSpace`.

Keep directives to a single line (no embedded newlines) so a stray newline
can't submit early.

## Re-arm

After injecting, start the Eye again. The loop continues until the work is
done or the human halts it.

## Guardrails the manager enforces

- **Read-only by default.** The orc proves / tests / reads / commits; it
  does not touch secrets, keys, funds, or anything reserved. Those escalate.
- **Reconcile to ground truth.** Every number the orc produces must match an
  independent oracle (in the StakeHub example: the ZK proof's outputs must
  equal what the existing `stakehub por` reports at the same block).
- **Phase gates.** Don't let the orc cross a milestone boundary without a
  manager review of the deliverable against acceptance criteria.
- **Load the full non-blocked queue** every time you dispatch, so the orc
  never idles next to work it could be doing while a reserved item waits on
  the human.

## Worked example

The StakeHub *Proof-of-Leverage (ZK)* build runs exactly this loop: a Claude
manager drove a Codex orc through the EVM/Aave leg — scaffold, then oracle
hardening, then the end-to-end proof — committing and reconciling each
cycle, escalating only the one action that needed the operator's signing
key. ~20-25 min orc bursts, a short manager beat between, human touched only
at the real decision.
