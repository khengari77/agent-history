"""Codex: state_*.sqlite indexes threads, thread_history_*.sqlite holds extracted turns, and
sessions/YYYY/MM/DD/rollout-*.jsonl is authoritative.

Filenames are version-suffixed (state_5.sqlite today, state_6.sqlite after an upgrade), so the highest
existing number wins and the rollout scan is the fallback when no index database exists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sources import base
from util import dir_clause, iso_ms, iter_jsonl, open_ro, snip, ts

NAME = "codex"
TITLE = "Codex"
KINDS = ("sqlite", "jsonl", "dir")
CANDIDATES = ("{home}/.codex",)
ENV = ("CODEX_HOME",)
FIND = {"dirs": (".codex",), "hint": ".codex"}
NEVER_OPEN = ("auth.json", "config.toml", ".credentials.json")

SOURCE_FILTER = "coalesce(thread_source,'user') != 'guardian_review'"


def db(where, stem):
    """Highest-numbered <stem>_N.sqlite, or None."""
    best = None
    for p in Path(where).glob(f"{stem}_*.sqlite"):
        m = re.search(rf"{re.escape(stem)}_(\d+)\.sqlite$", p.name)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    return best[1] if best else None


def rollouts(where):
    return sorted(Path(where).glob("sessions/*/*/*/rollout-*.jsonl"))


def probe(where):
    where = Path(where)
    if not where.exists():
        return base.Probe("missing", "no ~/.codex directory")
    if not where.is_dir():
        return base.Probe("schema_mismatch", "expected a directory")
    counts = {"rollouts": len(rollouts(where))}
    state = db(where, "state")
    if state:
        try:
            with open_ro(state) as c:
                counts["threads"] = c.execute("select count(*) from threads").fetchone()[0]
        except Exception as exc:  # noqa: BLE001
            return base.Probe("unreadable", f"{type(exc).__name__}: {exc}", counts)
    elif not counts["rollouts"]:
        return base.Probe("schema_mismatch", "no state_*.sqlite and no rollout files", counts)
    return base.Probe("ok", "rollouts only" if not state else "", counts)


def codex_text(line):
    """(role, text, timestamp) from one rollout line. Only response_item/message carries conversation;
    event_msg/item_completed mirror it, developer turns are the system prompt."""
    if not isinstance(line, dict) or line.get("type") != "response_item":
        return None
    p = line.get("payload") or {}
    if p.get("type") != "message" or p.get("role") not in ("user", "assistant"):
        return None
    parts = [b.get("text", "") for b in p.get("content") or []
             if isinstance(b, dict) and b.get("type") in ("input_text", "output_text")]
    text = "\n".join(t for t in parts if t)
    if not text.strip():
        return None
    return p["role"], strip_wrappers(text), line.get("timestamp")


def strip_wrappers(text):
    """Drop Codex's injected preamble so listings and snippets show the user's own words."""
    text = re.sub(r"^\s*<environment_context>.*?</environment_context>\s*", "", text, flags=re.S)
    return re.sub(r"^\s*The following is the (Codex|Claude Code) agent history.*?\n(?=\S)", "", text, flags=re.S)


def meta(path):
    """(cwd, session_id, thread_source) from a rollout's first session_meta line."""
    for line in iter_jsonl(path):
        if line.get("type") == "session_meta":
            p = line.get("payload") or {}
            return p.get("cwd"), p.get("id") or p.get("session_id"), p.get("thread_source")
        break
    return None, None, None


def first_user(path):
    for line in iter_jsonl(path):
        r = codex_text(line)
        if r and r[0] == "user" and r[1].strip():
            return r[1]
    return ""


def memories(where, roots, budget):
    """Codex keeps no per-project memory here; the global AGENTS.md is the only curated file."""
    p = Path(where) / "AGENTS.md"
    return [base.Memory("codex-global", "/", p)] if p.is_file() else []


