"""Path resolution: platform defaults, environment overrides, saved overrides, and the exit-code contract."""
import json
import shutil
import unittest

from support import Fixture, run


class DoctorTest(Fixture):
    def test_all_sources_ok_on_a_well_formed_home(self):
        code, out = self.out("doctor", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        status = {s["name"]: s["status"] for s in data["sources"]}
        self.assertEqual(status, {"claude": "ok", "opencode": "ok", "mimo": "ok", "codex": "ok"})
        self.assertEqual(data["load_errors"], [])

    def test_missing_source_is_reported_not_hidden(self):
        code, out = self.out("doctor", "--source", "codex", "--json")
        self.assertEqual(code, 0)
        path = self.p.home / ".codex"
        shutil.rmtree(path)
        code, out = self.out("doctor", "--source", "codex", "--json")
        source = json.loads(out)["sources"][0]
        self.assertEqual(source["status"], "missing")

    def test_schema_mismatch_is_diagnosed(self):
        db = self.p.home / ".local" / "share" / "opencode" / "opencode.db"
        import sqlite3
        c = sqlite3.connect(db)
        c.execute("drop table part")
        c.commit()
        c.close()
        out = self.out("doctor", "--source", "opencode", "--json")[1]
        source = json.loads(out)["sources"][0]
        self.assertEqual(source["status"], "schema_mismatch")
        self.assertIn("part", source["detail"])


class PrecedenceTest(Fixture):
    def test_environment_beats_default(self):
        other = self.p.tmp / "alt" / "opencode.db"
        other.parent.mkdir(parents=True)
        shutil.copy(self.p.home / ".local" / "share" / "opencode" / "opencode.db", other)
        code, out, _ = run("doctor", "--source", "opencode", "--json")
        self.assertEqual(json.loads(out)["sources"][0]["path"],
                         str(self.p.home / ".local" / "share" / "opencode" / "opencode.db"))
        from unittest import mock
        with mock.patch.dict("os.environ", {"AGENT_HISTORY_OPENCODE_DB": str(other)}):
            out = run("doctor", "--source", "opencode", "--json")[1]
        source = json.loads(out)["sources"][0]
        self.assertEqual(source["path"], str(other))
        self.assertTrue(source["origin"].startswith("env:"))

    def test_config_beats_default_and_env_beats_config(self):
        other = self.p.tmp / "alt" / "opencode.db"
        other.parent.mkdir(parents=True)
        shutil.copy(self.p.home / ".local" / "share" / "opencode" / "opencode.db", other)
        code, out, _ = self.run_cli("config", "--set", f"opencode={other}")
        self.assertEqual(code, 0, out)
        source = json.loads(self.out("doctor", "--source", "opencode", "--json")[1])["sources"][0]
        self.assertEqual(source["origin"], "config")
        self.assertEqual(source["path"], str(other))

        from unittest import mock
        with mock.patch.dict("os.environ", {"AGENT_HISTORY_OPENCODE_DB": str(other)}):
            source = json.loads(self.out("doctor", "--source", "opencode", "--json")[1])["sources"][0]
        self.assertTrue(source["origin"].startswith("env:"))


class ConfigCommandTest(Fixture):
    def test_set_refuses_a_path_that_does_not_probe(self):
        code, out = self.out("config", "--set", "opencode=/does/not/exist")
        self.assertEqual(code, 2)
        self.assertIn("not saved", out)
        self.assertFalse((self.p.home / ".config" / "agent-history" / "config.json").exists())

    def test_set_refuses_mismatched_schema_without_force(self):
        empty = self.p.tmp / "empty.db"
        import sqlite3
        sqlite3.connect(empty).close()
        code, out = self.out("config", "--set", f"opencode={empty}")
        self.assertEqual(code, 2)
        self.assertIn("schema_mismatch", out)
        code, out = self.out("config", "--set", f"opencode={empty}", "--force")
        self.assertEqual(code, 0)

    def test_unset_restores_default(self):
        other = self.p.tmp / "alt" / "opencode.db"
        other.parent.mkdir(parents=True)
        shutil.copy(self.p.home / ".local" / "share" / "opencode" / "opencode.db", other)
        self.run_cli("config", "--set", f"opencode={other}")
        code, out, _ = self.run_cli("config", "--unset", "opencode")
        self.assertEqual(code, 0)
        source = json.loads(self.out("doctor", "--source", "opencode", "--json")[1])["sources"][0]
        self.assertEqual(source["origin"], "default")


class ExitCodeTest(Fixture):
    def test_named_source_that_is_missing_exits_2(self):
        shutil.rmtree(self.p.home / ".codex")
        code, out, err = self.run_cli("sessions", "--dir", str(self.p.proj), "--source", "codex")
        self.assertEqual(code, 2)
        self.assertIn("codex: missing", err)

    def test_all_is_best_effort(self):
        shutil.rmtree(self.p.home / ".codex")
        code, out, err = self.run_cli("sessions", "--dir", str(self.p.proj))
        self.assertEqual(code, 0)

    def test_unknown_source_name(self):
        code, out, err = self.run_cli("search", "x", "--source", "nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown source", err)


if __name__ == "__main__":
    unittest.main()
