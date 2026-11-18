"""Session listings: ordering, scoping from a subdirectory, automated threads, JSON output."""
import json
import unittest

from support import Fixture


class SessionsTest(Fixture):
    def test_newest_first_and_limited(self):
        code, out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "3")
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)
        self.assertIn("th-sub", lines[0])       # 6000
        self.assertIn("th-main", lines[1])      # 5000
        self.assertIn("ses_mimo_ar", lines[2])  # 4200

    def test_listings_include_all_four_sources(self):
        out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "20")[1]
        for source in ("claude", "opencode", "mimo", "codex"):
            self.assertIn(source, out)

    def test_sibling_repository_is_excluded_but_visible_from_itself(self):
        self.assertNotIn("ses_open_sib", self.out("sessions", "--dir", str(self.p.proj), "--limit", "20")[1])
        self.assertIn("ses_open_sib", self.out("sessions", "--dir", str(self.p.sibling))[1])

    def test_subdirectory_sees_its_own_tree_and_the_repo_root(self):
        out = self.out("sessions", "--dir", str(self.p.sub), "--limit", "20")[1]
        self.assertIn("th-sub", out)       # started in the subdirectory
        self.assertIn("th-main", out)      # started at the repository root
        self.assertIn("ses_open_proj", out)
        self.assertNotIn("ses_open_sib", out)

    def test_repo_flag_widens_to_the_whole_repository(self):
        narrow = self.out("sessions", "--dir", str(self.p.sub), "--limit", "20")[1]
        wide = self.out("sessions", "--dir", str(self.p.sub), "--limit", "20", "--repo")[1]
        self.assertNotIn("ses_open_other", wide)
        self.assertGreaterEqual(len(wide.splitlines()), len(narrow.splitlines()))

    def test_guardian_threads_hidden_unless_requested(self):
        out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "20")[1]
        self.assertNotIn("th-guardian", out)
        out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "20", "--include-automated")[1]
        self.assertIn("th-guardian", out)

    def test_subagent_sessions_are_tagged(self):
        out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "2")[1]
        self.assertIn("[subagent]", out)

    def test_json_output(self):
        code, out = self.out("sessions", "--dir", str(self.p.proj), "--limit", "2", "--json")
        data = json.loads(out)
        self.assertEqual(len(data), 2)
        self.assertIn("session_id", data[0])

    def test_empty_directory(self):
        empty = self.p.tmp / "empty"
        empty.mkdir()
        out = self.out("sessions", "--dir", str(empty))[1]
        self.assertIn("no sessions found", out)


if __name__ == "__main__":
    unittest.main()
