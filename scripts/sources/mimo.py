"""MiMo Code: sqlite history plus per-project memory files.

History lives in `history_fts` (plain table) with an FTS5 index in `history_fts_idx`; the same Claude Code
transcripts are often imported, so duplicates are removed by the CLI, not here. Memory files live beside the
database in `memory/projects/<project-id>/` and `memory/projects/global/`.
"""
from __future__ import annotations

import os
from pathlib import Path

from sources import base
from util import dir_clause, open_ro, snip, ts

NAME = "mimo"
TITLE = "MiMo Code"
KINDS = ("sqlite", "dir")
CANDIDATES = (
    "{data}/mimocode/mimocode.db",
    "{appsupport}/mimocode/mimocode.db",
    "{config}/mimocode/mimocode.db",
)
ENV = ("MIMOCODE_HOME", "AGENT_HISTORY_MIMO_DB")
FIND = {"files": ("mimocode.db",), "hint": "mimocode"}
NEVER_OPEN = ("auth.json", ".credentials.json", "account.json", "config.toml")

REQUIRED = ("session", "history_fts", "history_fts_idx")


def from_env(value):
    base_dir = Path(value).expanduser()
    db = base_dir / "mimocode.db"
    return db if db.exists() else base_dir


def memory_root(where):
    """Where memory files sit: explicit override, beside the database, or the platform default."""
    override = os.environ.get("AGENT_HISTORY_MIMO_MEM")
    if override:
        return Path(override).expanduser()
    beside = Path(where).parent / "memory" / "projects"
    if beside.is_dir():
        return beside
    from config import expand
    default = expand("{data}/mimocode/memory/projects") or expand("{appsupport}/mimocode/memory/projects")
    return default


def probe(where):
    where = Path(where)
    if not where.exists():
        return base.Probe("missing", "database not found")
    try:
        with open_ro(where) as c:
            found = {r[0] for r in c.execute("select name from sqlite_master")}
            missing = [t for t in REQUIRED if t not in found]
            if missing:
                return base.Probe("schema_mismatch", "missing tables: " + ", ".join(missing))
            n = c.execute("select count(*) from session").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        return base.Probe("unreadable", f"{type(exc).__name__}: {exc}")
    return base.Probe("ok", "", {"sessions": n})


def project_ids(where, roots):
    """Project ids whose worktree contains one of the roots, longest (most specific) first."""
    if roots is None:
        return []
    try:
        with open_ro(where) as c:
            rows = c.execute("select id, worktree from project").fetchall()
    except Exception:  # noqa: BLE001 - older databases may not have `project`
        return []
    wanted = []
    for root in roots.all_paths():
        r = str(Path(root).resolve())
        for pid, worktree in rows:
            if worktree and worktree != "/" and (r == worktree or r.startswith(worktree.rstrip("/") + "/")):
                wanted.append((pid, len(worktree)))
    wanted.sort(key=lambda t: -t[1])
    out, seen = [], set()
    for pid, _ in wanted:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def memories(where, roots, budget):
    root = memory_root(where)
    out = []
    if not root or not Path(root).is_dir():
        return out
    for pid in project_ids(where, roots)[:1]:
        worktree = ""
        try:
            with open_ro(where) as c:
                row = c.execute("select worktree from project where id = ?", (pid,)).fetchone()
                worktree = row[0] if row else ""
        except Exception:  # noqa: BLE001
            pass
        out += [base.Memory(NAME, worktree or str(pid), f) for f in sorted((Path(root) / pid).glob("*.md"))]
    out += [base.Memory("mimo-global", "/", f) for f in sorted((Path(root) / "global").glob("*.md"))]
    return out


def sessions(where, roots, limit, include_all=False):
    where = Path(where)
    if not where.exists():
        return []
    clause, args = dir_clause("directory", roots)
    with open_ro(where) as c:
        rows = c.execute(
            f"select id, title, time_updated from session where parent_id is null and {clause} "
            "order by time_updated desc limit 50", args).fetchall()
    return [base.Session(NAME, r[0], r[2], r[1] or "") for r in rows]


def _fts_query(query):
    return " ".join('"' + w.replace('"', "") + '"' for w in query.split())


def search(where, roots, pat, query, since_ms, limit, include_all=False):
    where = Path(where)
    if not where.exists():
        return []
    clause, args = dir_clause("s.directory", roots)
    sql = ("select h.session_id, h.time_created, h.tool_name, h.body, s.directory "
           "from history_fts_idx i join history_fts h on h.rowid=i.rowid join session s on s.id=h.session_id "
           f"where history_fts_idx match ? and h.time_created>=? and {clause} "
           "order by h.time_created desc limit ?")
    try:
        with open_ro(where) as c:
            rows = c.execute(sql, [_fts_query(query), since_ms, *args, limit]).fetchall()
    except Exception:  # noqa: BLE001 - FTS syntax rejects some queries; fall back to LIKE
        sql = ("select h.session_id, h.time_created, h.tool_name, h.body, s.directory "
               "from history_fts h join session s on s.id=h.session_id "
               f"where h.body like ? and h.time_created>=? and {clause} "
               "order by h.time_created desc limit ?")
        with open_ro(where) as c:
            rows = c.execute(sql, [f"%{query}%", since_ms, *args, limit]).fetchall()
    return [base.Hit(NAME, r[0], ts(r[1]), r[2] or "text", snip(r[3], pat), r[4] or "")
            for r in rows if r[3]]


def show(where, session_id):
    where = Path(where)
    if not where.exists():
        raise LookupError("database not found")
    with open_ro(where) as c:
        ids = [r[0] for r in c.execute("select id from session where id like ?", (session_id + "%",))]
        if not ids:
            raise LookupError("session not found")
        if len(ids) > 1:
            raise LookupError("ambiguous session prefix, matches: " + ", ".join(ids[:5]))
        rows = c.execute(
            "select json_extract(m.data,'$.role'), json_extract(p.data,'$.text') "
            "from part p join message m on m.id=p.message_id "
            "where p.session_id = ? and json_extract(p.data,'$.type')='text' "
            "order by p.time_created", (ids[0],)).fetchall()
    return [base.Turn(r[0] or "", r[1]) for r in rows if r[1]]
