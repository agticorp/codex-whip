# Instrumentation Roadmap

Today `codex-whip` is a complete *whip*: it captures the pane, classifies
state well, and injects a **static** continuation string (cron-driven). The
managed loop currently lives *outside* the package (the manager shells out
to `tmux` directly). These changes pull the loop *into* the package, so the
whip can summon a mind instead of only cracking.

The package is a single module, `codex_whip/cli.py`. The relevant seams:

| function | role today |
|---|---|
| `capture_pane` | `capture-pane -p -J -S -N -t target` |
| `has_busy_indicator` / `has_waiting_prompt` / `has_approval_prompt` | state classifiers |
| `pane_state`, `decide` → `Decision` | classify and choose an action |
| `choose_message` | pick the **static** continuation string |
| `send_text` | inject via `paste-buffer` + `paste_submit_delay` + submit key |
| `text_digest` | stable-pane hashing |

## 1. `--on-idle <handler>` (the core change)

In `execute_decision`, when the decision is "continue," and an
`on_idle_handler` is configured, **run the handler** with the captured pane
on stdin and inject its **stdout** instead of `choose_message`. Honour
sentinels so the handler can choose *not* to inject:

- `HOLD` — do nothing; leave the orc stopped.
- `ESCALATE: <text>` — surface to the human channel; do not inject.
- anything else — inject it as the next directive.

`choose_message` stays as the fallback when no handler is set. This single
seam turns "mindless nudge" into "summon the Nazgûl."

## 2. Expose a library API

`codex_whip/__init__.py` is empty. Export the primitives so a manager can
script the loop without reimplementing tmux:

```python
from codex_whip import capture, state, inject, wait_until_idle

wait_until_idle("codex", stable_s=36)     # the Eye
text = capture("codex")                    # read
inject("codex", nazgul_decides(text))      # command — or escalate
```

- `capture(target)` → wrap `capture_pane`.
- `state(target)` → wrap `pane_state` (`working|waiting|approval|idle|errored`).
- `inject(target, text)` → wrap `send_text` (keep the `paste_submit_delay`;
  test whether bracketed paste `-p` is needed on the current Codex TUI and
  add it if so — the managed loop empirically needs it from raw `tmux`).
- `wait_until_idle(target, stable_s)` → the Eye, built from `capture_pane`
  + `text_digest` + `has_busy_indicator` (poll, digest-compare, return when
  stable and not busy). This replaces the external `orc_watch.sh`.

## 3. Routing on state

`decide`/`pane_state` already distinguish busy / waiting / approval / idle.
Pass that classification to the handler so the Nazgûl dispatches correctly:
finished-a-unit → next task; approval prompt → approve or escalate; question
→ answer; error → debug. The mechanics detect *that* it stopped; the handler
decides *what* it means.

## Net

`codex-whip` keeps its job — drive the pane, classify state, dumb-nudge
fallback — and gains one hook (`--on-idle`) plus a small API so the manager
becomes the decision-maker. The external watcher and shell-injection in the
managed loop collapse into `wait_until_idle` and `inject`.
