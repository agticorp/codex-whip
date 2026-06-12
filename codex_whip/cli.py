"""Command line interface for codex-whip."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from codex_whip import __version__


STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
DEFAULT_CONFIG_FILE = CONFIG_HOME / "codex-whip" / "config.toml"
DEFAULT_PROFILE = "default"
AGTI_QUANT_RESEARCH_MANDATE_FILE = (
    Path(__file__).resolve().parents[1] / "AGTI_QUANT_RESEARCH_MANDATE.md"
)

AGTI_QUANT_RESEARCH_MANDATE = (
    "Read and follow the AGTI quantitative research mandate in "
    f"{AGTI_QUANT_RESEARCH_MANDATE_FILE}. please proceed and follow this mandate"
)

PROMPT_VARIANTS = [AGTI_QUANT_RESEARCH_MANDATE]

WAITING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bwaiting for (user )?input\b",
        r"\bready for input\b",
        r"\bpress enter\b",
        r"\btype .{0,40}continue\b",
        r"\bturn aborted\b",
        r"\binterrupted\b",
        r"\bconversation interrupted\b",
        r"\bfinal answer\b",
        r"\btask complete\b",
        r"\bapproval required\b",
        r"\bapprove (command|execution|tool|operation)\b",
        r"\ballow (command|execution|tool|operation)\b",
        r"\bUse /skills to list available skills\b",
        r"(?m)^\s*(codex>|you:|>)\s*$",
        r"(?m)^\s*\u203a\s*$",
        r"(?m)^\s*>\s*$",
    ]
]

BUSY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bWorking \(",
        r"\besc to interrupt\b",
        # Cursor agent shows "Running 12.08k tokens" / "Reading 6.63k tokens"
        r"\bRunning\s+[\d.]+[kKmM]?\s*tokens\b",
        r"\bReading\s+[\d.]+[kKmM]?\s*tokens\b",
    ]
]

APPROVAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bapproval required\b",
        r"\bapprove (command|execution|tool|operation)\b",
        r"\ballow (command|execution|tool|operation)\b",
        r"\brun this command\?\b",
        r"\bdo you want to .*?\?",
    ]
]

SHELL_COMMANDS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}


@dataclass(frozen=True)
class Settings:
    profile: str = DEFAULT_PROFILE
    target: str | None = None
    repo: str = str(Path.cwd())
    message: str | None = None
    message_file: str | None = None
    interval: float = 30.0
    stable_seconds: float = 300.0
    restart_stable_seconds: float = 20.0
    cooldown_seconds: float = 900.0
    capture_lines: int = 240
    tmux: str = "tmux"
    socket_name: str | None = None
    socket_path: str | None = None
    codex_command_regex: str = r"(^|/)codex(?:-cli)?$"
    state_file: str | None = None
    log_file: str | None = None
    start_codex: bool = False
    start_command: str | None = None
    new_session: str | None = None
    auto_approve: bool = False
    submit_key: str = "Enter"
    queue_key: str = "Tab"
    paste_submit_delay: float = 0.2

    def resolved_state_file(self) -> Path:
        if self.state_file:
            return Path(self.state_file).expanduser()
        return STATE_HOME / "codex-whip" / f"{self.profile}.state.json"

    def resolved_log_file(self) -> Path:
        if self.log_file:
            return Path(self.log_file).expanduser()
        return STATE_HOME / "codex-whip" / f"{self.profile}.log"


@dataclass
class Pane:
    pane_id: str
    address: str
    command: str
    active: str
    path: str
    title: str


@dataclass
class Decision:
    action: str
    reason: str


def str_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def sanitize_profile(profile: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", profile).strip("-") or DEFAULT_PROFILE


def load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        return {}
    return data


def settings_from_config(config: dict[str, Any], profile: str) -> Settings:
    profile = sanitize_profile(profile)
    base = config.get("defaults", {})
    profiles = config.get("profiles", {})
    raw = {}
    if isinstance(base, dict):
        raw.update(base)
    if isinstance(profiles, dict) and isinstance(profiles.get(profile), dict):
        raw.update(profiles[profile])
    raw["profile"] = profile

    allowed = set(Settings.__dataclass_fields__)
    coerced: dict[str, Any] = {}
    for key, value in raw.items():
        normalized = key.replace("-", "_")
        if normalized not in allowed:
            continue
        coerced[normalized] = value

    for key in ["start_codex", "auto_approve"]:
        if key in coerced:
            coerced[key] = str_to_bool(coerced[key])
    for key in [
        "interval",
        "stable_seconds",
        "restart_stable_seconds",
        "cooldown_seconds",
        "paste_submit_delay",
    ]:
        if key in coerced:
            coerced[key] = float(coerced[key])
    if "capture_lines" in coerced:
        coerced["capture_lines"] = int(coerced["capture_lines"])

    return Settings(**coerced)


def apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    updates: dict[str, Any] = {}
    for field in Settings.__dataclass_fields__:
        if not hasattr(args, field):
            continue
        value = getattr(args, field)
        if value is not None:
            updates[field] = value
    if getattr(args, "start_codex_flag", False):
        updates["start_codex"] = True
    if getattr(args, "auto_approve_flag", False):
        updates["auto_approve"] = True
    if updates.get("new_session"):
        updates["start_codex"] = True
    return replace(settings, **updates)


def load_settings(args: argparse.Namespace) -> Settings:
    config_file = Path(args.config).expanduser() if args.config else DEFAULT_CONFIG_FILE
    profile = sanitize_profile(args.profile or DEFAULT_PROFILE)
    settings = settings_from_config(load_config_file(config_file), profile)
    return apply_overrides(settings, args)


def tmux_base(settings: Settings) -> list[str]:
    cmd = [settings.tmux]
    if settings.socket_path:
        cmd.extend(["-S", settings.socket_path])
    if settings.socket_name:
        cmd.extend(["-L", settings.socket_name])
    return cmd


def run_tmux(settings: Settings, tmux_args: list[str], check: bool = True) -> str:
    proc = subprocess.run(
        tmux_base(settings) + tmux_args,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "tmux command failed"
        raise RuntimeError(f"{' '.join(tmux_base(settings) + tmux_args)}: {message}")
    return proc.stdout


def log(settings: Settings, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{stamp} {message}"
    print(line, flush=True)
    path = settings.resolved_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def pane_from_line(line: str) -> Pane | None:
    parts = line.rstrip("\n").split("\t", 5)
    if len(parts) != 6:
        return None
    return Pane(*parts)


def list_panes(settings: Settings) -> list[Pane]:
    fmt = (
        "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t"
        "#{pane_current_command}\t#{pane_active}\t#{pane_current_path}\t#{pane_title}"
    )
    output = run_tmux(settings, ["list-panes", "-a", "-F", fmt], check=False)
    return [pane for pane in (pane_from_line(line) for line in output.splitlines()) if pane]


def display_pane(settings: Settings, target: str) -> Pane:
    fmt = (
        "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t"
        "#{pane_current_command}\t#{pane_active}\t#{pane_current_path}\t#{pane_title}"
    )
    output = run_tmux(settings, ["display-message", "-p", "-t", target, fmt])
    pane = pane_from_line(output)
    if not pane:
        raise RuntimeError(f"could not resolve tmux target {target!r}")
    return pane


def print_panes(panes: list[Pane]) -> None:
    if not panes:
        print("No tmux panes are visible from this tmux socket.")
        return
    for pane in panes:
        print(
            f"{pane.pane_id}\t{pane.address}\tcmd={pane.command or '-'}\t"
            f"active={pane.active}\tpath={pane.path}\ttitle={pane.title}"
        )


def socket_scan_dir() -> Path:
    base = Path(os.environ.get("TMUX_TMPDIR", "/tmp"))
    return base / f"tmux-{os.getuid()}"


def discover_socket_paths() -> list[Path]:
    base = socket_scan_dir()
    if not base.exists():
        return []
    sockets = []
    for path in sorted(base.iterdir()):
        try:
            if stat.S_ISSOCK(path.stat().st_mode):
                sockets.append(path)
        except OSError:
            continue
    return sockets


def settings_for_socket_path(settings: Settings, socket_path: Path) -> Settings:
    return replace(settings, socket_name=None, socket_path=str(socket_path))


def print_discovered_sockets(settings: Settings) -> None:
    sockets = discover_socket_paths()
    if not sockets:
        print(f"No tmux sockets found under {socket_scan_dir()}.")
        return
    for socket_path in sockets:
        print(f"socket={socket_path}")
        print_panes(list_panes(settings_for_socket_path(settings, socket_path)))


def create_session(settings: Settings) -> Pane:
    if not settings.new_session:
        raise RuntimeError("no target pane found; pass --target or --new-session")
    run_tmux(settings, ["new-session", "-d", "-s", settings.new_session, "-c", settings.repo])
    log(settings, f"created tmux session {settings.new_session!r} in {settings.repo}")
    return display_pane(settings, f"{settings.new_session}:0.0")


def resolve_pane(settings: Settings) -> Pane:
    if settings.target:
        return display_pane(settings, settings.target)

    panes = list_panes(settings)
    codex_re = re.compile(settings.codex_command_regex, re.IGNORECASE)
    candidates = [
        pane
        for pane in panes
        if codex_re.search(pane.command)
        or "codex" in pane.address.lower()
        or "codex" in pane.title.lower()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return create_session(settings)

    print("Multiple Codex-like tmux panes found. Re-run with --target:")
    print_panes(candidates)
    raise SystemExit(2)


def capture_pane(settings: Settings, target: str) -> str:
    return run_tmux(
        settings,
        ["capture-pane", "-p", "-J", "-S", f"-{settings.capture_lines}", "-t", target],
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def tail_text(text: str, lines: int = 80) -> str:
    return "\n".join(text.rstrip().splitlines()[-lines:])


def is_codex_like(settings: Settings, pane: Pane, text: str) -> bool:
    codex_re = re.compile(settings.codex_command_regex, re.IGNORECASE)
    return (
        bool(codex_re.search(pane.command))
        or "codex" in pane.address.lower()
        or "codex" in pane.title.lower()
        or "codex" in tail_text(text, 40).lower()
    )


def is_shell(command: str) -> bool:
    return command in SHELL_COMMANDS


def has_waiting_prompt(text: str) -> bool:
    tail = tail_text(text)
    return any(pattern.search(tail) for pattern in WAITING_PATTERNS)


def has_approval_prompt(text: str) -> bool:
    tail = tail_text(text)
    return any(pattern.search(tail) for pattern in APPROVAL_PATTERNS)


def has_busy_indicator(text: str) -> bool:
    tail = tail_text(text)
    return any(pattern.search(tail) for pattern in BUSY_PATTERNS)


def has_queued_followup(text: str) -> bool:
    return "queued follow-up inputs" in tail_text(text).lower()


def pane_state(
    state: dict[str, Any], pane: Pane, text: str, now: float
) -> tuple[dict[str, Any], float]:
    panes = state.setdefault("panes", {})
    current = panes.setdefault(pane.pane_id, {})
    digest = text_digest(text)
    if current.get("last_digest") != digest:
        current["last_digest"] = digest
        current["stable_since"] = now
    stable_since = float(current.get("stable_since", now))
    return current, now - stable_since


def choose_message(settings: Settings, current: dict[str, Any]) -> str:
    if settings.message_file:
        return Path(settings.message_file).expanduser().read_text(encoding="utf-8").strip()
    if settings.message:
        return settings.message.strip()
    index = int(current.get("prompt_index", 0))
    current["prompt_index"] = index + 1
    return PROMPT_VARIANTS[index % len(PROMPT_VARIANTS)]


def decide(
    settings: Settings,
    pane: Pane,
    text: str,
    current: dict[str, Any],
    stable_for: float,
    now: float,
    force: bool = False,
) -> Decision | None:
    codex_like = is_codex_like(settings, pane, text)
    shell_like = is_shell(pane.command) and not codex_like
    if codex_like:
        current["saw_codex"] = True

    busy = codex_like and has_busy_indicator(text)
    if not busy:
        current.pop("busy_queue_sent", None)

    if not force:
        last_action = float(current.get("last_action_at", 0.0))
        if now - last_action < settings.cooldown_seconds:
            return None

    can_start = settings.start_codex or settings.start_command or current.get("saw_codex")
    if shell_like:
        if force and can_start:
            return Decision("start", "forced Codex start from shell")
        if not force and can_start and stable_for >= settings.restart_stable_seconds:
            return Decision(
                "start",
                f"previous Codex pane is at shell and stable for {stable_for:.0f}s",
            )
        return None

    if busy:
        if not has_queued_followup(text) and not current.get("busy_queue_sent"):
            return Decision("queue", "Codex pane is working; queuing follow-up input")
        return None

    if settings.auto_approve and codex_like and has_approval_prompt(text):
        return Decision("approve", "approval prompt detected")

    if force:
        if codex_like:
            return Decision("nudge", "forced Codex pane nudge")
        return None

    if codex_like and has_waiting_prompt(text):
        return Decision("nudge", "Codex-like pane appears to be waiting")

    if codex_like and stable_for >= settings.stable_seconds:
        return Decision(
            "nudge",
            f"Codex-like pane has been stable for {stable_for:.0f}s",
        )

    return None


def input_settle_delay(settings: Settings, text: str) -> float:
    return max(settings.paste_submit_delay, min(12.0, len(text) * 0.006))


def send_text(settings: Settings, pane: Pane, text: str, submit_key: str | None = None) -> None:
    # Codex's TUI can keep bracketed paste text in the composer after a
    # subsequent Enter. Literal key injection behaves like normal typing, but
    # long prompts need time to drain through the TUI before the final key.
    run_tmux(settings, ["send-keys", "-t", pane.pane_id, "-l", text])
    time.sleep(input_settle_delay(settings, text))
    run_tmux(settings, ["send-keys", "-t", pane.pane_id, submit_key or settings.submit_key])


def default_start_command(settings: Settings, prompt: str) -> str:
    return " ".join(
        [
            "codex",
            "--cd",
            shlex.quote(settings.repo),
            "--yolo",
            "--no-alt-screen",
            shlex.quote(prompt),
        ]
    )


def build_start_command(settings: Settings, prompt: str) -> str:
    if not settings.start_command:
        return default_start_command(settings, prompt)
    return settings.start_command.format(
        prompt=shlex.quote(prompt),
        prompt_raw=prompt,
        repo=shlex.quote(settings.repo),
    )


def execute_decision(
    settings: Settings,
    pane: Pane,
    decision: Decision,
    current: dict[str, Any],
    now: float,
    dry_run: bool = False,
) -> None:
    prompt = choose_message(settings, current)
    if decision.action == "approve":
        log(settings, f"{pane.address} {pane.pane_id}: sending approval key: {decision.reason}")
        if not dry_run:
            run_tmux(settings, ["send-keys", "-t", pane.pane_id, settings.submit_key])
    elif decision.action == "nudge":
        log(settings, f"{pane.address} {pane.pane_id}: nudging Codex: {decision.reason}")
        if not dry_run:
            send_text(settings, pane, prompt)
    elif decision.action == "queue":
        log(settings, f"{pane.address} {pane.pane_id}: queueing Codex input: {decision.reason}")
        if not dry_run:
            current["busy_queue_sent"] = True
            send_text(settings, pane, prompt, settings.queue_key)
    elif decision.action == "start":
        command = build_start_command(settings, prompt)
        log(settings, f"{pane.address} {pane.pane_id}: starting Codex: {decision.reason}")
        if dry_run:
            log(settings, f"dry-run start command: {command}")
        else:
            send_text(settings, pane, command)
    else:
        raise RuntimeError(f"unknown decision action: {decision.action}")
    if not dry_run:
        current["last_action_at"] = now


def tick(settings: Settings, state: dict[str, Any], dry_run: bool = False, force: bool = False) -> bool:
    pane = resolve_pane(settings)
    text = capture_pane(settings, pane.pane_id)
    now = time.time()
    current, stable_for = pane_state(state, pane, text, now)
    decision = decide(settings, pane, text, current, stable_for, now, force=force)
    if decision:
        execute_decision(settings, pane, decision, current, now, dry_run=dry_run)
        return True
    log(
        settings,
        (
            f"{pane.address} {pane.pane_id}: no action "
            f"(cmd={pane.command or '-'}, stable_for={stable_for:.0f}s)"
        ),
    )
    return False


def run_loop(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    state_path = settings.resolved_state_file()
    state = load_state(state_path)
    while True:
        tick(settings, state, dry_run=args.dry_run, force=args.force)
        if not args.dry_run:
            save_state(state_path, state)
        if args.once:
            return 0
        time.sleep(settings.interval)


def cron_block(profile: str, command: str, frequency: str) -> str:
    return (
        f"# BEGIN codex-whip profile {profile}\n"
        f"{frequency} {command}\n"
        f"# END codex-whip profile {profile}\n"
    )


def read_crontab() -> str:
    proc = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def write_crontab(content: str) -> None:
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def remove_cron_block(crontab: str, profile: str) -> str:
    start = f"# BEGIN codex-whip profile {profile}"
    end = f"# END codex-whip profile {profile}"
    lines = crontab.splitlines()
    output: list[str] = []
    skip = False
    for line in lines:
        if line.strip() == start:
            skip = True
            continue
        if line.strip() == end:
            skip = False
            continue
        if not skip:
            output.append(line)
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output) + ("\n" if output else "")


def build_cron_command(args: argparse.Namespace) -> tuple[str, str]:
    settings = load_settings(args)
    profile = sanitize_profile(settings.profile)
    frequency = args.frequency
    executable = shutil.which("codex-whip")
    if executable:
        base_command = shlex.quote(executable)
    else:
        base_command = f"{shlex.quote(sys.executable)} -m codex_whip.cli"

    command_parts = [
        base_command,
        "run",
        "--profile",
        shlex.quote(profile),
        "--once",
    ]
    if args.config:
        command_parts.extend(["--config", shlex.quote(str(Path(args.config).expanduser()))])
    for option, value in [
        ("--target", settings.target),
        ("--repo", settings.repo),
        ("--socket-name", settings.socket_name),
        ("--socket-path", settings.socket_path),
        ("--state-file", str(settings.resolved_state_file())),
        ("--log-file", str(settings.resolved_log_file())),
    ]:
        if value:
            command_parts.extend([option, shlex.quote(str(value))])
    if settings.start_codex:
        command_parts.append("--start-codex")
    command_parts.extend(
        [
            "--stable-seconds",
            str(settings.stable_seconds),
            "--restart-stable-seconds",
            str(settings.restart_stable_seconds),
            "--cooldown-seconds",
            str(settings.cooldown_seconds),
            "--submit-key",
            shlex.quote(settings.submit_key),
            "--queue-key",
            shlex.quote(settings.queue_key),
            "--paste-submit-delay",
            str(settings.paste_submit_delay),
        ]
    )
    command = " ".join(command_parts)

    lock = shlex.quote(str(STATE_HOME / "codex-whip" / f"{profile}.lock"))
    flock = shutil.which("flock")
    if flock:
        command = f"{shlex.quote(flock)} -n {lock} {command}"

    output = shlex.quote(str(settings.resolved_log_file().with_suffix(".cron.out")))
    command = f"{command} >> {output} 2>&1"
    return profile, cron_block(profile, command, frequency)


def install_cron(args: argparse.Namespace) -> int:
    profile, block = build_cron_command(args)
    crontab = remove_cron_block(read_crontab(), profile)
    write_crontab(crontab + block)
    print(block, end="")
    return 0


def uninstall_cron(args: argparse.Namespace) -> int:
    profile = sanitize_profile(args.profile or DEFAULT_PROFILE)
    write_crontab(remove_cron_block(read_crontab(), profile))
    print(f"removed codex-whip cron profile {profile}")
    return 0


def print_sample_config(_: argparse.Namespace) -> int:
    print(
        """[profiles.l1]
