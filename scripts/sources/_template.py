"""Skeleton for a new source. Copy to `sources/<name>.py` (no leading underscore) and fill it in.

Discovery is automatic: any module in this folder with a NAME attribute is picked up, listed in `doctor`,
accepted by `--source`, and merged into `memories`/`sessions`/`search`/`show`. Nothing else needs editing.

Implement `probe` first and check it with `agent_history.py doctor`: it is the only required function and
the fastest way to know you resolved the right path. Then add `sessions`, `search` and `show`. Leave
`memories` out when the agent keeps no curated memory files - the default raises NotSupported and the CLI
prints a clear message instead of failing.

Checklist before sending a contribution:
  * read-only (open databases with util.open_ro, never write into the agent's directory)
  * lists NEVER_OPEN with every credential/config filename you must not touch
  * only conversation text in `show` (no tool calls, no tool output)
  * snippets are short (util.snip) and respect the caller's limit
  * paths come from CANDIDATES/ENV, never hardcoded to one machine
  * a fixture in tests/fixtures/<name>/ and a row in README.md
"""
from __future__ import annotations

from pathlib import Path

from sources import base
from util import iter_jsonl, open_ro, snip, ts

NAME = "example"  # registry name, also used by --source
TITLE = "Example Agent"
KINDS = ("jsonl",)  # ("sqlite",) ("jsonl",) ("dir",) - informational, used by doctor
CANDIDATES = (  # {home} {data} {config} {appsupport} {appdata} {localappdata}
    "{data}/example/sessions",
    "{appsupport}/example/sessions",
)
ENV = ()  # the agent's own variable, if it has one: ("EXAMPLE_HOME",)
FIND = {"files": (), "dirs": (), "hint": "example"}  # what `doctor --discover` looks for
NEVER_OPEN = ("auth.json", ".credentials.json", "account.json")


def probe(where):
    """Report whether this path is present and has the shape this module expects."""
    where = Path(where)
    if not where.exists():
        return base.Probe("missing", "not found")
    try:
        files = list(where.glob("*.jsonl"))
    except OSError as exc:
        return base.Probe("unreadable", str(exc))
    if files:
        sample = next(iter_jsonl(files[0]), None)
        if not isinstance(sample, dict) or "role" not in sample:
            return base.Probe("schema_mismatch", "jsonl lines do not look like transcripts")
    return base.Probe("ok", "", {"sessions": len(files)})


def sessions(where, roots, limit, include_all=False):
    """Recent conversations for `roots` (None means every project, i.e. `search --all`)."""
    out = []
    for f in sorted(Path(where).glob("*.jsonl"), key=lambda p: -p.stat().st_mtime)[:limit]:
        first = next((o.get("text", "") for o in iter_jsonl(f) if o.get("role") == "user"), "")
        out.append(base.Session(NAME, f.stem, f.stat().st_mtime * 1000, first[:120]))
    return out


def search(where, roots, pat, query, since_ms, limit, include_all=False):
    """Hits as base.Hit; `pat` is the compiled, case-insensitive regex for `query`."""
    hits = []
    for f in Path(where).glob("*.jsonl"):
        if f.stat().st_mtime * 1000 < since_ms:
            continue
        for obj in iter_jsonl(f):
            text = obj.get("text") or ""
            if pat.search(text):
                hits.append(base.Hit(NAME, f.stem, ts(f.stat().st_mtime * 1000), obj.get("role", ""),
                                     snip(text, pat)))
                if len(hits) >= limit:
                    return hits
    return hits


def show(where, session_id):
    """Conversation turns only. Raise LookupError when the id is unknown or ambiguous."""
    f = Path(where) / f"{session_id}.jsonl"
    if not f.exists():
        raise LookupError("session not found")
    return [base.Turn(o.get("role", ""), o.get("text", "")) for o in iter_jsonl(f) if o.get("text")]
