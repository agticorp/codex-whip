# Multi-Orc Supervision Playbook

This is how a Claude Code Nazgûl runs **several specialised Codex orcs at once** on a
long, gated, real-money build. It distils a 30-hour run with three orcs (platform,
proof, execution) that took a product from spec to live funds. That run included
about a dozen stop-and-fix cycles, a full-disk incident, provider outages and one
founder escalation. Each rule below exists because skipping it cost hours.

The single-orc loop is in [The Operating Loop](operating-loop.md). Keeping the
manager alive is covered in [Managing a Claude Code Nazgûl](managing-claude.md).
This page covers the layer on top: files, ticks, decisions, approvals, verification
and operations hygiene.

## 1. Topology

| Thing | What it is | Rule |
|---|---|---|
| **Orcs** | One Codex session per track, in its own tmux session (`orc-<project>`, `orc-<project>-proof`, `orc-<project>-exec`) | One track per orc. Tracks talk only through files, never through each other's panes. |
| **Status log** | One append-only markdown file all orcs write to (`<PROJECT>-STATUS.md`) | Each entry gets a heading with an ISO timestamp and the track name. The Nazgûl reads the latest headings every tick. |
| **Decisions log** | `NAZGUL-DECISIONS-<project>.md`, with numbered entries D1, D2, … | Every directive is written here first. The injected line then *references* the entry. |
| **HOLD files** | `HOLD-<project>-<item>-<timestamp>.md`, written by an orc | Required for any privileged action: fleet or host changes, signer restarts, deployments, money. Each one holds the exact commands, pinned hashes, scope, abort conditions and rollback. |
| **Approval file** | `approval.json` beside the frozen bundle | `approved:false` until the Nazgûl reviews. The Nazgûl fills in `approved:true` plus `authorization_source: "Nazgul Dnn …"`. |
| **Operator runbook** | `…-OPERATOR-RUNBOOK.md` for live-money steps | The orc prepares it; the Nazgûl runs it one command at a time (§6). |
| **Tracker** | `<ITEM>-TRACKER.md` that the founder can read | A step table with what each step waits on, its time if nothing breaks, its status, and a timestamped log (§8). |

Keep all of these outside the supervised repos (e.g. `~/repos/orc_directives/`).
They are working state, not source.

## 2. The supervision tick (every 15 minutes)

