"""Small helpers shared by every source module."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


def ts(ms):
    """Epoch milliseconds -> 'YYYY-MM-DD HH:MM' (the printable form used by all listings)."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M") if ms else "?"


def iso_ms(s):
    """RFC3339 timestamps (Codex) -> epoch ms so they sort and print like the other sources."""
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def one_line(text):
    """Collapse whitespace: transcripts contain newlines and the listings are one line per item."""
    return " ".join(str(text).split())


def snip(text, pat, width=110):
    """A short window around the first regex match, so a hit shows the word in context."""
    text = one_line(text)
    m = pat.search(text) if pat else None
    if not m:
        return text[: width * 2]
    a = max(0, m.start() - width)
    return ("…" if a else "") + text[a : m.end() + width] + (
        "…" if m.end() + width < len(text) else ""
    )


def open_ro(db):
    """Open a sqlite database read-only. Never creates, migrates or writes anything."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)


def iter_jsonl(path):
    """Yield parsed objects from a jsonl file, skipping malformed lines (transcripts are append-only and
    a killed process can leave a half-written final line)."""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def tables(db):
    with open_ro(db) as c:
        return {r[0] for r in c.execute("select name from sqlite_master where type in ('table','view')")}


def dir_clause(col, roots):
    """SQL fragment for a session/thread's worktree column. roots is a base.Roots (or None = no filter)."""
    if roots is None:
        return "1=1", []
    return roots.clause(col)


def parent_of(db):
    return Path(db).parent
