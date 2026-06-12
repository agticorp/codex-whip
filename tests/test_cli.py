import argparse
import unittest

from codex_whip.cli import (
    AGTI_QUANT_RESEARCH_MANDATE_FILE,
    Pane,
    PROMPT_VARIANTS,
    Settings,
    apply_overrides,
    build_cron_command,
    default_start_command,
    decide,
    input_settle_delay,
    is_codex_like,
    cron_block,
    remove_cron_block,
    sanitize_profile,
    settings_from_config,
    tail_text,
)


class ConfigTests(unittest.TestCase):
    def test_profile_config_loads_and_coerces_values(self):
        settings = settings_from_config(
            {
                "defaults": {"stable_seconds": 300, "start_codex": False},
                "profiles": {
                    "l1": {
                        "target": "l1-codex:0.0",
                        "repo": "/tmp/repo",
                        "start_codex": "true",
                        "cooldown_seconds": "120",
                    }
                },
            },
            "l1",
        )
        self.assertEqual(settings.profile, "l1")
        self.assertEqual(settings.target, "l1-codex:0.0")
        self.assertEqual(settings.repo, "/tmp/repo")
        self.assertTrue(settings.start_codex)
        self.assertEqual(settings.stable_seconds, 300.0)
        self.assertEqual(settings.cooldown_seconds, 120.0)

    def test_cli_overrides_config(self):
        settings = Settings(profile="x", target="old")
        args = argparse.Namespace(
            profile=None,
            target="new",
            repo=None,
            message=None,
            message_file=None,
            interval=None,
            stable_seconds=None,
            restart_stable_seconds=None,
            cooldown_seconds=None,
            capture_lines=None,
            tmux=None,
            socket_name=None,
            socket_path=None,
            codex_command_regex=None,
            state_file=None,
            log_file=None,
            start_command=None,
            new_session=None,
            submit_key=None,
            queue_key=None,
            paste_submit_delay=None,
            start_codex_flag=True,
            auto_approve_flag=False,
        )
        updated = apply_overrides(settings, args)
        self.assertEqual(updated.target, "new")
        self.assertTrue(updated.start_codex)

    def test_cron_block_removal_is_idempotent(self):
        block = cron_block("l1", "echo hi", "* * * * *")
        crontab = "MAILTO=\n" + block + "0 0 * * * echo keep\n"
        stripped = remove_cron_block(crontab, "l1")
        self.assertIn("MAILTO=", stripped)
        self.assertIn("echo keep", stripped)
        self.assertNotIn("codex-whip profile l1", stripped)
        self.assertEqual(remove_cron_block(stripped, "l1"), stripped)

    def test_profile_sanitization(self):
        self.assertEqual(sanitize_profile("L1 codex!"), "L1-codex")
        self.assertEqual(sanitize_profile(""), "default")

    def test_default_prompt_is_agti_research_mandate(self):
        self.assertEqual(len(PROMPT_VARIANTS), 1)
        self.assertIn("AGTI quantitative research mandate", PROMPT_VARIANTS[0])
        self.assertIn(str(AGTI_QUANT_RESEARCH_MANDATE_FILE), PROMPT_VARIANTS[0])
        self.assertTrue(PROMPT_VARIANTS[0].endswith("please proceed and follow this mandate"))

    def test_mandate_file_contains_requested_mandate(self):
        text = AGTI_QUANT_RESEARCH_MANDATE_FILE.read_text(encoding="utf-8")
        self.assertIn("Senior Quantitative Portfolio Researcher at AGTI", text)
        self.assertIn("Drift, Autocorrelation, and Lead Lag", text)
        self.assertTrue(text.strip().endswith("please proceed and follow this mandate"))

    def test_cron_command_preserves_submit_key_and_paste_delay(self):
        args = argparse.Namespace(
            config=None,
            profile="x",
            target="x:0.0",
            repo="/tmp/repo",
            message=None,
            message_file=None,
            stable_seconds=60,
            restart_stable_seconds=20,
            cooldown_seconds=120,
            capture_lines=None,
            tmux=None,
            socket_name=None,
            socket_path=None,
            codex_command_regex=None,
            state_file=None,
            log_file=None,
            start_command=None,
            new_session=None,
            submit_key="Enter",
            queue_key="Tab",
            paste_submit_delay=1.0,
            start_codex_flag=True,
            auto_approve_flag=False,
            frequency="* * * * *",
        )
        _profile, block = build_cron_command(args)
        self.assertIn("--submit-key Enter", block)
        self.assertIn("--queue-key Tab", block)
        self.assertIn("--paste-submit-delay 1.0", block)

    def test_default_start_command_uses_yolo(self):
        command = default_start_command(Settings(repo="/tmp/repo"), "hello")
        self.assertIn("--yolo", command)
        self.assertIn("--no-alt-screen", command)
        self.assertNotIn("--ask-for-approval", command)

    def test_tail_text_ignores_trailing_tmux_padding(self):
        self.assertEqual(tail_text("OpenAI Codex\n\n\n", 1), "OpenAI Codex")

    def test_input_settle_delay_scales_for_long_prompts(self):
        settings = Settings(paste_submit_delay=0.2)
        self.assertEqual(input_settle_delay(settings, "short"), 0.2)
        self.assertGreater(input_settle_delay(settings, "x" * 1000), 5.0)
        self.assertEqual(input_settle_delay(settings, "x" * 10000), 12.0)

    def test_shell_wrapped_codex_screen_is_nudgeable(self):
        pane = Pane(
            pane_id="%1",
            address="backtester:1.0",
            command="bash",
            active="1",
            path="/tmp/repo",
            title="agtinodeserver",
        )
        text = (
            "╭────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.130.0)\n"
            "│ permissions: YOLO mode\n"
            "╰────────────────────╯\n\n"
            "◦ Working (12s • esc to interrupt)\n\n"
            "› Use /skills to list available skills\n"
            + "\n" * 80
        )
        self.assertTrue(is_codex_like(Settings(), pane, text))
        decision = decide(Settings(), pane, text, {}, stable_for=0.0, now=0.0, force=True)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "queue")

    def test_busy_queue_only_once_until_not_busy(self):
        pane = Pane(
            pane_id="%1",
            address="backtester:1.0",
            command="node",
            active="1",
            path="/tmp/repo",
            title="goodalexander",
        )
        busy_text = "OpenAI Codex\n◦ Working (12s • esc to interrupt)\n"
        current = {"busy_queue_sent": True}
        self.assertIsNone(decide(Settings(), pane, busy_text, current, 0.0, 0.0))

        idle_text = "OpenAI Codex\n› Use /skills to list available skills\n"
        self.assertIsNone(decide(Settings(), pane, idle_text, current, 0.0, 1.0))
        self.assertNotIn("busy_queue_sent", current)


if __name__ == "__main__":
    unittest.main()
