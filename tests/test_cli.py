import argparse
import unittest

from codex_whip.cli import (
    Settings,
    apply_overrides,
    cron_block,
    remove_cron_block,
    sanitize_profile,
    settings_from_config,
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


if __name__ == "__main__":
    unittest.main()
