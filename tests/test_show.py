"""show: conversation text only, grep narrowing, budgets, and honest ambiguity errors."""
import json
import unittest

import support
from support import Fixture


class ShowTest(Fixture):
    def test_claude_turns_exclude_tool_output(self):
        code, out = self.out("show", "claude", "sess-claude")
        self.assertEqual(code, 0)
        self.assertIn("we discussed the self-destroy flag", out)
        self.assertIn("The flag self-destroys the box", out)
        self.assertNotIn("TOOL OUTPUT MUST NOT APPEAR", out)

    def test_grep_narrows(self):
        out = self.out("show", "claude", "sess-claude", "--grep", "box at the end")[1]
        self.assertIn("The flag self-destroys", out)
        self.assertNotIn("we discussed", out)

    def test_budget_message(self):
        out = self.out("show", "claude", "sess-claude", "--max-chars", "20")[1]
        self.assertIn("max-chars reached", out)

    def test_codex_strips_wrappers_and_mirrors(self):
        out = self.out("show", "codex", "th-main")[1]
        self.assertIn("self-destroy the box please", out)
        self.assertNotIn("<environment_context>", out)
        self.assertNotIn("MIRRORED EVENT MUST NOT APPEAR", out)

    def test_opencode_session(self):
        out = self.out("show", "opencode", "ses_open_proj")[1]
        self.assertIn("we discussed the self-destroy flag", out)

    def test_ambiguous_prefix_is_reported(self):
        out = self.out("show", "codex", "th-")
        self.assertEqual(out[0], 2)
        self.assertIn("ambiguous session prefix", out[1])

    def test_unknown_session(self):
        code, out, err = self.run_cli("show", "codex", "nope")
        self.assertEqual(code, 2)
        self.assertIn("session not found", err)

    def test_missing_source(self):
        import shutil
        shutil.rmtree(self.p.home / ".codex")
        code, out, err = self.run_cli("show", "codex", "th-main")
        self.assertEqual(code, 2)
        self.assertIn("no data", err)


if __name__ == "__main__":
    unittest.main()
