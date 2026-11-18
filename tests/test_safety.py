"""Properties that matter for something that reads other agents' private data: read-only, no credentials,
and discovery that stays out of build folders."""
import hashlib
import json
import os
import shutil
import sqlite3
import unittest
from pathlib import Path

from support import Fixture


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReadOnlyTest(Fixture):
    def test_databases_and_transcripts_are_untouched(self):
        files = [
            self.p.home / ".local" / "share" / "opencode" / "opencode.db",
            self.p.home / ".local" / "share" / "mimocode" / "mimocode.db",
            self.p.home / ".codex" / "state_5.sqlite",
            self.p.home / ".codex" / "thread_history_1.sqlite",
        ]
        before = {str(f): (digest(f), f.stat().st_mtime_ns) for f in files}
        self.out("sessions", "--dir", str(self.p.proj), "--limit", "20")
        self.out("search", "self-destroy", "--dir", str(self.p.proj), "--limit", "20")
        self.out("memories", "--dir", str(self.p.proj), "--print")
        self.out("show", "codex", "th-main")
        for f in files:
            self.assertEqual(before[str(f)], (digest(f), f.stat().st_mtime_ns), f"{f} was modified")

    def test_credential_files_are_never_opened(self):
        creds = [self.p.home / ".claude" / "auth.json", self.p.home / ".codex" / "auth.json"]
        for c in creds:
            c.chmod(0o000)
            self.addCleanup(c.chmod, 0o600)
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 0)
        code, out, err = self.run_cli("search", "self-destroy", "--dir", str(self.p.proj))
        self.assertEqual(code, 0)
        code, out, err = self.run_cli("memories", "--dir", str(self.p.proj), "--print")
        self.assertEqual(code, 0)
        self.assertNotIn("Permission denied", err)
        for c in creds:
            self.assertNotIn(str(c), out)


class DiscoveryTest(Fixture):
    def _vendor_copy(self):
        vendor = self.p.tmp / "mnt" / "vendor" / "opencode"
        vendor.mkdir(parents=True)
        target = vendor / "opencode.db"
        shutil.copy(self.p.home / ".local" / "share" / "opencode" / "opencode.db", target)
        decoy = self.p.tmp / "mnt" / "node_modules" / "opencode"
        decoy.mkdir(parents=True)
        shutil.copy(target, decoy / "opencode.db")
        return target

    def test_finds_unconventional_path_and_prunes_build_folders(self):
        target = self._vendor_copy()
        code, out, err = self.run_cli("doctor", "--source", "opencode", "--discover",
                                      "--search-root", str(self.p.tmp / "mnt"))
        self.assertEqual(code, 0)
        self.assertIn(str(target), out)
        self.assertNotIn("node_modules", out)
        self.assertIn("strong", out)

    def test_save_writes_a_verified_path(self):
        target = self._vendor_copy()
        self.run_cli("doctor", "--source", "opencode", "--discover",
                     "--search-root", str(self.p.tmp / "mnt"), "--save")
        cfg = self.p.home / ".config" / "agent-history" / "config.json"
        self.assertTrue(cfg.is_file())
        saved = json.loads(cfg.read_text())["sources"]["opencode"]["path"]
        self.assertTrue(Path(saved).is_file())
        from sources import get
        self.assertEqual(get("opencode").probe(saved).status, "ok")
        self.assertIn(saved, {str(target),
                              str(self.p.home / ".local" / "share" / "opencode" / "opencode.db")})

    def test_no_save_without_the_flag(self):
        self._vendor_copy()
        self.run_cli("doctor", "--source", "opencode", "--discover",
                     "--search-root", str(self.p.tmp / "mnt"))
        self.assertFalse((self.p.home / ".config" / "agent-history" / "config.json").exists())

    def test_reports_when_nothing_is_found(self):
        empty = self.p.tmp / "empty"
        empty.mkdir()
        out = self.run_cli("doctor", "--source", "opencode", "--discover",
                           "--search-root", str(empty), "--search-root", str(empty))[1]
        self.assertIn("opencode", out)


class BadSourceTest(Fixture):
    def test_a_broken_database_warns_but_does_not_stop_other_sources(self):
        db = self.p.home / ".local" / "share" / "opencode" / "opencode.db"
        db.write_bytes(b"not a database")
        code, out, err = self.run_cli("search", "self-destroy", "--dir", str(self.p.proj))
        self.assertEqual(code, 0)
        self.assertIn("claude", out)          # other sources still answered
        self.assertIn("opencode", err)        # the broken one explained itself


if __name__ == "__main__":
    unittest.main()
