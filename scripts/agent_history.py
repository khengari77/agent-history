#!/usr/bin/env python3
"""Read-only lookups across the user's OTHER agents: Claude Code, opencode, MiMo Code, Codex, and any source
module added under scripts/sources/.

  agent_history.py memories [--dir D] [--print] [--max-chars 4000]   curated memories for a project (read first)
  agent_history.py sessions [--dir D] [--limit 15] [--source LIST]   recent sessions, all sources
  agent_history.py search QUERY [--dir D | --all] [--source LIST] [--days N] [--limit 15]
  agent_history.py show SOURCE SESSION [--grep RE] [--max-chars 6000]  conversation text, no tool output
  agent_history.py doctor [--json] [--discover] [--search-root DIR] [--save]   where each source lives, and why not
  agent_history.py config [--show] [--set name=path] [--unset name]  saved overrides for unconventional installs

--dir defaults to the current directory. Output is deliberately short (snippets, caps) to save context.
Databases are opened read-only. Credential files are never touched. `doctor` is the first thing to run when
a source is missing; references/discovery.md explains the follow-up.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from sources import base, get, load_all, parse
from util import one_line, snip, ts

MEMORY_NAMES = ("AGENTS.md", "CLAUDE.md", "PROMPT.md")
DEFAULT_SEARCH_ROOTS = ("{data}", "{config}", "{home}", "/opt", "/srv")


# ------------------------------------------------------------------ project roots
def git_root(d):
    """Nearest ancestor containing .git, or None. Bounds session/search lookups so a subdirectory sees its
    repository's history without inheriting every sibling project under the parent folder."""
    for p in [d, *d.parents]:
        if (p / ".git").exists():
            return p
        if p == Path.home() or p == p.parent:
            break
    return None


def project_roots(d, whole_repo=False):
    """exact = this directory and, inside a repo, the repo root; trees = this directory.

    From a repo root that means the whole repository; from a subdirectory it means just that subtree plus
    sessions that were started at the root itself, so a sibling project under the same parent does not leak
    into the answer. --repo widens the subtree to the whole repository.
    """
    d = Path(d).resolve()
    root = git_root(d)
    exact = [d] if root in (None, d) else [d, root]
    trees = [root if whole_repo and root else d]
    return base.Roots(exact=list(dict.fromkeys(exact)), trees=trees)


def ancestor_roots(d):
    """Every ancestor up to and including home: memories are often written at a parent level."""
    out = []
    for p in [Path(d).resolve(), *Path(d).resolve().parents]:
        out.append(p)
        if p == Path.home():
            break
    return base.Roots(exact=out, trees=[])


def project_files(d):
    """Instruction files a project keeps for agents, nearest wins, stopping at the repository root."""
    out = []
    for name in MEMORY_NAMES:
        for q in [Path(d).resolve(), *Path(d).resolve().parents]:
            if (q / name).is_file():
                out.append(base.Memory("project", str(q), q / name))
                break
            if (q / ".git").exists() or q == Path.home():
                break
    return out


# ------------------------------------------------------------------ helpers
def _warn(msg):
    print(msg, file=sys.stderr)


def _load(args):
    mods, errors = load_all()
    wanted, unknown = parse(getattr(args, "source", "all"))
    if unknown:
        _warn(f"unknown source(s): {', '.join(unknown)}; available: {', '.join(m.NAME for m in mods)}")
        raise SystemExit(2)
    mods = [get(n) for n in wanted]
    return mods, config.resolve_all(mods), errors


def _unavailable(mods, resolved):
    """Names explicitly requested whose path is missing or unusable (used for the exit code)."""
    bad = []
    for mod in mods:
        res = resolved[mod.NAME]
        status = mod.probe(res.path).status if res.path else "missing"
        if status != "ok":
            bad.append((mod.NAME, status, str(res.path or "-")))
    return bad


def _call(mod, fn, *a, **kw):
    """Run one source's lookup; a broken database warns instead of killing the other sources."""
    try:
        return fn(*a, **kw)
    except base.NotSupported:
        return []
    except Exception as exc:  # noqa: BLE001
        _warn(f"{mod.NAME}: {type(exc).__name__}: {exc}")
        return []


def _finish(mods, resolved, args):
    """Exit 2 only when the caller named a source that is not usable; "all" is best-effort."""
    if args.source in (None, "", "all"):
        return 0
    bad = _unavailable(mods, resolved)
    for name, status, path in bad:
        _warn(f"{name}: {status} at {path} (run `doctor`)")
    return 2 if bad else 0


def _as_dict(obj):
    return {k: (str(v) if isinstance(v, Path) else v) for k, v in obj.__dict__.items()}