The tick is a durable recurring prompt in the manager's harness scheduler. Template:
[examples/multi-orc-supervision-tick.md](https://github.com/agticorp/codex-whip/blob/main/examples/multi-orc-supervision-tick.md).
For each orc:

1. **Capture** the pane tail:
   `tmux capture-pane -t <orc> -p | grep -v '^\s*$' | tail -8`.
2. **Check the model line in the footer** (e.g. `gpt-6-astra xhigh`). If it changed,
   fix it with the procedure in §3. Do this every tick: sub-agents and capacity
   dialogs silently downgrade sessions.
3. **Dialogs.** If a capacity dialog is open, pick **"Dismiss and keep waiting"**
   (§3). Never accept "Retry with a faster model".
4. **Idle at the prompt.** Read its last output and the newest status-log headings,
   then push the next item. Never leave an orc idle while non-blocked work exists.
5. **New HOLD files.** Review them with the checklist in §5.
6. **Anything the orc calls DONE** must be verified independently (§4) before you
   report it.
7. **Report** to the human only on: a DONE you verified, a RED, a HOLD that truly
   needs the human, or a completed phase. Otherwise send one short line.

## 3. Codex TUI mechanics (learned the hard way)

**Fixing a downgraded model:**

```bash
tmux send-keys -t <orc> Escape; sleep 4          # interrupt the turn
tmux send-keys -t <orc> "/model"; sleep 2; tmux send-keys -t <orc> Enter
# model list opens with the cursor on option 1 (the frontier model) → Enter
tmux send-keys -t <orc> Enter; sleep 3
# effort list opens on "Medium (default)" → Down, Down = "Extra high" → Enter
tmux send-keys -t <orc> Down; tmux send-keys -t <orc> Down; tmux send-keys -t <orc> Enter
# confirm the footer reads e.g. "gpt-6-astra xhigh", then re-send the orc's task
```

After fixing it, tell the orc it was downgraded and that it must re-check any work
it did on the weaker model.

**The capacity dialog.** "Our systems are thinking a bit more… 1. Retry with a
faster model / 2. Dismiss and keep waiting". The cursor starts on **option 1, which
is the downgrade**. Send `Down`, check that `› 2.` is selected, then `Enter`. Never
press Enter blind on an unknown dialog.

**Queued versus preempting:**
- Text sent while an orc is `Working` is **queued**. It shows under "Queued follow-up
  inputs" and runs when the turn ends.
- To **preempt**: send `Escape`. Codex interrupts and puts the queued text back in
  the composer. Then send `Enter`.
- Long directives often need a **second Enter**. Re-capture after ~5 s to confirm the
  orc shows `Working (`.

**Cyber-filter false positives.** "This content can't be shown… Trusted Access":
nudge the orc that it is a false positive on its own legitimate work, tell it to
continue, and suggest it narrow or rephrase the step that tripped it.

## 4. Never accept an orc's "done": verify it yourself

| Claim | How the Nazgûl verifies |
|---|---|
| A transaction succeeded | Read the receipt from **two independent providers**, and check status, block, logs and the balance delta. A committed rejection is not success. |
| A deploy is live | `curl` the public URL with trusted TLS (no `-k`). Byte-match the served bundle against the canonical build. Hit the readiness endpoints. |
| A UI works | A **real browser** (Playwright) on the deployed URL, run on the path a real user takes. That includes the returning-user path (an existing wallet, then unlock) with a **cold cache, 4× CPU and Slow-3G**. A fresh-profile load only tests onboarding. |
| A config changed | Read the live config API, not the orc's report. |
| No funds moved | Open the journals read-only (`sqlite3 "file:…?mode=ro"`), check balances on the chain, and check positions at the venue. |
| An auth boundary holds | A matrix of anonymous, wrong-credential, wrong-origin and correct requests, expecting 403 / 403 / 403 / 200. |

Run the verification **before** telling the human it's fixed. Say what you checked
and what you didn't.

## 5. Reviewing a HOLD

1. Recompute the hashes of the runner, pins and bundle files, and check they match
   the HOLD text.
2. Diff against the previous approved bundle: unchanged files must be
   **byte-identical** (`cmp`).
3. Read the code diff that justifies the change. Confirm it touches only what the
   HOLD claims.
4. Check scope: exact amounts and counts, one attempt, explicit abort triggers, exact
   rollback, and no fleet or consensus restart unless that is the point.
   - For validator changes: the rolling plan must keep quorum live, and rollback must
     be per host.
5. Approve by writing the decisions-log entry **with any extra conditions**, filling
   in `approval.json`, and telling the orc which decision approved it.
6. Pre-authorise **classes** of low-risk action so the orc doesn't HOLD on every
   step: local-only restarts, guarded switches with automatic rollback, read-only
   probes. A HOLD per trivial step adds hours.

**Retry policy that works.** A failure **before any signature or dispatch** may be
retried within the same approval (cap it at 3) with fresh inputs and a recorded root
cause. **After** anything is signed or dispatched, rules are strict: STOP, reconcile
read-only, and never sign a replacement.

## 6. Running live-money steps: the Nazgûl as operator

Orcs prepare; the Nazgûl executes. The orc writes a runbook with exact commands and
the **gate** each one must show (e.g. `check=PASS`, `next_step=…`). Then:

- Run **one command at a time**, and read its gate before the next.
- A step that returned `STOP` is **never re-run**. Inspect it read-only. Use `rearm`
  only with a **no-dispatch proof**: no action row, nonces and balances unchanged.
- After a dispatch, read the chain yourself. "The tx succeeded on-chain but the tool
  halted" is common, and the fix is receipt-only reconciliation, never a resend.
- **Market refusals are not safety halts.** Gas over the cap, price-gap or depth
  failures and closed sessions before dispatch should return `market_blocked` and
  wait for a better window. Don't lock the system.
- When the human makes a money call (for example "top up and lift the gas cap"),
  write it as a numbered decision, have the orc implement it as a reviewed policy
  change with old and new hashes, then run it.

## 7. Operations hygiene (each of these cost real hours)

- **Disk.** A full root disk killed nine 48-hour evidence runs. Put every bulky
  output (build targets, proofs, test temp dirs, logs over 50 MB) on a data volume.
  Add disk guards that pause and alarm below a threshold. Clean up by **relocating
  with a symlink after verifying the copy** (cp, diff, rm, ln), skipping anything
  open, referenced or recently written.
- **Free public RPCs are not infrastructure.** Providers failed one after another:
  token walls, 429s, load-balanced backends missing historical state, narrow
  `getLogs` ranges. Qualify providers on the **real workload repeated 5× back-to-back
  with zero stops**; a one-call-per-method matrix proves nothing. Keep two-provider
  agreement. Put live money on a paid provider.
- **Your own monitors can take down the system.** Status pollers that each opened a
  new TCP connection exhausted validator RPC connection budgets within hours. Use
  keep-alive or shared readers, cache identical reads per tick, and measure
  connections per minute per source.
- **Read-only samplers must never die on one bad read.** Log `READ_FAILED`, retry
  next tick, and set `Restart=on-failure`. Only reads that gate money should STOP.
- **Locks.** A read-only follower holding the operator lock blinded the entry
  watcher and blocked the operator. Readers take short read transactions and yield to
  the operator.
- **Time-boxed authorisations expire.** A one-session GPU approval silently took a
  public relay offline when it lapsed. Use standing, budgeted, revocable
  authorisations for always-on services.
- **Warm GPUs for latency-critical proofs.** Proving takes about 3 minutes warm; cold
  start and leasing were most of a "15–30 min" estimate.

## 8. Talking to the human

- **Give them a live tracker, not an opaque estimate.** For each step: what happens,
  what it waits on, its time if nothing breaks, and its status. State plainly how
  much of any estimate is padding for failures.
- **Don't make the human wait on calls you can make.** Take the call, log it as a
  decision, and move on. Escalate only money above the agreed envelope, structural
  or irreversible changes, and anything public.
- **Never report green on a proxy.** "The endpoint returns 200" is not "the wallet
  works". Test the user's actual path first (§4).
- **When the human is right, say so and fix it.** Correct the record in the shared
  artefact, not just in chat.

## 9. Anti-patterns from the run

| Anti-pattern | Cost | Rule now |
|---|---|---|
| Patching one provider failure at a time | About 10 stop-and-fix cycles on one funding step | Qualify on the real workload; pay for live-money RPC |
| A fixed $4 gas cap on a $400 trade during a gas spike | Half a day of waiting | Put money caps to the human early, with a recommendation |
| Fresh-profile UI checks only | The founder hit the bug first | Test the returning-user path, throttled and with a cold cache |
| Running each step only after the previous one finished | 20 hours on a 2-hour step | Pre-stage downstream steps; send idle orcs to parallel work |
| One-shot private attempts that consumed approval on read errors | 6 attempts burned | Pre-signature failures are retryable within an approval |
| Accepting "Retry with a faster model" | Orcs silently downgraded | Pick option 2; check the footer every tick |
| `pkill -f <pattern>` matching your own background job | A killed monitor | Kill by PID only |