target = "l1-codex:0.0"
repo = "/home/postfiat/repos/postfiatl1v2"
start_codex = true
stable_seconds = 60
cooldown_seconds = 120
# Omit message to use the built-in AGTI quantitative research mandate.
"""
    )
    return 0


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help=f"config file, default {DEFAULT_CONFIG_FILE}")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="profile name")
    parser.add_argument("-t", "--target", help="tmux target pane, for example %%1 or l1:0.0")
    parser.add_argument("--repo", help="repo path for Codex start commands")
    parser.add_argument("--message", help="custom continuation message")
    parser.add_argument("--message-file", help="read continuation message from a file")
    parser.add_argument("--stable-seconds", type=float, help="nudge after stable output")
    parser.add_argument("--restart-stable-seconds", type=float, help="restart after shell is stable")
    parser.add_argument("--cooldown-seconds", type=float, help="minimum seconds between actions")
    parser.add_argument("--capture-lines", type=int, help="tail lines to inspect")
    parser.add_argument("--tmux", help="tmux binary")
    parser.add_argument("--socket-name", help="tmux socket name passed with -L")
    parser.add_argument("--socket-path", help="tmux socket path passed with -S")
    parser.add_argument("--codex-command-regex", help="regex for pane_current_command")
    parser.add_argument("--state-file", help="JSON state file")
    parser.add_argument("--log-file", help="append-only log file")
    parser.add_argument("--start-codex", dest="start_codex_flag", action="store_true")
    parser.add_argument("--start-command", help="custom shell command to start Codex")
    parser.add_argument("--new-session", help="create a detached tmux session if needed")
    parser.add_argument("--auto-approve", dest="auto_approve_flag", action="store_true")
    parser.add_argument("--submit-key", help="tmux key used to submit text")
    parser.add_argument("--queue-key", help="tmux key used to queue text while Codex is working")
    parser.add_argument("--paste-submit-delay", type=float, help="delay between paste and submit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Keep Codex CLI sessions moving in tmux.")
    parser.add_argument("--version", action="version", version=f"codex-whip {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run one tick or watch continuously")
    add_common_options(run_parser)
    run_parser.add_argument("--once", action="store_true", help="evaluate once and exit")
    run_parser.add_argument("--force", action="store_true", help="nudge/start even if checks do not match")
    run_parser.add_argument("--dry-run", action="store_true", help="log action without sending keys")
    run_parser.add_argument("--interval", type=float, help="watch interval in seconds")
    run_parser.set_defaults(func=run_loop)

    list_parser = subparsers.add_parser("list", help="list visible tmux panes")
    add_common_options(list_parser)
    list_parser.set_defaults(func=lambda args: (print_panes(list_panes(load_settings(args))) or 0))

    discover_parser = subparsers.add_parser("discover-sockets", help="list panes for tmux sockets under /tmp")
    add_common_options(discover_parser)
    discover_parser.set_defaults(func=lambda args: (print_discovered_sockets(load_settings(args)) or 0))

    install_parser = subparsers.add_parser("install-cron", help="install or replace a crontab tick")
    add_common_options(install_parser)
    install_parser.add_argument("--frequency", default="* * * * *", help="cron frequency")
    install_parser.set_defaults(func=install_cron)

    uninstall_parser = subparsers.add_parser("uninstall-cron", help="remove a crontab tick")
    uninstall_parser.add_argument("--profile", default=DEFAULT_PROFILE, help="profile name")
    uninstall_parser.set_defaults(func=uninstall_cron)

    sample_parser = subparsers.add_parser("sample-config", help="print a sample TOML config")
    sample_parser.set_defaults(func=print_sample_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"codex-whip: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
