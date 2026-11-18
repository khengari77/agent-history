"""Curated memories: discovered per source, labelled with the real project path, printed on demand."""
import unittest

from support import Fixture


class MemoriesTest(Fixture):
    def test_lists_every_source_with_real_scope(self):
        code, out = self.out("memories", "--dir", str(self.p.proj))
        self.assertEqual(code, 0)
        self.assertIn("[claude]", out)
        self.assertIn("feedback.md", out)
        self.assertIn(f"scope {self.p.proj}", out)      # the real path, not the slug
        self.assertIn("[mimo]", out)
        self.assertIn("[mimo-global]", out)
        self.assertIn("[codex-global]", out)
        self.assertIn("[project]", out)
        self.assertIn(str(self.p.proj / "AGENTS.md"), out)

    def test_print_shows_bodies_without_frontmatter(self):
        code, out = self.out("memories", "--dir", str(self.p.proj), "--print", "--max-chars", "4000")
        self.assertIn("Never add Co-Authored-By trailers.", out)
        self.assertNotIn("name: commits", out)          # YAML frontmatter stripped
        self.assertIn("mimo project rule: use tabs", out)

    def test_budget_stops_reading(self):
        code, out = self.out("memories", "--dir", str(self.p.proj), "--print", "--max-chars", "10")
        self.assertIn("budget reached", out)

    def test_subdirectory_still_sees_repository_memory(self):
        code, out = self.out("memories", "--dir", str(self.p.sub))
        self.assertIn(f"scope {self.p.proj}", out)

    def test_unrelated_directory_has_no_project_memory(self):
        code, out = self.out("memories", "--dir", str(self.p.other))
        self.assertNotIn("[claude]", out)
        self.assertNotIn("[mimo]", out)          # global memories are still listed, by design
        self.assertIn("[mimo-global]", out)


if __name__ == "__main__":
    unittest.main()
