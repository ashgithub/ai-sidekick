import importlib.util
import unittest
from pathlib import Path


ONBOARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "onboard.py"
SPEC = importlib.util.spec_from_file_location("gbu_jira_onboard", ONBOARD_PATH)
onboard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(onboard)


class NetrcTests(unittest.TestCase):
    def test_upsert_netrc_entry_adds_machine_without_losing_existing_entries(self):
        existing = "machine other.example.com\n  login old\n  password old-token\n"

        updated = onboard.upsert_netrc_entry(
            existing,
            "gbujira.oraclecorp.com",
            "ashish.ag.agarwal@oracle.com",
            "new-token",
        )

        self.assertIn("machine other.example.com", updated)
        self.assertIn("machine gbujira.oraclecorp.com", updated)
        self.assertIn("  login ashish.ag.agarwal@oracle.com", updated)
        self.assertIn("  password new-token", updated)

    def test_upsert_netrc_entry_replaces_existing_machine(self):
        existing = "\n".join(
            [
                "machine gbujira.oraclecorp.com",
                "  login old@example.com",
                "  password old-token",
                "machine other.example.com",
                "  login keep",
                "  password keep-token",
                "",
            ]
        )

        updated = onboard.upsert_netrc_entry(
            existing,
            "gbujira.oraclecorp.com",
            "ashish.ag.agarwal@oracle.com",
            "new-token",
        )

        self.assertNotIn("old-token", updated)
        self.assertIn("machine other.example.com", updated)
        self.assertIn("  password keep-token", updated)
        self.assertIn("  login ashish.ag.agarwal@oracle.com", updated)
        self.assertIn("  password new-token", updated)


class JiraConfigTests(unittest.TestCase):
    def test_parse_jira_cli_config_reads_login_and_server(self):
        config = "\n".join(
            [
                "auth_type: bearer",
                "login: ashish.ag.agarwal@oracle.com",
                "server: https://gbujira.oraclecorp.com",
            ]
        )

        self.assertEqual(
            onboard.parse_jira_cli_config(config),
            {
                "login": "ashish.ag.agarwal@oracle.com",
                "server": "https://gbujira.oraclecorp.com",
            },
        )


if __name__ == "__main__":
    unittest.main()
