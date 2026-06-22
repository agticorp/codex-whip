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

    def test_pfterminal_screen_is_nudgeable(self):
        pane = Pane(
            pane_id="%9",
            address="pfterminalworker:0.0",
            command="pfterminal",
            active="1",
            path="/home/postfiat/repos",
            title="repos",
        )
        text = (
            "╭────────────────────╮\n"
            "│ >_ PFTerminal (v0.0.0)\n"
            "╰────────────────────╯\n\n"
            "› Implement {feature}\n"
            "  zai-org/GLM-5.2-FP8 standard · ~/repos · Post Fiat Terminal\n"
        )
        self.assertTrue(is_codex_like(Settings(), pane, text))
        decision = decide(Settings(), pane, text, {}, stable_for=0.0, now=0.0, force=True)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "nudge")

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


class SendTextTests(unittest.TestCase):
    def _pane(self):
        return Pane(
            pane_id="%1",
            address="x:0.0",
            command="claude",
            active="1",
            path="/tmp/repo",
            title="",
        )

    def test_send_text_retries_submit_until_busy_then_stops(self):
        from unittest import mock

        from codex_whip import cli

        settings = Settings(
            max_submit_attempts=4,
            submit_verify_delay=0.0,
            paste_submit_delay=0.0,
        )
        busy = iter([False, False, True, True])
        with mock.patch.object(cli, "run_tmux_input") as mock_input, mock.patch.object(
            cli, "run_tmux"
        ) as mock_run, mock.patch.object(cli, "capture_pane", return_value=""), mock.patch.object(
            cli, "has_busy_indicator", side_effect=lambda _: next(busy)
        ), mock.patch.object(cli, "log") as mock_log, mock.patch.object(cli, "time"):
            cli.send_text(settings, self._pane(), "hello")

        mock_input.assert_called_once()
        self.assertEqual(mock_input.call_args.args[1][0], "load-buffer")
        self.assertEqual(mock_input.call_args.args[2], "hello")
        self.assertTrue(
            any(
                call.args[1][0] == "paste-buffer" and "-p" in call.args[1]
                for call in mock_run.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args[1][0] == "paste-buffer" and "-r" in call.args[1]
                for call in mock_run.call_args_list
            ),
            "paste-buffer must pass -r so multiline prompts keep their LF characters",
        )
        self.assertTrue(
            any(call.args[1][0] == "delete-buffer" for call in mock_run.call_args_list)
        )
        submits = [
            call
            for call in mock_run.call_args_list
            if call.args[1][:2] == ["send-keys", "-t"]
            and call.args[1][-1] == settings.submit_key
        ]
        self.assertEqual(len(submits), 3)
        mock_log.assert_not_called()

    def test_send_text_logs_when_submit_never_verifies(self):
        from unittest import mock

        from codex_whip import cli

        settings = Settings(
            max_submit_attempts=3,
            submit_verify_delay=0.0,
            paste_submit_delay=0.0,
        )
        with mock.patch.object(cli, "run_tmux_input"), mock.patch.object(
            cli, "run_tmux"
        ), mock.patch.object(cli, "capture_pane", return_value=""), mock.patch.object(
            cli, "has_busy_indicator", return_value=False
        ), mock.patch.object(cli, "log") as mock_log, mock.patch.object(cli, "time"):
            cli.send_text(settings, self._pane(), "hello")

        mock_log.assert_called_once()
        self.assertIn("did not verify", mock_log.call_args[0][1])


class PasteTextTests(unittest.TestCase):
    def _pane(self):
        return Pane(
            pane_id="%1",
            address="x:0.0",
            command="claude",
            active="1",
            path="/tmp/repo",
            title="",
        )

    def test_paste_buffer_uses_r_flag_to_preserve_lf(self):
        from unittest import mock

        from codex_whip import cli

        settings = Settings()
        with mock.patch.object(cli, "run_tmux_input") as mock_input, mock.patch.object(
            cli, "run_tmux"
        ) as mock_run:
            cli.paste_text(settings, self._pane(), "line1\nline2")

        # load-buffer <name> - receives the multiline text unchanged as stdin.
        mock_input.assert_called_once()
        args = mock_input.call_args.args[1]
        self.assertEqual(args[0], "load-buffer")
        self.assertEqual(args[1], "-b")
        self.assertTrue(args[2].startswith("codex-whip-"))
        self.assertEqual(args[3], "-")
        self.assertEqual(mock_input.call_args.args[2], "line1\nline2")

        # paste-buffer is invoked with both -p (bracketed paste) and -r (raw,
        # LF-preserving) and targets the pane.
        paste_calls = [
            call for call in mock_run.call_args_list if call.args[1][0] == "paste-buffer"
        ]
        self.assertEqual(len(paste_calls), 1)
        args = paste_calls[0].args[1]
        self.assertIn("-p", args)
        self.assertIn("-r", args)
        self.assertIn("-t", args)
        # delete-buffer still runs unconditionally.
        self.assertTrue(
            any(call.args[1][0] == "delete-buffer" for call in mock_run.call_args_list)
        )

    def test_multiline_text_loaded_unchanged_and_buffer_deleted(self):
        from unittest import mock

        from codex_whip import cli

        settings = Settings()
        multiline = (
            "First line of the mandate.\n"
            "Second line, with punctuation: !@#$%^&*()\n"
            "\n"
            "Third line after a blank line.\n"
        )
        with mock.patch.object(cli, "run_tmux_input") as mock_input, mock.patch.object(
            cli, "run_tmux"
        ) as mock_run:
            cli.paste_text(settings, self._pane(), multiline)

        # No CR characters leaked into the loaded buffer content.
        loaded = mock_input.call_args.args[2]
        self.assertEqual(loaded, multiline)
        self.assertNotIn("\r", loaded)

        # delete-buffer is called exactly once regardless of paste success.
        delete_calls = [
            call for call in mock_run.call_args_list if call.args[1][0] == "delete-buffer"
        ]
        self.assertEqual(len(delete_calls), 1)


if __name__ == "__main__":
    unittest.main()