# ------------------------------------------------------------------ memories
def cmd_memories(args):
    mods, resolved, _ = _load(args)
    d = Path(args.dir).resolve()
    roots = ancestor_roots(d)
    items = []
    for mod in mods:
        res = resolved[mod.NAME]
        if res.path and res.path.exists():
            items += _call(mod, mod.memories, res.path, roots, args.max_chars)
    items += project_files(d)
    seen, uniq = set(), []
    for m in items:
        key = str(m.path)
        if key not in seen:
            seen.add(key)
            uniq.append(m)
    if not uniq:
        print(f"no memories found for {d}")
        return 0
    for m in uniq:
        try:
            size = m.path.stat().st_size
        except OSError:
            size = 0
        print(f"[{m.source}] {m.path}  ({size} B, scope {m.scope})")
    if args.print:
        budget = args.max_chars
        for m in uniq:
            if budget <= 0:
                print("... (budget reached; open specific files)")
                break
            try:
                body = m.path.read_text(errors="replace")
            except OSError:
                continue
            body = re.sub(r"^---\n.*?\n---\n", "", body, flags=re.S)  # drop frontmatter
            chunk = body[:budget]
            budget -= len(chunk)
            print(f"\n===== [{m.source}] {m.path.name}\n{chunk.strip()}")
    return 0


# ------------------------------------------------------------------ sessions
def cmd_sessions(args):
    mods, resolved, _ = _load(args)
    roots = project_roots(args.dir, args.repo)
    rows = []
    for mod in mods:
        res = resolved[mod.NAME]
        if res.path:
            rows += _call(mod, mod.sessions, res.path, roots, args.limit, args.include_all)
    rows.sort(key=lambda s: -s.updated_ms)
    rows = rows[: args.limit]
    if args.json:
        print(json.dumps([_as_dict(r) for r in rows], indent=2))
    elif not rows:
        print(f"no sessions found for {Path(args.dir).resolve()}")
    else:
        for r in rows:
            tag = f" [{r.note}]" if r.note and r.note != "user" else ""
            print(f"{ts(r.updated_ms)}  {r.source:8} {r.session_id}  {one_line(r.title)[:90]}{tag}")
    return _finish(mods, resolved, args)


# ------------------------------------------------------------------ search
def cmd_search(args):
    mods, resolved, _ = _load(args)
    pat = re.compile(re.escape(args.query), re.I)
    since = (time.time() - args.days * 86400) * 1000 if args.days else 0
    roots = None if args.all else project_roots(args.dir, args.repo)
    hits = []
    for mod in mods:
        res = resolved[mod.NAME]
        if res.path:
            hits += _call(mod, mod.search, res.path, roots, pat, args.query, since, args.limit,
                          args.include_all)
    seen, uniq = set(), []
    for h in hits:  # MiMo imports Claude sessions, so identical text can appear under both sources
        key = h.text[:160]
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    hits = uniq
    if args.json:
        print(json.dumps([_as_dict(h) for h in hits[: args.limit * 3]], indent=2))
    else:
        for h in hits[: args.limit * 3]:
            print(f"{str(h.when)[:16]}  {h.source:8} {h.session_id[:26]}  {h.role:9} {h.text}")
        print(f"-- {len(hits)} hit(s); `show <source> <session>` for context" if hits else "-- no hits")
    return _finish(mods, resolved, args)


# ------------------------------------------------------------------ show
def cmd_show(args):
    mod = get(args.source)
    if not mod:
        _warn(f"unknown source {args.source}; available: {', '.join(m.NAME for m in load_all()[0])}")
        return 2
    res = config.resolve(mod)
    if not res.path or not res.path.exists():
        _warn(f"{args.source}: no data at {res.path or '-'} (run `doctor`)")
        return 2
    pat = re.compile(args.grep, re.I) if args.grep else None
    try:
        turns = mod.show(res.path, args.session)
    except LookupError as exc:
        _warn(f"{args.source}: {exc}")
        return 2
    except base.NotSupported as exc:
        _warn(f"{args.source} {exc}")
        return 2
    budget = args.max_chars
    for t in turns:
        if pat and not pat.search(t.text):
            continue
        text = one_line(t.text)
        text = snip(text, pat, 300) if pat else text[:600]
        if budget - len(text) < 0:
            print("... (max-chars reached; narrow with --grep)")
            break
        budget -= len(text)
        print(f"[{t.role}] {text}")
    return 0


# ------------------------------------------------------------------ doctor
def _doctor_row(name, title, res, probe):
    counts = " ".join(f"{k}={v}" for k, v in probe.counts.items())
    detail = probe.detail or counts
    print(f"{name:9} {probe.status:15} {str(res.path or '-'):45} ({res.origin})  {detail}")


