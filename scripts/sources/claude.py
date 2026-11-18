"""Claude Code: ~/.claude/projects/<slug>/{*.jsonl, memory/*.md}.

The slug is the absolute path with every non-alphanumeric character replaced by '-'. Above 200 characters
Claude truncates and appends a short hash we cannot reproduce, so lookups fall back to a prefix match.
"""
from __future__ import annotations

import re
from pathlib import Path

from sources import base
from util import iter_jsonl, snip

NAME = "claude"
TITLE = "Claude Code"
KINDS = ("jsonl",)
CANDIDATES = ("{home}/.claude/projects",)
ENV = ("CLAUDE_CONFIG_DIR",)
FIND = {"dirs": ("projects",), "hint": ".claude"}
NEVER_OPEN = ("auth.json", ".credentials.json", "account.json")

SLUG_MAX = 200


def from_env(value):
    """CLAUDE_CONFIG_DIR points at the config directory; projects live underneath it."""
    return Path(value).expanduser() / "projects"


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _match(folders, root, tree):
    """Folders for one root. Claude records the directory a session was started in, so a descendant of a
    tree root has the root's slug as a prefix."""
    s = slug(Path(root).resolve())
    if tree:
        return [d for d in folders if d.name == s or d.name.startswith(s + "-")]
    exact = [d for d in folders if d.name == s]
    if exact:
        return exact
    if len(s) > SLUG_MAX:  # long paths are truncated with a hash we cannot rebuild
        prefix = s[:SLUG_MAX]
        return [d for d in folders if d.name == prefix or d.name.startswith(prefix + "-")]
    return []


def project_dirs(where, roots):
    """Claude project folders for the given roots, or every folder when roots is None (--all).

    Arabic folder names collapse to dashes and equal-length names can collide, which is a limitation of
    Claude's own layout, not of this lookup.
    """
    where = Path(where)
    if not where.is_dir():
        return []
    folders = [p for p in where.iterdir() if p.is_dir()]
    if roots is None:
        return folders
    out = []
    for root in roots.exact:
        out += _match(folders, root, tree=False)
    for root in roots.trees:
        out += _match(folders, root, tree=True)
    return list(dict.fromkeys(out))


def probe(where):
    where = Path(where)
    if not where.exists():
        return base.Probe("missing", "no claude projects folder")
    if not where.is_dir():
        return base.Probe("schema_mismatch", "expected a directory of project folders")
    try:
        projects = [p for p in where.iterdir() if p.is_dir()]
        sessions = sum(1 for p in projects for _ in p.glob("*.jsonl"))
    except OSError as exc:
        return base.Probe("unreadable", str(exc))
    return base.Probe("ok", "", {"projects": len(projects), "sessions": sessions})


def claude_text(line):
    """(role, text, timestamp) from one transcript line; tool calls, results and system lines are skipped."""
    if not isinstance(line, dict):
        return None
    if line.get("type") not in ("user", "assistant"):
        return None
    msg = line.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return msg.get("role", line["type"]), content, line.get("timestamp")
    parts = [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
    if not any(parts):
        return None
    return msg.get("role", line["type"]), "\n".join(parts), line.get("timestamp")


def first_user(path):
    for line in iter_jsonl(path):
        r = claude_text(line)
        if r and r[0] == "user" and r[1].strip() and not r[1].lstrip().startswith("<"):
            return r[1]
    return ""


def memories(where, roots, budget):
    """Memory files for each ancestor root, labelled with the real project path (not the slug)."""
    out = []
    for root in roots.all_paths():
        for d in project_dirs(where, base.Roots(exact=[root], trees=[])):
            mem = d / "memory"
            if mem.is_dir():
                out += [base.Memory(NAME, str(root), f) for f in sorted(mem.glob("*.md"))]
    return out


def sessions(where, roots, limit, include_all=False):
    out = []
    for d in project_dirs(where, roots):
        for f in d.glob("*.jsonl"):
            out.append(base.Session(NAME, f.stem, f.stat().st_mtime * 1000, first_user(f)))
    return out


def search(where, roots, pat, query, since_ms, limit, include_all=False):
    hits = []
    files = [f for d in project_dirs(where, roots) for f in d.glob("*.jsonl")]
    for f in sorted(files, key=lambda p: -p.stat().st_mtime):
        if f.stat().st_mtime * 1000 < since_ms:
            continue
        for line in iter_jsonl(f):
            r = claude_text(line)
            if r and pat.search(r[1]):
                hits.append(base.Hit(NAME, f.stem, r[2] or "", r[0], snip(r[1], pat), f.parent.name))
                if len(hits) >= limit:
                    return hits
    return hits


def _find_session(where, session_id):
    files = [f for d in project_dirs(where, None) for f in d.glob(f"{session_id}*.jsonl")]
    return files


def show(where, session_id):
    files = _find_session(where, session_id)
    if not files:
        raise LookupError("session not found")
    if len(files) > 1:
        raise LookupError("ambiguous session prefix, matches: " + ", ".join(f.stem for f in files[:5]))
    return [base.Turn(r[0], r[1]) for r in map(claude_text, iter_jsonl(files[0]))
            if r and r[1].strip()]