def sessions(where, roots, limit, include_all=False):
    where = Path(where)
    if not where.exists():
        return []
    state = db(where, "state")
    if not state:
        out = []
        for f in rollouts(where):
            cwd, sid, src = meta(f)
            if not cwd or not _under(cwd, roots):
                continue
            if src == "guardian_review" and not include_all:
                continue
            note = "" if (src or "user") == "user" else (src or "")
            out.append(base.Session(NAME, sid or f.stem, f.stat().st_mtime * 1000,
                                    first_user(f)[:200], note))
        return out
    clause, args = dir_clause("cwd", roots)
    sql = f"select id, title, first_user_message, updated_at_ms, coalesce(thread_source,'user'), " \
          f"rollout_path, agent_path, agent_nickname from threads where {clause}"
    if not include_all:
        sql += f" and {SOURCE_FILTER}"
    with open_ro(state) as c:
        try:
            rows = c.execute(sql + " order by updated_at_ms desc limit 50", args).fetchall()
        except Exception:  # noqa: BLE001 - older schema without agent_path/agent_nickname
            rows = c.execute(
                f"select id, title, first_user_message, updated_at_ms, coalesce(thread_source,'user'), "
                f"rollout_path, null, null from threads where {clause}"
                + ("" if include_all else f" and {SOURCE_FILTER}")
                + " order by updated_at_ms desc limit 50", args).fetchall()
    out = []
    for sid, title, first, t, src, path, apath, nick in rows:
        title = (title or "").strip() or strip_wrappers(first or "").strip()
        if not title:
            title = (f"[{src} {apath}]" if apath else f"[{src} {nick}]" if nick else "") or \
                (first_user(path) if path else "")
        out.append(base.Session(NAME, sid, t, title, "" if (src or "user") == "user" else (src or "")))
    return out


def _under(cwd, roots):
    return True if roots is None else bool(cwd) and roots.contains(cwd)


def search(where, roots, pat, query, since_ms, limit, include_all=False):
    where = Path(where)
    if not where.exists():
        return []
    hits = []
    hist, state = db(where, "thread_history"), db(where, "state")
    ids = None
    if hist and state and roots is not None:
        clause, args = dir_clause("cwd", roots)
        sql = f"select id from threads where {clause}"
        if not include_all:
            sql += f" and {SOURCE_FILTER}"
        with open_ro(state) as c:
            ids = [r[0] for r in c.execute(sql, args).fetchall()]
        if not ids:
            return search_jsonl(where, roots, pat, since_ms, limit, include_all, set())
    if hist:
        sql = ("select thread_id, created_at_ms, item_type, item_json from thread_items "
               "where item_type in ('userMessage','agentMessage') and created_at_ms >= ? "
               "and lower(item_json) like ?")
        args = [since_ms, f"%{query.lower()}%"]
        if ids is not None:
            sql += f" and thread_id in ({','.join('?' * len(ids))})"
            args += ids
        with open_ro(hist) as c:
            rows = c.execute(sql + " order by created_at_ms desc limit ?", [*args, limit * 2]).fetchall()
        found = []
        for tid, t0, itype, item in rows:
            try:
                obj = json.loads(item)
            except json.JSONDecodeError:
                continue
            if itype == "userMessage":
                text = strip_wrappers("\n".join(b.get("text", "") for b in obj.get("content") or []
                                                 if isinstance(b, dict)))
                role = "user"
            else:
                text, role = obj.get("text") or "", "assistant"
            if text and pat.search(text):
                found.append((tid, t0, role, snip(text, pat)))
                if len(found) >= limit:
                    break
        cwds = {}
        if found and state:
            tids = list({f[0] for f in found})
            with open_ro(state) as c:
                cwds = dict(c.execute(
                    f"select id, cwd from threads where id in ({','.join('?' * len(tids))})", tids).fetchall())
        hits += [base.Hit(NAME, tid, ts(t0), role, text, cwds.get(tid) or "")
                 for tid, t0, role, text in found]
    if len(hits) < limit:
        hits += search_jsonl(where, roots, pat, since_ms, limit - len(hits), include_all,
                             {h.session_id for h in hits})
    return hits


def search_jsonl(where, roots, pat, since_ms, limit, include_all, seen):
    hits = []
    for f in sorted(rollouts(where), key=lambda p: -p.stat().st_mtime):
        if f.stat().st_mtime * 1000 < since_ms:
            break  # sorted newest-first
        cwd, sid, src = meta(f)
        if sid in seen or (src == "guardian_review" and not include_all):
            continue
        if not _under(cwd, roots):
            continue
        for line in iter_jsonl(f):
            r = codex_text(line)
            if r and pat.search(r[1]):
                hits.append(base.Hit(NAME, sid or f.stem, ts(iso_ms(r[2])), r[0], snip(r[1], pat), cwd or ""))
                if len(hits) >= limit:
                    return hits
    return hits


def show(where, session_id):
    where = Path(where)
    path = None
    state = db(where, "state")
    if state:
        with open_ro(state) as c:
            row = c.execute("select rollout_path from threads where id like ?",
                            (session_id + "%",)).fetchall()
        if len(row) > 1:
            raise LookupError(f"ambiguous session prefix ({len(row)} matches), use a longer id")
        path = row[0][0] if row and row[0][0] else None
    f = Path(path) if path and Path(path).exists() else \
        next(iter(Path(where).glob(f"sessions/*/*/*/rollout-*{session_id}*.jsonl")), None)
    if not f:
        raise LookupError("session not found")
    return [base.Turn(r[0], r[1]) for r in map(codex_text, iter_jsonl(f)) if r and r[1].strip()]
