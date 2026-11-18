"""opencode: a sqlite database with session -> message -> part, where part.data is JSON.

The schema is version-coupled. `probe` checks for the tables this module needs, so an upstream rename shows
up as schema_mismatch in `doctor` instead of a silent empty result.
"""
from __future__ import annotations

from pathlib import Path

from sources import base
from util import dir_clause, open_ro, snip, ts

NAME = "opencode"
TITLE = "opencode"
KINDS = ("sqlite",)
CANDIDATES = (
    "{data}/opencode/opencode.db",
    "{appsupport}/opencode/opencode.db",
    "{config}/opencode/opencode.db",
)
ENV = ("AGENT_HISTORY_OPENCODE_DB",)
FIND = {"files": ("opencode.db",), "hint": "opencode"}
NEVER_OPEN = ("auth.json", ".credentials.json", "account.json", "config.toml")

REQUIRED = ("session", "message", "part")


def probe(where):
    where = Path(where)
    if not where.exists():
        return base.Probe("missing", "database not found")
    try:
        with open_ro(where) as c:
            found = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
            if not found:
                return base.Probe("schema_mismatch", "database has no tables")
            missing = [t for t in REQUIRED if t not in found]
            if missing:
                return base.Probe("schema_mismatch", "missing tables: " + ", ".join(missing))
            n = c.execute("select count(*) from session").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - unreadable/not-a-db both mean "cannot use this path"
        return base.Probe("unreadable", f"{type(exc).__name__}: {exc}")
    return base.Probe("ok", "", {"sessions": n})


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


def search(where, roots, pat, query, since_ms, limit, include_all=False):
    where = Path(where)
    if not where.exists():
        return []
    clause, args = dir_clause("s.directory", roots)
    with open_ro(where) as c:
        rows = c.execute(
            "select p.session_id, p.time_created, json_extract(m.data,'$.role'), "
            "json_extract(p.data,'$.text'), s.directory "
            "from part p join message m on m.id=p.message_id join session s on s.id=p.session_id "
            f"where json_extract(p.data,'$.type')='text' and p.data like ? and p.time_created>=? "
            f"and {clause} order by p.time_created desc limit ?",
            [f"%{query}%", since_ms, *args, limit]).fetchall()
    return [base.Hit(NAME, r[0], ts(r[1]), r[2] or "", snip(r[3], pat), r[4] or "")
            for r in rows if r[3] and pat.search(r[3])]


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
