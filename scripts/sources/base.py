"""The contract every source module implements.

A source module is a plain module in `scripts/sources/` (not a class) exposing a few constants and up to
four read functions. `sources/__init__.py` finds it automatically, so adding an agent is one file plus one
fixture in `tests/fixtures/`.

Only `probe()` is mandatory. A source with no notion of curated memories simply leaves `memories`
unimplemented: the default below raises NotSupported and the CLI prints "does not keep memories" instead
of failing. That keeps trivial agents (jsonl logs, single sqlite table) cheap to add.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class NotSupported(Exception):
    """Raised by a capability the source does not implement."""


@dataclass
class Probe:
    """Result of looking at a resolved path: is it there, and is it the shape we expect?"""

    status: str  # ok | missing | unreadable | schema_mismatch
    detail: str = ""
    counts: dict = field(default_factory=dict)


@dataclass
class Memory:
    """One curated memory / instruction file."""

    source: str  # registry name, e.g. "claude", "mimo-global"
    scope: str  # project path the memory belongs to, or "/" for global
    path: Path


@dataclass
class Session:
    source: str
    session_id: str
    updated_ms: int
    title: str
    note: str = ""  # extra tag shown in brackets, e.g. "subagent"


@dataclass
class Hit:
    source: str
    session_id: str
    when: str  # printable timestamp
    role: str
    text: str  # snippet around the match
    where: str = ""  # worktree the hit belongs to


@dataclass
class Turn:
    role: str
    text: str


@dataclass
class Roots:
    """Which project directories a query is about.

    `exact` matches a session whose directory is exactly that path (the working directory and, when we are
    inside a repository, its root). `trees` matches descendants too. Running from a repo root sets
    trees=[root], so the whole repository counts; running from a subdirectory sets trees=[cwd], so sibling
    projects under the same parent are not pulled in by accident.
    """

    exact: list
    trees: list

    def clause(self, col):
        parts, args = [], []
        for r in self.exact:
            parts.append(f"{col} = ?")
            args.append(str(r))
        for r in self.trees:
            parts.append(f"{col} like ?")
            args.append(str(r).rstrip("/") + "/%")
        return ("(" + " or ".join(parts) + ")") if parts else "0=1", args

    def all_paths(self):
        return list(dict.fromkeys([*self.exact, *self.trees]))

    def contains(self, path):
        p = str(path or "").rstrip("/")
        return any(p == str(r).rstrip("/") for r in self.exact) or \
            any(p.startswith(str(r).rstrip("/") + "/") for r in self.trees)


# ------------------------------------------------------------------ default capabilities
def memories(path, roots, budget):
    raise NotSupported("does not keep curated memory files")


def show(path, session_id):
    raise NotSupported("cannot replay a session")