def _discover(mods, roots, save):
    for mod in mods:
        found = config.discover(mod, roots)
        print(f"\n{mod.NAME} ({mod.TITLE}):")
        if not found:
            print("  nothing found in the scanned roots")
            continue
        saved = False
        for c in found:
            probe = mod.probe(c.path)
            note = f"{c.confidence}: {c.note}; probe={probe.status}"
            if probe.detail and probe.status != "ok":
                note += f" ({probe.detail})"
            print(f"  {note}\n    {c.path}")
            if save and not saved and probe.status == "ok" and c.confidence == "strong":
                config.set_source(mod.NAME, c.path)
                print(f"  saved to {config.config_path()}")
                saved = True
        if not saved and save:
            ok = [c for c in found if mod.probe(c.path).status == "ok"]
            if ok:
                config.set_source(mod.NAME, ok[0].path)
                print(f"  saved {ok[0].path} to {config.config_path()}")
    print("\nRe-run `doctor` to confirm. See references/discovery.md.")


def cmd_doctor(args):
    mods, resolved, errors = _load(args)
    rows = []
    for mod in mods:
        res = resolved[mod.NAME]
        probe = mod.probe(res.path) if res.path else base.Probe("missing", "no candidate path on this platform")
        rows.append((mod.NAME, mod.TITLE, res, probe))
    if args.json:
        print(json.dumps({
            "config": str(config.config_path()),
            "sources": [{"name": n, "title": t, "path": str(r.path) if r.path else None,
                         "origin": r.origin, "status": p.status, "detail": p.detail, "counts": p.counts}
                        for n, t, r, p in rows],
            "load_errors": [{"module": m, "error": e} for m, e in errors],
        }, indent=2))
    else:
        for name, title, res, probe in rows:
            _doctor_row(name, title, res, probe)
        for name, err in errors:
            print(f"{name:9} {'load_error':15} {'-':45} (module)  {err}")
        if not errors:
            print(f"\nconfig: {config.config_path()}")
            if any(p.status != "ok" for _, _, _, p in rows):
                print("some sources are unavailable: `doctor --discover` looks for them, "
                      "`config --set name=path` records one you know.")
    if args.discover:
        roots = [config.expand(t) for t in DEFAULT_SEARCH_ROOTS if config.expand(t)]
        roots += [Path(r).expanduser() for r in args.search_root]
        unique = list(dict.fromkeys(roots))
        print(f"\nscanning: {', '.join(str(p) for p in unique)}")
        _discover(mods, unique, args.save)
    return 0


# ------------------------------------------------------------------ config
def cmd_config(args):
    if args.set:
        if "=" not in args.set:
            _warn("expected name=path")
            return 2
        name, path = args.set.split("=", 1)
        mod = get(name)
        if not mod:
            _warn(f"unknown source {name}; available: {', '.join(m.NAME for m in load_all()[0])}")
            return 2
        p = Path(path).expanduser()
        probe = mod.probe(p)
        if probe.status != "ok" and not args.force:
            _warn(f"{name}: {probe.status} at {p}" + (f" ({probe.detail})" if probe.detail else "")
                  + "; not saved (use --force to override)")
            return 2
        saved = config.set_source(name, p)
        print(f"{name} -> {p}\nsaved to {saved}")
        return 0
    if args.unset:
        if not get(args.unset):
            _warn(f"unknown source {args.unset}; available: {', '.join(m.NAME for m in load_all()[0])}")
            return 2
        config.unset_source(args.unset)
        print(f"{args.unset}: override removed ({config.config_path()})")
        return 0
    mods, resolved, _ = _load(args)
    print(json.dumps({
        "config": str(config.config_path()),
        "sources": {n: {"path": str(r.path) if r.path else None, "origin": r.origin}
                    for n, r in resolved.items()},
    }, indent=2))
    return 0


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("memories")
    p.add_argument("--dir", default=".")
    p.add_argument("--print", action="store_true")
    p.add_argument("--max-chars", type=int, default=4000)
    p.add_argument("--source", default="all")
    p.set_defaults(func=cmd_memories)

    p = sub.add_parser("sessions")
    p.add_argument("--dir", default=".")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--source", default="all")
    p.add_argument("--repo", action="store_true", help="include the whole git repository from a subdirectory")
    p.add_argument("--include-automated", "--codex-all", dest="include_all", action="store_true",
                   help="include automated/security-review threads (Codex guardian_review)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--dir", default=".")
    p.add_argument("--all", action="store_true", help="search every project, not just this one")
    p.add_argument("--repo", action="store_true", help="include the whole git repository from a subdirectory")
    p.add_argument("--source", default="all")
    p.add_argument("--days", type=int, default=0)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--include-automated", "--codex-all", dest="include_all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show")
    p.add_argument("source")
    p.add_argument("session")
    p.add_argument("--grep")
    p.add_argument("--max-chars", type=int, default=6000)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("doctor")
    p.add_argument("--json", action="store_true")
    p.add_argument("--discover", action="store_true")
    p.add_argument("--search-root", action="append", default=[])
    p.add_argument("--save", action="store_true", help="persist verified discovery results")
    p.add_argument("--source", default="all")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("config")
    p.add_argument("--show", action="store_true")
    p.add_argument("--set")
    p.add_argument("--unset")
    p.add_argument("--force", action="store_true")
    p.add_argument("--source", default="all")
    p.set_defaults(func=cmd_config)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
