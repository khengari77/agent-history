"""Search: all sources, dedupe of imported sessions, project scoping, Unicode, no-hit message."""
import json
import unittest

from support import Fixture


class SearchTest(Fixture):
    def test_finds_hits_in_every_source(self):
        code, out = self.out("search", "self-destroy", "--dir", str(self.p.proj), "--limit", "20")
        self.assertEqual(code, 0)
        for source in ("claude", "opencode", "mimo", "codex"):
            self.assertIn(source, out)
        self.assertIn("Codex history hit", out)

    def test_duplicate_imported_text_is_shown_once(self):
        out = self.out("search", "we discussed the self-destroy flag", "--dir", str(self.p.proj))[1]
        self.assertEqual(out.count("we discussed the self-destroy flag"), 1)

    def test_project_scoping_excludes_siblings(self):
        out = self.out("search", "self-destroy", "--dir", str(self.p.proj), "--limit", "20")[1]
        self.assertNotIn("sibling self-destroy note", out)
        out = self.out("search", "self-destroy", "--all", "--limit", "20")[1]
        self.assertIn("sibling self-destroy note", out)

    def test_subdirectory_includes_repository_hits(self):
        out = self.out("search", "self-destroy", "--dir", str(self.p.sub), "--limit", "20")[1]
        self.assertIn("The flag self-destroys", out)

    def test_days_filter(self):
        out = self.out("search", "self-destroy", "--dir", str(self.p.proj), "--days", "1")[1]
        self.assertIn("no hits", out)

    def test_arabic_query(self):
        out = self.out("search", "مناهج", "--dir", str(self.p.proj), "--limit", "20")[1]
        self.assertIn("مناهج المفسرين", out)

    def test_single_source_filter(self):
        out = self.out("search", "self-destroy", "--dir", str(self.p.proj), "--source", "claude")[1]
        self.assertIn("claude", out)
        self.assertNotIn("mimo", out)

    def test_no_hits_message(self):
        out = self.out("search", "definitely-not-present-xyz", "--dir", str(self.p.proj))[1]
        self.assertIn("no hits", out)

    def test_json_output(self):
        code, out = self.out("search", "self-destroy", "--dir", str(self.p.proj), "--json")
        data = json.loads(out)
        self.assertTrue(data)
        self.assertTrue({"source", "session_id", "when", "role", "text"} <= set(data[0]))


if __name__ == "__main__":
    unittest.main()
