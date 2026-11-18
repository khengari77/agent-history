"""The registry is the extension point: a file in scripts/sources/ with a NAME is a source."""
import unittest

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

from sources import base, get, load_all


class RegistryTest(unittest.TestCase):
    def test_bundled_sources_load_without_errors(self):
        mods, errors = load_all()
        self.assertEqual(errors, [])
        self.assertEqual([m.NAME for m in mods], ["claude", "opencode", "mimo", "codex"])

    def test_template_is_not_registered(self):
        self.assertNotIn("_template", [m.NAME for m in load_all()[0]])

    def test_contract(self):
        for mod in load_all()[0]:
            for attr in ("NAME", "TITLE", "KINDS", "CANDIDATES", "probe", "sessions", "search"):
                self.assertTrue(hasattr(mod, attr), f"{mod.NAME} is missing {attr}")
            self.assertTrue(getattr(mod, "NEVER_OPEN"), f"{mod.NAME} must declare credential files")

    def test_optional_capabilities_degrade(self):
        mod = get("opencode")  # implements history but no curated memory files
        with self.assertRaises(base.NotSupported):
            mod.memories(None, None, 1000)

    def test_every_source_has_a_discovery_rule(self):
        for mod in load_all()[0]:
            find = getattr(mod, "FIND", {})
            self.assertTrue(find.get("files") or find.get("dirs"), f"{mod.NAME} cannot be discovered")


if __name__ == "__main__":
    unittest.main()
