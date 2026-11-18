"""Test support: build a throwaway HOME containing all four sources, then run the CLI in-process.

Nothing here reads the developer's real agent history. Synthetic transcripts/databases are created under a
temporary directory and HOME/XDG are pointed at it, so the suite proves the lookups work on a machine that
is not this one.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import agent_history  # noqa: E402

T0 = 1_700_000_000             # base epoch seconds; times below are offsets in ms
ENV_VARS = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "MIMOCODE_HOME", "OPENCODE_HOME",
            "XDG_DATA_HOME", "XDG_CONFIG_HOME", "AGENT_HISTORY_CLAUDE", "AGENT_HISTORY_OPENCODE",
            "AGENT_HISTORY_OPENCODE_DB", "AGENT_HISTORY_MIMO", "AGENT_HISTORY_MIMO_DB",
            "AGENT_HISTORY_MIMO_MEM", "AGENT_HISTORY_CODEX")


def claude_slug(p):
    return re.sub(r"[^A-Za-z0-9]", "-", str(p))


def run(*argv):
    """Invoke the CLI and capture (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = agent_history.main([str(a) for a in argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


class Paths:
    """Everything a test needs to point at."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.home = tmp / "home"
        self.work = tmp / "work"
        self.proj = self.work / "proj"          # a git repository
        self.sub = self.proj / "pkg"            # a subdirectory of it
        self.sibling = self.work / "sibling"    # a different repository
        self.other = tmp / "unrelated"
        self.claude_mem = self.home / ".claude" / "projects" / claude_slug(self.proj) / "memory"


def build(tmp: Path) -> Paths:
    p = Paths(tmp)
    for d in (p.home, p.proj, p.sub, p.sibling, p.other):
        d.mkdir(parents=True, exist_ok=True)
    (p.proj / ".git").mkdir(exist_ok=True)
    (p.sibling / ".git").mkdir(exist_ok=True)

    _claude(p)
    _opencode(p)
    _mimo(p)
    _codex(p)

    (p.proj / "AGENTS.md").write_text("project rule: never commit without asking\n")
    (p.home / ".claude" / "auth.json").write_text('{"token":"secret"}')
    (p.home / ".codex" / "auth.json").write_text('{"token":"secret"}')
    return p


# ------------------------------------------------------------------ claude
def _claude(p: Paths):
    proj_dir = p.home / ".claude" / "projects" / claude_slug(p.proj)
    mem = proj_dir / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# index\n- [feedback.md](feedback.md)\n")
    (mem / "feedback.md").write_text("---\nname: commits\n---\nNever add Co-Authored-By trailers.\n")
    (p.home / ".claude" / "projects" / claude_slug(p.sub)).mkdir(parents=True)

    lines = [
        {"type": "user", "message": {"role": "user", "content": "<command-name>/clear</command-name>"},
         "timestamp": "2026-11-15T09:59:00Z"},
        {"type": "user", "message": {"role": "user", "content": "we discussed the self-destroy flag"},
         "timestamp": "2026-11-15T10:00:00Z"},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "The flag self-destroys the box at the end of the run."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]},
         "timestamp": "2026-11-15T10:01:00Z"},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "TOOL OUTPUT MUST NOT APPEAR"}]},
         "timestamp": "2026-11-15T10:02:00Z"},
        {"type": "system", "message": {"role": "system", "content": "system note"}},
    ]
    f = proj_dir / "sess-claude.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    os.utime(f, (T0, T0))


# ------------------------------------------------------------------ opencode / mimo
def _session_db(path, sessions, extra_sql=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript("""
        create table project(id text, worktree text);
        create table session(id text, parent_id text, title text, directory text, time_updated int);
        create table message(id text, session_id text, data text);
        create table part(id text, message_id text, session_id text, time_created int, data text);
    """)
    for pid, worktree in [("p1", None), ("p2", None)]:
        c.execute("insert into project values (?,?)", (pid, worktree))
    for i, (sid, title, directory, when, role, text) in enumerate(sessions):
        c.execute("insert into session values (?,?,?,?,?)", (sid, None, title, str(directory), when))
        c.execute("insert into message values (?,?,?)", (f"m{i}", sid, json.dumps({"role": role})))
        c.execute("insert into part values (?,?,?,?,?)",
                  (f"p{i}", f"m{i}", sid, when, json.dumps({"type": "text", "text": text})))
    if extra_sql:
        c.executescript(extra_sql)
    c.commit()
    c.close()


def _opencode(p: Paths):
    db = p.home / ".local" / "share" / "opencode" / "opencode.db"
    _session_db(db, [
        ("ses_open_proj", "opencode project session", p.proj, T0 * 1000 + 3000, "user",
         "we discussed the self-destroy flag"),
        ("ses_open_sub", "opencode subdir session", p.sub, T0 * 1000 + 3500, "assistant",
         "subdir self-destroy note"),
        ("ses_open_sib", "opencode sibling session", p.sibling, T0 * 1000 + 9000, "user",
         "sibling self-destroy note"),
        ("ses_open_other", "opencode unrelated session", p.other, T0 * 1000 + 1000, "user",
         "unrelated self-destroy note"),
    ])
    c = sqlite3.connect(db)
    c.execute("update project set worktree=? where id='p1'", (str(p.proj),))
    c.commit()
    c.close()


def _mimo(p: Paths):
    base = p.home / ".local" / "share" / "mimocode"
    db = base / "mimocode.db"
    _session_db(db, [
        ("ses_mimo_proj", "mimo project session", p.proj, T0 * 1000 + 4000, "user", "mimo self-destroy note"),
        ("ses_mimo_ar", "mimo arabic session", p.proj, T0 * 1000 + 4200, "user", "مناهج المفسرين"),
    ])
    c = sqlite3.connect(db)
    c.execute("update project set worktree=? where id='p1'", (str(p.proj),))
    c.executescript("""
        create table history_fts(rowid integer primary key, session_id text, time_created int,
                                 tool_name text, body text);
        create virtual table history_fts_idx using fts5(body);
    """)
    rows = [
        (1, "ses_mimo_proj", T0 * 1000 + 4000, "text", "mimo self-destroy note"),
        (2, "ses_mimo_ar", T0 * 1000 + 4200, "text", "مناهج المفسرين"),
        (3, "ses_mimo_proj", T0 * 1000 + 4100, "Bash", "duplicate of the claude line"),
    ]
    for r in rows:
        c.execute("insert into history_fts values (?,?,?,?,?)", r)
        c.execute("insert into history_fts_idx(rowid, body) values (?,?)", (r[0], r[4]))
    c.commit()
    c.close()
    mem = base / "memory" / "projects"
    (mem / "p1").mkdir(parents=True)
    (mem / "p1" / "MEMORY.md").write_text("mimo project rule: use tabs\n")
    (mem / "global").mkdir(parents=True)
    (mem / "global" / "MEMORY.md").write_text("mimo global rule: be brief\n")


# ------------------------------------------------------------------ codex
def _codex(p: Paths):
    home = p.home / ".codex"
    home.mkdir(parents=True, exist_ok=True)
    (home / "AGENTS.md").write_text("codex global rule: no network during tests\n")
    day = home / "sessions" / "2026" / "11" / "18"
    day.mkdir(parents=True)

    def rollout(name, sid, cwd, text):
        f = day / f"rollout-{name}.jsonl"
        lines = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": str(cwd), "thread_source": "user"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"<environment_context>cwd {cwd}</environment_context>\n{text}"}]},
             "timestamp": "2026-11-15T11:00:00Z"},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "Codex answer about self-destroy."}]},
             "timestamp": "2026-11-15T11:01:00Z"},
            {"type": "event_msg", "payload": {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "MIRRORED EVENT MUST NOT APPEAR"}]}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
        os.utime(f, (T0, T0))
        return f

    r1 = rollout("main", "th-main", p.proj, "self-destroy the box please")
    r2 = rollout("sub", "th-sub", p.sub, "subagent self-destroy work")
    r3 = rollout("guardian", "th-guardian", p.proj, "guardian self-destroy review")

    state = sqlite3.connect(home / "state_5.sqlite")
    state.executescript("""
        create table threads(id text, title text, first_user_message text, updated_at_ms int,
                             thread_source text, rollout_path text, agent_path text,
                             agent_nickname text, cwd text);
    """)
    state.executemany("insert into threads values (?,?,?,?,?,?,?,?,?)", [
        ("th-main", "codex project session", "self-destroy the box please", T0 * 1000 + 5000, "user",
         str(r1), None, None, str(p.proj)),
        ("th-sub", "", "subagent self-destroy work", T0 * 1000 + 6000, "subagent",
         str(r2), "/root/helper", "helper", str(p.sub)),
        ("th-guardian", "security review", "guardian self-destroy review", T0 * 1000 + 7000,
         "guardian_review", str(r3), None, None, str(p.proj)),
    ])
    state.commit()
    state.close()

    hist = sqlite3.connect(home / "thread_history_1.sqlite")
    hist.executescript("create table thread_items(thread_id text, created_at_ms int, item_type text, item_json text);")
    hist.executemany("insert into thread_items values (?,?,?,?)", [
        ("th-main", T0 * 1000 + 5000, "userMessage",
         json.dumps({"content": [{"type": "input_text", "text": "self-destroy the box please"}]})),
        ("th-main", T0 * 1000 + 5100, "agentMessage",
         json.dumps({"text": "Codex history hit for self-destroy."})),
    ])
    hist.commit()
    hist.close()


# ------------------------------------------------------------------ test base
class Fixture(unittest.TestCase):
    """Temporary HOME with all four sources, plus helpers to run the CLI against it."""

    def setUp(self):
        tmpdir = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        self._tmp = Path(tempfile.mkdtemp(prefix="agent-history-test-", dir=tmpdir))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.p = build(self._tmp)
        env = {
            "HOME": str(self.p.home),
            "XDG_DATA_HOME": str(self.p.home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(self.p.home / ".config"),
        }
        for var in ENV_VARS:
            os.environ.pop(var, None)
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        return run(*argv)

    def out(self, *argv):
        code, out, err = self.run_cli(*argv)
        return code, out + err
